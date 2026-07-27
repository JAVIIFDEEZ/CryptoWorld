"""
tests/integration/test_quant_snapshot.py — Terminal cuantitativa.

Verifica la matemática pura del servicio de dominio quant_metrics (anualización,
régimen de tendencia, posición en el rango, beta/correlación frente a BTC,
volumen) y el cableado del caso de uso + endpoint (OHLCV mockeado).
"""

import numpy as np
import pandas as pd
import pytest


def _ohlcv_from_close(close: np.ndarray) -> pd.DataFrame:
    n = len(close)
    return pd.DataFrame({
        "timestamp": [1_700_000_000_000 + i * 3_600_000 for i in range(n)],
        "open": close, "high": close + 1.0, "low": close - 1.0, "close": close,
        "volume": np.full(n, 1000.0),
    })


def _from_returns(returns: np.ndarray, start: float = 100.0) -> np.ndarray:
    prices = [start]
    for r in returns:
        prices.append(prices[-1] * (1.0 + r))
    return np.asarray(prices, dtype=float)


class TestQuantMetricsDomain:

    @pytest.mark.unit
    def test_periods_per_year_by_interval(self):
        from core.domain.services.quant_metrics import periods_per_year
        assert periods_per_year("1h") == pytest.approx(8760.0)
        assert periods_per_year("1d") == pytest.approx(365.0)
        assert periods_per_year("4h") == pytest.approx(2190.0)
        assert periods_per_year("15m") == pytest.approx(35040.0)

    @pytest.mark.unit
    def test_snapshot_has_full_structure(self):
        from core.domain.services.quant_metrics import compute_quant_snapshot
        close = 100 + np.arange(200, dtype=float)
        snap = compute_quant_snapshot(_ohlcv_from_close(close), interval="1h", symbol="TEST")
        for key in ("volatility", "returns", "risk", "range", "market", "volume",
                    "regime", "bias", "spark", "last_price"):
            assert key in snap
        assert snap["volatility"]["annualized_pct"] is not None
        assert snap["last_price"] == pytest.approx(299.0)

    @pytest.mark.unit
    def test_insufficient_data_errors(self):
        from core.domain.services.quant_metrics import compute_quant_snapshot
        close = 100 + np.arange(10, dtype=float)
        assert "error" in compute_quant_snapshot(_ohlcv_from_close(close), interval="1h")

    @pytest.mark.unit
    def test_strong_uptrend_is_bullish(self):
        from core.domain.services.quant_metrics import compute_quant_snapshot
        close = 100 + np.arange(200, dtype=float) * 1.5     # tendencia limpia al alza
        snap = compute_quant_snapshot(_ohlcv_from_close(close), interval="1h", symbol="UP")
        assert snap["regime"]["direction"] == "ALCISTA"
        assert snap["bias"] == "ALCISTA"
        # El último precio está en lo alto del rango de la ventana.
        assert snap["range"]["pct_rank"] > 90
        assert snap["range"]["dist_to_high_pct"] > -1.0     # pegado al máximo

    @pytest.mark.unit
    def test_strong_downtrend_is_bearish(self):
        from core.domain.services.quant_metrics import compute_quant_snapshot
        close = 400 - np.arange(200, dtype=float) * 1.5
        snap = compute_quant_snapshot(_ohlcv_from_close(close), interval="1h", symbol="DOWN")
        assert snap["regime"]["direction"] == "BAJISTA"
        assert snap["bias"] == "BAJISTA"
        assert snap["range"]["pct_rank"] < 10               # pegado al mínimo

    @pytest.mark.unit
    def test_returns_multi_horizon(self):
        from core.domain.services.quant_metrics import compute_quant_snapshot
        close = np.full(200, 100.0)
        close[-1] = 110.0                                   # +10% en la última vela
        snap = compute_quant_snapshot(_ohlcv_from_close(close), interval="1h", symbol="R")
        r1 = next(r["pct"] for r in snap["returns"] if r["h"] == 1)
        assert r1 == pytest.approx(10.0, abs=1e-6)

    @pytest.mark.unit
    def test_beta_and_correlation_vs_btc(self):
        from core.domain.services.quant_metrics import compute_quant_snapshot
        rng = np.random.default_rng(42)
        btc_ret = rng.normal(0, 0.01, 250)
        asset_ret = 1.5 * btc_ret + rng.normal(0, 0.001, 250)   # beta≈1.5, muy correlado
        asset = _ohlcv_from_close(_from_returns(asset_ret))
        btc = _ohlcv_from_close(_from_returns(btc_ret))
        snap = compute_quant_snapshot(asset, interval="1h", btc_df=btc, symbol="ALT")
        assert snap["market"]["beta_btc"] == pytest.approx(1.5, abs=0.2)
        assert snap["market"]["corr_btc"] > 0.9

    @pytest.mark.unit
    def test_btc_excludes_its_own_beta(self):
        from core.domain.services.quant_metrics import compute_quant_snapshot
        close = 100 + np.arange(200, dtype=float)
        df = _ohlcv_from_close(close)
        snap = compute_quant_snapshot(df, interval="1h", btc_df=df, symbol="BTC")
        assert snap["market"]["beta_btc"] is None

    @pytest.mark.unit
    def test_zero_volume_flagged(self):
        from core.domain.services.quant_metrics import compute_quant_snapshot
        close = 100 + np.arange(200, dtype=float)
        df = _ohlcv_from_close(close)
        df["volume"] = 0.0
        snap = compute_quant_snapshot(df, interval="1h", symbol="NV")
        assert snap["volume"]["has_volume"] is False
        assert snap["volume"]["relative"] is None


class TestUseCase:

    @pytest.mark.unit
    def test_missing_symbol(self):
        from core.application.use_cases.get_quant_snapshot import GetQuantSnapshotUseCase
        assert "error" in GetQuantSnapshotUseCase().execute("")

    @pytest.mark.unit
    def test_use_case_composes_snapshot(self, monkeypatch):
        from core.application.use_cases.get_quant_snapshot import GetQuantSnapshotUseCase
        from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult

        close = 100 + np.arange(200, dtype=float)
        df = _ohlcv_from_close(close)

        def fake_fetch(symbol, interval="1h", limit=500, **kw):
            return OhlcvFetchResult(df=df, source="binance")

        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe", fake_fetch,
        )
        out = GetQuantSnapshotUseCase().execute("ETH", interval="1h")
        assert out["data_source"] == "binance"
        assert out["symbol"] == "ETH"
        assert out["regime"]["direction"] in ("ALCISTA", "BAJISTA", "NEUTRAL")


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/analysis/quant/", {"asset_symbol": "BTC"}).status_code == 401

    @pytest.mark.integration
    def test_requires_symbol(self, authenticated_client):
        assert authenticated_client.get("/api/analysis/quant/").status_code == 400

    @pytest.mark.integration
    def test_endpoint_returns_snapshot(self, authenticated_client, monkeypatch):
        from django.core.cache import cache
        from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult
        cache.delete("quant_snapshot:QNTTEST:1h")

        close = 100 + np.arange(200, dtype=float)
        df = _ohlcv_from_close(close)

        def fake_fetch(symbol, interval="1h", limit=500, **kw):
            return OhlcvFetchResult(df=df, source="binance")

        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe", fake_fetch,
        )
        resp = authenticated_client.get("/api/analysis/quant/", {"asset_symbol": "QNTTEST"})
        assert resp.status_code == 200
        assert set(resp.data) >= {"volatility", "returns", "risk", "regime", "range"}
