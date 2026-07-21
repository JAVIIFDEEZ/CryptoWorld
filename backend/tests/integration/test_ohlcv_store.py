"""
tests/integration/test_ohlcv_store.py — Almacén histórico OHLCV propio.

Verifica: solo se persisten velas cerradas (idempotente), la carga devuelve el
mismo esquema que el fetcher, la detección de huecos, la regla de frescura, la
integración con el fetcher (servir de BD en peticiones históricas y acumular
oportunistamente lo remoto) y el backfill paginado hacia atrás.
"""

import time

import numpy as np
import pandas as pd
import pytest

from core.application.use_cases import ohlcv_store as store

_H = 3_600_000  # 1h en ms


def _now_ms() -> int:
    return int(time.time() * 1000)


def _df(n: int, start_ms: int, step: int = _H) -> pd.DataFrame:
    ts = np.arange(start_ms, start_ms + n * step, step, dtype=np.int64)
    price = 100.0 + np.arange(n)
    return pd.DataFrame({
        "timestamp": ts, "open": price, "high": price + 1, "low": price - 1,
        "close": price + 0.5, "volume": np.full(n, 10.0),
    })


class TestPersistAndLoad:

    @pytest.mark.integration
    def test_only_closed_candles_and_idempotent(self, db):
        # 5 velas: las 4 primeras ya cerraron; la 5ª (abre en `now`) está en curso
        now = _now_ms()
        df = _df(5, now - 4 * _H)
        created = store.persist_candles("BTC", "1h", df, source="binance")
        assert created == 4          # la vela en curso no se guarda
        assert store.persist_candles("BTC", "1h", df, source="binance") == 0  # idempotente

    @pytest.mark.integration
    def test_load_matches_fetcher_schema_ascending(self, db):
        now = _now_ms()
        store.persist_candles("ETH", "1h", _df(10, now - 12 * _H), source="binance")
        out = store.load_dataframe("ETH", "1h", limit=5)
        assert list(out.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
        assert len(out) == 5
        assert out["timestamp"].is_monotonic_increasing


class TestGapsAndFreshness:

    @pytest.mark.integration
    def test_find_gaps_detects_hole(self, db):
        now = _now_ms()
        df = _df(10, now - 20 * _H)
        df = df[df.index != 4]       # quitar una vela del medio → hueco de 1
        store.persist_candles("SOL", "1h", df, source="binance")
        gaps = store.find_gaps("SOL", "1h")
        assert gaps["gaps"] == 1 and gaps["missing_candles"] == 1
        cov = store.coverage("SOL", "1h")
        assert cov["candles"] == 9 and cov["gaps"] == 1

    @pytest.mark.integration
    def test_freshness_requires_all_closed_candles(self, db):
        now = _now_ms()
        store.persist_candles("ADA", "1h", _df(52, now - 52 * _H), source="binance")
        assert store.store_is_fresh("ADA", "1h", limit=40) is True
        assert store.store_is_fresh("ADA", "1h", limit=100) is False  # no hay tantas
        # Histórico viejo (última vela hace 10h) → no fresco
        store.persist_candles("DOT", "1h", _df(50, now - 62 * _H), source="binance")
        assert store.store_is_fresh("DOT", "1h", limit=40) is False


class TestFetcherIntegration:

    @pytest.mark.integration
    def test_historical_request_served_from_store_without_network(self, db):
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe

        now = _now_ms()
        store.persist_candles("BTC", "1h", _df(402, now - 402 * _H), source="binance")

        class _Boom:  # si toca la red, el test falla
            def get_klines(self, *a, **kw):
                raise AssertionError("no debería llamar a Binance")
        res = fetch_ohlcv_dataframe(symbol="BTC", interval="1h", limit=350,
                                    binance_client=_Boom(), kucoin_client=_Boom())
        assert res is not None and res.source == "store"
        assert len(res.df) == 350

    @pytest.mark.integration
    def test_live_request_stays_remote_and_persists(self, db):
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.infrastructure.persistence.models import OhlcvCandle

        now = _now_ms()
        raw_df = _df(60, now - 61 * _H)

        class _FakeBinance:
            def get_klines(self, symbol, interval, limit=500, end_time_ms=None):
                return [[int(r.timestamp), str(r.open), str(r.high), str(r.low),
                         str(r.close), str(r.volume), 0, "0", 0, "0", "0", "0"]
                        for r in raw_df.itertuples(index=False)]
        res = fetch_ohlcv_dataframe(symbol="LTC", interval="1h", limit=60,
                                    binance_client=_FakeBinance())
        assert res is not None and res.source == "binance"   # en vivo: remoto
        # …pero el almacén acumuló las velas cerradas oportunistamente
        assert OhlcvCandle.objects.filter(symbol="LTC", interval="1h").count() >= 59


class TestBackfill:

    @pytest.mark.integration
    def test_backfill_pages_backwards_until_exhausted(self, db):
        now_aligned = (_now_ms() // _H) * _H

        class _FakeBinance:
            """2 páginas de histórico de 100 velas; antes de eso, nada."""
            def __init__(self):
                self.calls = []
            def get_klines(self, symbol, interval, limit=1000, end_time_ms=None):
                self.calls.append(end_time_ms)
                end = end_time_ms if end_time_ms is not None else now_aligned - _H
                start = end - (100 - 1) * _H
                floor = now_aligned - 200 * _H          # histórico total: 200 velas
                if end < floor:
                    return []
                df = _df(100, max(start, floor))
                return [[int(r.timestamp), str(r.open), str(r.high), str(r.low),
                         str(r.close), str(r.volume), 0, "0", 0, "0", "0", "0"]
                        for r in df.itertuples(index=False) if r.timestamp <= end]

        fake = _FakeBinance()
        uc = store.BackfillOhlcvUseCase(binance_client=fake)
        out = uc.execute("XRP", "1h", target_candles=500, max_pages=6, page_pause_s=0)
        assert out["exhausted"] is True
        assert out["candles"] >= 190                    # ~200 velas menos la en curso
        assert fake.calls[0] is None                    # 1ª página: desde ahora
        assert all(c is not None for c in fake.calls[1:])  # después: hacia atrás
        gaps = store.find_gaps("XRP", "1h")
        assert gaps["missing_candles"] == 0             # sin huecos entre páginas
