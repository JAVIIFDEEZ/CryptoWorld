"""
tests/integration/test_price_structure.py — Soportes/resistencias y divergencias.

Verifica los pivotes (sin lookahead escondido), la agrupación de niveles por
toques, la clasificación soporte/resistencia, las divergencias RSI/precio con
series construidas a mano, y el endpoint.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services.price_structure import (
    cluster_levels, detect_divergences, find_pivots, support_resistance,
)


class TestPivots:

    @pytest.mark.unit
    def test_finds_confirmed_extremes(self):
        # Triángulo: sube hasta el índice 10 y baja → un máximo en 10
        up = np.concatenate([np.linspace(100, 120, 11), np.linspace(119, 100, 10)])
        highs, lows = find_pivots(up, up, k=3)
        assert 10 in highs
        assert all(i >= 3 and i <= len(up) - 4 for i in highs + lows)  # bordes excluidos

    @pytest.mark.unit
    def test_last_k_bars_cannot_confirm(self):
        # El máximo está en la penúltima vela: no puede confirmarse con k=3
        s = np.concatenate([np.linspace(100, 110, 20), [130.0]])
        s = np.append(s, 129.0)
        highs, _ = find_pivots(s, s, k=3)
        assert (len(s) - 2) not in highs


class TestLevels:

    @pytest.mark.unit
    def test_clusters_similar_prices_by_touches(self):
        # Tres toques ~100 y uno aislado en 150 → nivel fuerte en ~100
        levels = cluster_levels([100.0, 100.3, 99.8, 150.0], tolerance_pct=0.6)
        assert levels[0]["touches"] == 3
        assert levels[0]["price"] == pytest.approx(100.03, abs=0.1)
        assert levels[1]["touches"] == 1

    @pytest.mark.unit
    def test_support_vs_resistance_classification(self):
        # Precio oscila entre ~100 (suelo) y ~120 (techo); cierra en 110
        n = 120
        t = np.arange(n)
        close = 110 + 10 * np.sin(t * 2 * np.pi / 20)
        close[-1] = 110.0
        high = close + 0.5
        low = close - 0.5
        levels = support_resistance(high, low, close, k=3, tolerance_pct=1.0)
        assert levels, "debe detectar niveles en una oscilación regular"
        kinds = {lv["kind"] for lv in levels}
        assert "support" in kinds and "resistance" in kinds
        for lv in levels:
            if lv["kind"] == "resistance":
                assert lv["price"] >= 110.0 and lv["distance_pct"] >= 0
            else:
                assert lv["price"] < 110.0 and lv["distance_pct"] < 0

    @pytest.mark.unit
    def test_short_series_returns_empty(self):
        s = np.linspace(100, 110, 5)
        assert support_resistance(s, s, s) == []


def _divergence_series(kind: str):
    """Construye cierre+RSI sintéticos con dos picos/valles controlados."""
    n = 80
    close = np.full(n, 100.0)
    rsi = np.full(n, 50.0)
    if kind == "bearish":
        # picos de precio en 40 (110) y 60 (115: más alto); RSI 75 → 65 (más bajo)
        for i, (px, r) in [(40, (110.0, 75.0)), (60, (115.0, 65.0))]:
            close[i] = px
            rsi[i] = r
    else:
        # valles: precio 90 → 85 (más bajo); RSI 25 → 35 (más alto)
        for i, (px, r) in [(40, (90.0, 25.0)), (60, (85.0, 35.0))]:
            close[i] = px
            rsi[i] = r
    return close, rsi


class TestDivergences:

    @pytest.mark.unit
    def test_bearish_divergence_detected(self):
        close, rsi = _divergence_series("bearish")
        divs = detect_divergences(close, rsi, k=3, lookback=80)
        assert any(d["type"] == "bearish" for d in divs)
        d = next(d for d in divs if d["type"] == "bearish")
        assert d["price_to"] > d["price_from"] and d["rsi_to"] < d["rsi_from"]

    @pytest.mark.unit
    def test_bullish_divergence_detected(self):
        close, rsi = _divergence_series("bullish")
        divs = detect_divergences(close, rsi, k=3, lookback=80)
        assert any(d["type"] == "bullish" for d in divs)

    @pytest.mark.unit
    def test_no_divergence_when_rsi_confirms(self):
        # Precio sube y el RSI también (confirmación, no divergencia)
        n = 80
        close = np.full(n, 100.0)
        rsi = np.full(n, 50.0)
        close[40], rsi[40] = 110.0, 60.0
        close[60], rsi[60] = 115.0, 70.0
        divs = detect_divergences(close, rsi, k=3, lookback=80)
        assert not any(d["type"] == "bearish" for d in divs)


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/analysis/levels/", {"asset_symbol": "BTC"}).status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_structure(self, authenticated_client, monkeypatch):
        from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult
        n = 200
        t = np.arange(n)
        close = 110 + 10 * np.sin(t * 2 * np.pi / 20)
        df = pd.DataFrame({
            "timestamp": [1_700_000_000_000 + i * 3_600_000 for i in range(n)],
            "open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
            "volume": [1000.0] * n,
        })
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1h", limit=400, **kw: OhlcvFetchResult(df=df, source="binance"),
        )
        resp = authenticated_client.get("/api/analysis/levels/", {"asset_symbol": "LVLTEST", "interval": "1h"})
        assert resp.status_code == 200
        assert set(resp.data) >= {"levels", "divergences", "nearest_support", "nearest_resistance"}
        assert len(resp.data["levels"]) > 0

    @pytest.mark.integration
    def test_endpoint_requires_symbol(self, authenticated_client):
        assert authenticated_client.get("/api/analysis/levels/").status_code == 400
