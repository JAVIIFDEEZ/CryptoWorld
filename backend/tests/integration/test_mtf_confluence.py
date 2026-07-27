"""
tests/integration/test_mtf_confluence.py — Confluencia multi-marco temporal.

Verifica la AGREGACIÓN del caso de uso: ponderación de la alineación (los marcos
altos pesan más), % de acuerdo direccional, veredicto honesto (ALINEADO / MIXTO /
NEUTRAL), tolerancia a marcos caídos y el endpoint. El dashboard de señales por
marco se mockea con summaries controlados (su matemática de indicadores ya tiene
sus propios tests); el OHLCV se mockea con un df mínimo.
"""

import numpy as np
import pandas as pd
import pytest

from core.application.use_cases.get_mtf_confluence import GetMtfConfluenceUseCase
from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult


def _df(n=120):
    close = 100 + np.arange(n, dtype=float)
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 3600000 for i in range(n)],
        "open": close, "high": close + 1, "low": close - 1, "close": close,
        "volume": [1000.0] * n,
    })


def _summary(score: float, total: int = 10, verdict: str = "NEUTRAL") -> dict:
    return {"summary": {"verdict": verdict, "score": score, "total": total,
                        "buy_count": 0, "neutral_count": 0, "sell_count": 0},
            "last_price": 100.0, "indicators": []}


def _mock(monkeypatch, per_interval_score: dict, missing: set | None = None):
    """Mockea OHLCV (df mínimo, o None para marcos caídos) y el dashboard con un
    score controlado por intervalo."""
    missing = missing or set()
    calls = {"interval": None}

    def fake_fetch(symbol, interval="1d", limit=300, **kw):
        calls["interval"] = interval
        if interval in missing:
            return None
        return OhlcvFetchResult(df=_df(), source="binance")

    def fake_dashboard(df):
        # calls["interval"] guarda el último intervalo pedido por el use case
        score = per_interval_score[calls["interval"]]
        return _summary(score)

    monkeypatch.setattr(
        "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe", fake_fetch,
    )
    monkeypatch.setattr(
        "core.domain.services.technical_analysis_service.calculate_signals_dashboard",
        fake_dashboard,
    )


class TestConfluence:

    @pytest.mark.unit
    def test_all_frames_bullish_gives_aligned_verdict(self, monkeypatch):
        # score 10 de máx 20 → normalized +0.5 en los 4 marcos
        _mock(monkeypatch, {"15m": 10, "1h": 10, "4h": 10, "1d": 10})
        r = GetMtfConfluenceUseCase().execute("BTC")
        assert r["frames_analyzed"] == 4
        assert r["alignment_score"] == pytest.approx(0.5)
        assert r["agreement_pct"] == 100.0
        assert r["verdict"] == "ALINEADO_ALCISTA"

    @pytest.mark.unit
    def test_all_frames_bearish_gives_aligned_bearish(self, monkeypatch):
        _mock(monkeypatch, {"15m": -10, "1h": -10, "4h": -10, "1d": -10})
        r = GetMtfConfluenceUseCase().execute("BTC")
        assert r["alignment_score"] == pytest.approx(-0.5)
        assert r["verdict"] == "ALINEADO_BAJISTA"

    @pytest.mark.unit
    def test_conflicting_frames_give_mixed(self, monkeypatch):
        # Intradía alcista fuerte pero marcos altos bajistas → dominan los altos
        # (pesos 1+2 vs 3+4) y el acuerdo es 50% → MIXTO, nunca ALINEADO.
        _mock(monkeypatch, {"15m": 10, "1h": 10, "4h": -10, "1d": -10})
        r = GetMtfConfluenceUseCase().execute("BTC")
        assert r["verdict"] in ("MIXTO", "NEUTRAL")
        assert r["alignment_score"] < 0  # la tendencia de fondo manda

    @pytest.mark.unit
    def test_higher_frames_weigh_more(self, monkeypatch):
        # 1d alcista (peso 4) vs 15m bajista igual de fuerte (peso 1); resto plano.
        _mock(monkeypatch, {"15m": -10, "1h": 0, "4h": 0, "1d": 10})
        r = GetMtfConfluenceUseCase().execute("BTC")
        # (−0.5·1 + 0 + 0 + 0.5·4) / 10 = +0.15 → el marco alto domina
        assert r["alignment_score"] == pytest.approx(0.15)

    @pytest.mark.unit
    def test_weak_direction_is_neutral(self, monkeypatch):
        _mock(monkeypatch, {"15m": 1, "1h": 1, "4h": 1, "1d": 1})   # +0.05 normalizado
        r = GetMtfConfluenceUseCase().execute("BTC")
        assert r["verdict"] == "NEUTRAL"

    @pytest.mark.unit
    def test_failed_frame_does_not_break(self, monkeypatch):
        _mock(monkeypatch, {"1h": 10, "4h": 10, "1d": 10}, missing={"15m"})
        r = GetMtfConfluenceUseCase().execute("BTC")
        assert r["frames_analyzed"] == 3
        assert any("error" in f for f in r["frames"])
        assert r["verdict"] == "ALINEADO_ALCISTA"

    @pytest.mark.unit
    def test_all_frames_failed_errors(self, monkeypatch):
        _mock(monkeypatch, {}, missing={"15m", "1h", "4h", "1d"})
        r = GetMtfConfluenceUseCase().execute("BTC")
        assert "error" in r

    @pytest.mark.unit
    def test_missing_symbol(self):
        assert "error" in GetMtfConfluenceUseCase().execute("")


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/analysis/mtf/", {"asset_symbol": "BTC"}).status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_confluence(self, authenticated_client, monkeypatch):
        _mock(monkeypatch, {"15m": 10, "1h": 10, "4h": 10, "1d": 10})
        resp = authenticated_client.get("/api/analysis/mtf/", {"asset_symbol": "MTFTEST"})
        assert resp.status_code == 200
        assert set(resp.data) >= {"frames", "alignment_score", "agreement_pct", "verdict"}

    @pytest.mark.integration
    def test_endpoint_requires_symbol(self, authenticated_client):
        assert authenticated_client.get("/api/analysis/mtf/").status_code == 400
