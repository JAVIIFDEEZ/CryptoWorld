"""
tests/integration/test_compare_strategies.py — Comparador cara a cara.

Verifica la comparación de 2-4 estrategias guardadas: evidencia almacenada,
re-ejecución fresca normalizada, correlación entre retornos, veredictos por
dimensión y la validación de entrada del endpoint.
"""

from collections import namedtuple

import numpy as np
import pandas as pd
import pytest


def _df(n=300, seed=5):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    price = np.maximum(100 + 18 * np.sin(t / 18.0) + rng.normal(0, 0.5, n), 5.0)
    return pd.DataFrame({
        "timestamp": (1_600_000_000 + t * 86400) * 1000,
        "open": price, "high": price + 0.3, "low": price - 0.3,
        "close": price, "volume": [1000.0] * n,
    })


def _spec(thr=30.0):
    return {
        "entry": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": thr}]},
        "exit": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 70.0}]},
    }


@pytest.fixture
def two_strategies(db):
    from django.utils import timezone
    from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition
    btc = CryptoAsset.objects.create(symbol="BTC", name="Bitcoin")
    eth = CryptoAsset.objects.create(symbol="ETH", name="Ethereum")
    a = StrategyDefinition.objects.create(
        asset=btc, name="A", spec=_spec(30.0), spec_hash="cmp-a", interval="1d",
        rank=1, fitness=1.5, passed_gating=True, status="validated",
        robustness_metrics={"sharpe": 1.4, "mean_oos_sharpe": 1.0, "pbo": 0.2,
                            "wf_efficiency": 0.8, "n_trades": 20, "cross_consistency": 0.67},
        holdout_metrics={"return_pct": 12.0, "sharpe": 1.1},
        generated_at=timezone.now(),
    )
    b = StrategyDefinition.objects.create(
        asset=eth, name="B", spec=_spec(35.0), spec_hash="cmp-b", interval="1d",
        rank=1, fitness=0.9, passed_gating=True, status="validated",
        robustness_metrics={"sharpe": 1.0, "mean_oos_sharpe": 0.7, "pbo": 0.3,
                            "wf_efficiency": 0.6, "n_trades": 15, "cross_consistency": 1.0},
        holdout_metrics={"return_pct": 20.0, "sharpe": 1.4},
        generated_at=timezone.now(),
    )
    return a, b


@pytest.fixture
def mocked_data(monkeypatch):
    from core.application.use_cases import ohlcv_fetcher
    Fetched = namedtuple("Fetched", ["df", "source"])
    monkeypatch.setattr(
        ohlcv_fetcher, "fetch_ohlcv_dataframe",
        lambda symbol, interval="1d", limit=730, **kw: Fetched(
            _df(seed=sum(ord(c) for c in symbol)), "test"),
    )


class TestUseCase:

    @pytest.mark.integration
    def test_compare_two_strategies(self, two_strategies, mocked_data):
        from core.application.use_cases.compare_strategies import CompareStrategiesUseCase
        a, b = two_strategies
        out = CompareStrategiesUseCase().execute([a.id, b.id])
        assert out["status"] == "OK"
        assert [it["strategy_id"] for it in out["items"]] == [a.id, b.id]
        for it in out["items"]:
            assert it["stored"]["fitness"] is not None
            assert it["fresh"]["available"] is True
            eq = it["fresh"]["equity"]
            assert eq[0] == pytest.approx(1.0)            # crecimiento de 1€
            assert len(eq) <= 160
        # Correlación con ventana común y veredictos coherentes
        assert out["correlation"]["common_days"] >= 5
        assert len(out["correlation"]["matrix"]) == 2
        v = out["verdicts"]
        assert v["best_fitness"] == "BTC 1d"              # 1.5 > 0.9
        assert v["best_holdout"] == "ETH 1d"              # 20 > 12
        assert v["best_generalization"] == "ETH 1d"       # 1.0 > 0.67
        assert v["most_diversifying_pair"] is not None

    @pytest.mark.integration
    def test_survives_without_fresh_data(self, two_strategies, monkeypatch):
        from core.application.use_cases import ohlcv_fetcher
        from core.application.use_cases.compare_strategies import CompareStrategiesUseCase
        monkeypatch.setattr(ohlcv_fetcher, "fetch_ohlcv_dataframe", lambda **kw: None)
        a, b = two_strategies
        out = CompareStrategiesUseCase().execute([a.id, b.id])
        assert out["status"] == "OK"                      # evidencia almacenada basta
        assert all(not it["fresh"]["available"] for it in out["items"])
        assert out["correlation"] is None
        assert out["verdicts"]["best_fitness"] == "BTC 1d"

    @pytest.mark.integration
    def test_unknown_ids(self, two_strategies):
        from core.application.use_cases.compare_strategies import CompareStrategiesUseCase
        a, _ = two_strategies
        out = CompareStrategiesUseCase().execute([a.id, 999_999])
        assert "error" in out


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/strategies/compare/?ids=1,2").status_code == 401

    @pytest.mark.integration
    def test_validates_ids(self, authenticated_client, db):
        assert authenticated_client.get("/api/strategies/compare/?ids=1").status_code == 400
        assert authenticated_client.get("/api/strategies/compare/?ids=a,b").status_code == 400
        assert authenticated_client.get(
            "/api/strategies/compare/?ids=1,2,3,4,5").status_code == 400

    @pytest.mark.integration
    def test_endpoint_returns_comparison(self, authenticated_client, two_strategies, mocked_data):
        a, b = two_strategies
        resp = authenticated_client.get(f"/api/strategies/compare/?ids={a.id},{b.id}")
        assert resp.status_code == 200
        assert resp.data["status"] == "OK"
        assert len(resp.data["items"]) == 2
