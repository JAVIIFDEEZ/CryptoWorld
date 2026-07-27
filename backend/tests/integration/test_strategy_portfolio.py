"""
tests/integration/test_strategy_portfolio.py — Cartera de estrategias campeonas.

Verifica la matemática de dominio (retornos diarios desde equity, alineación,
correlación, métricas de cartera) y el caso de uso end-to-end con OHLCV mockeado
sobre estrategias reales persistidas.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services.portfolio_analysis import (
    align_returns, avg_pairwise_correlation, correlation_matrix,
    daily_returns_from_equity, portfolio_stats,
)


class TestDomainMath:

    @pytest.mark.unit
    def test_daily_returns_from_hourly_equity(self):
        # 48 velas horarias = 2 días completos tras el día base
        day_ms = 86_400_000
        ts = [1_700_000_000_000 + i * 3_600_000 for i in range(48)]
        equity = [100.0] + [100.0 + i for i in range(1, 49)]   # sube 1 por vela
        rets = daily_returns_from_equity(ts, equity)
        assert len(rets) >= 1
        assert all(r > 0 for r in rets.values())               # siempre sube
        del day_ms

    @pytest.mark.unit
    def test_align_keeps_only_common_dates(self):
        a = {"2026-01-01": 0.01, "2026-01-02": 0.02, "2026-01-03": 0.03}
        b = {"2026-01-02": -0.01, "2026-01-03": 0.01, "2026-01-04": 0.02}
        dates, aligned = align_returns({"A": a, "B": b})
        assert dates == ["2026-01-02", "2026-01-03"]
        assert aligned["A"] == [0.02, 0.03] and aligned["B"] == [-0.01, 0.01]

    @pytest.mark.unit
    def test_correlation_perfect_and_inverse(self):
        x = [0.01, -0.02, 0.03, -0.01, 0.02]
        inv = [-v for v in x]
        names, m = correlation_matrix({"A": x, "B": list(x), "C": inv})
        i, j, k = names.index("A"), names.index("B"), names.index("C")
        assert m[i][i] == 1.0
        assert m[i][j] == pytest.approx(1.0)
        assert m[i][k] == pytest.approx(-1.0)
        # media de pares: (1 − 1 − 1) / 3
        assert avg_pairwise_correlation(m) == pytest.approx(-1 / 3, abs=1e-3)

    @pytest.mark.unit
    def test_flat_series_gives_none_not_nan(self):
        _, m = correlation_matrix({"A": [0.01, 0.02, 0.03], "B": [0.0, 0.0, 0.0]})
        assert m[0][1] is None and m[1][0] is None

    @pytest.mark.unit
    def test_portfolio_stats_diversification(self):
        # Dos series perfectamente inversas → cartera plana, drawdown 0
        dates = [f"2026-01-{d:02d}" for d in range(1, 6)]
        x = [0.02, -0.01, 0.03, -0.02, 0.01]
        stats = portfolio_stats(dates, {"A": x, "B": [-v for v in x]})
        assert stats["total_return_pct"] == pytest.approx(0.0, abs=1e-6)
        assert stats["max_drawdown_pct"] == pytest.approx(0.0, abs=1e-6)
        assert len(stats["equity"]) == 5

    @pytest.mark.unit
    def test_portfolio_stats_drawdown(self):
        dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
        stats = portfolio_stats(dates, {"A": [0.10, -0.50, 0.0]})
        # pico 110 → cae a 55 → dd 50%
        assert stats["max_drawdown_pct"] == pytest.approx(50.0, abs=0.01)


@pytest.fixture
def champions(db):
    """Dos estrategias campeonas validadas sobre activos distintos."""
    from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition
    spec = {
        "entry": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 45.0}]},
        "exit": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 60.0}]},
    }
    out = []
    for i, sym in enumerate(["BTC", "ETH"]):
        asset = CryptoAsset.objects.create(symbol=sym, name=sym)
        out.append(StrategyDefinition.objects.create(
            asset=asset, name=f"RSI {sym}", spec=spec, spec_hash=f"h{i}", interval="1d",
            fitness=2.0 - i * 0.5, passed_gating=True, status="validated",
            holdout_metrics={"return_pct": 10.0, "sharpe": 1.0},
        ))
    return out


def _ohlcv(seed: int, n=200):
    rng = np.random.default_rng(seed)
    close = np.maximum(100 + np.cumsum(rng.normal(0.2, 2.0, n)), 5.0)
    return pd.DataFrame({
        "timestamp": [1_700_000_000_000 + i * 86_400_000 for i in range(n)],
        "open": close, "high": close + 1.5, "low": close - 1.5, "close": close,
        "volume": [1000.0] * n,
    })


class TestUseCase:

    @pytest.mark.integration
    def test_portfolio_analysis_end_to_end(self, champions, monkeypatch):
        from core.application.use_cases.strategy_portfolio import StrategyPortfolioUseCase
        from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult

        dfs = {"BTC": _ohlcv(1), "ETH": _ohlcv(2)}
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=500, **kw: OhlcvFetchResult(df=dfs[symbol], source="binance"),
        )
        r = StrategyPortfolioUseCase().execute(top_n=5)
        assert "error" not in r
        assert len(r["members"]) == 2
        assert len(r["correlation_matrix"]) == 2
        assert r["correlation_matrix"][0][0] == 1.0
        assert r["common_days"] >= 5
        assert "total_return_pct" in r["portfolio"] and len(r["portfolio"]["equity"]) > 0

    @pytest.mark.integration
    def test_needs_at_least_two_champions(self, db):
        from core.application.use_cases.strategy_portfolio import StrategyPortfolioUseCase
        assert "error" in StrategyPortfolioUseCase().execute()


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/strategies/portfolio/").status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_analysis_or_honest_error(self, authenticated_client):
        resp = authenticated_client.get("/api/strategies/portfolio/")
        assert resp.status_code == 200
        assert ("error" in resp.data) or ("correlation_matrix" in resp.data)
