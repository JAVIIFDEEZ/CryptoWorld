"""
test_ohlcv_health.py — Salud del almacén histórico OHLCV (calidad de datos).
"""

import time

import pytest

from core.domain.services.data_quality import series_health, overall_health

_STEP = 3_600_000   # 1h en ms
_NOW = 1_700_000_000_000


class TestSeriesHealth:
    def test_healthy(self):
        h = series_health(candles=100, missing_candles=0, last_ms=_NOW,
                          now_ms=_NOW, step_ms=_STEP)
        assert h["status"] == "SANO" and h["completeness_pct"] == 100.0 and h["fresh"]

    def test_with_gaps(self):
        h = series_health(candles=90, missing_candles=10, last_ms=_NOW,
                          now_ms=_NOW, step_ms=_STEP)
        assert h["status"] == "CON_HUECOS" and h["completeness_pct"] == 90.0

    def test_stale(self):
        h = series_health(candles=100, missing_candles=0, last_ms=_NOW - 10 * _STEP,
                          now_ms=_NOW, step_ms=_STEP)
        assert h["status"] == "DESACTUALIZADO" and not h["fresh"]

    def test_empty(self):
        h = series_health(candles=0, missing_candles=0, last_ms=None,
                          now_ms=_NOW, step_ms=_STEP)
        assert h["status"] == "VACIO"


class TestOverall:
    def test_grade_excellent(self):
        series = [{"status": "SANO", "candles": 100} for _ in range(9)] + \
                 [{"status": "CON_HUECOS", "candles": 50}]
        out = overall_health(series)
        assert out["grade"] == "EXCELENTE" and out["healthy_pct"] == 90.0
        assert out["with_gaps"] == 1 and out["total_candles"] == 950

    def test_no_data(self):
        assert overall_health([])["grade"] == "SIN_DATOS"


@pytest.mark.django_db
class TestUseCaseAndApi:
    def _candle(self, symbol, open_time, interval="1h"):
        from core.infrastructure.persistence.models import OhlcvCandle
        return OhlcvCandle(symbol=symbol, interval=interval, open_time=open_time,
                           open=1, high=1, low=1, close=1, volume=1)

    def test_detects_healthy_and_gapped(self, db):
        from core.infrastructure.persistence.models import OhlcvCandle
        now = int(time.time() * 1000)
        # BTC: 10 velas contiguas y frescas → SANO
        btc = [self._candle("BTC", now - _STEP * i) for i in range(10)]
        # ETH: salta la posición 3 → un hueco → CON_HUECOS
        eth = [self._candle("ETH", now - _STEP * i) for i in [0, 1, 2, 4, 5, 6]]
        OhlcvCandle.objects.bulk_create(btc + eth)

        from core.application.use_cases.ohlcv_health import OhlcvHealthUseCase
        out = OhlcvHealthUseCase().execute()
        assert out["status"] == "OK"
        by = {r["symbol"]: r for r in out["series"]}
        assert by["BTC"]["status"] == "SANO"
        assert by["ETH"]["status"] == "CON_HUECOS" and by["ETH"]["missing_candles"] == 1

    def test_empty_store(self, db):
        from core.application.use_cases.ohlcv_health import OhlcvHealthUseCase
        assert OhlcvHealthUseCase().execute()["status"] == "EMPTY"

    def test_endpoint(self, authenticated_client):
        r = authenticated_client.get("/api/data/health/")
        assert r.status_code == 200 and r.data["status"] in ("EMPTY", "OK")
