"""
tests/integration/test_funding_store.py — Almacén histórico de financiación y
ciclo de vida del universo.

Estas dos piezas cierran la última omisión sistemática del motor: un backtest
de perpetuos que no cobra funding, y un universo que solo contiene a los que
sobrevivieron. Ambos errores comparten la propiedad que los hace peligrosos —
van siempre en la misma dirección, hacia arriba.

Se verifica: ingesta idempotente, imputación del coste a las velas correctas,
la distinción entre «funding cero» y «no hay dato», y que la sincronización de
altas/bajas no invente delistings de activos que nunca tuvieron perpetuo.
"""

import numpy as np
import pandas as pd
import pytest

from core.application.use_cases import funding_store as store

_DAY = 86_400_000
_H8 = 8 * 3_600_000


def _rows(n: int, start_ms: int, rate: float = 0.0001):
    return [{"fundingTime": start_ms + i * _H8, "fundingRate": str(rate),
             "markPrice": "30000.0"} for i in range(n)]


def _ohlcv(n: int, start_ms: int, step: int = _DAY) -> pd.DataFrame:
    ts = np.arange(start_ms, start_ms + n * step, step, dtype=np.int64)
    price = 100.0 + np.arange(n)
    return pd.DataFrame({
        "timestamp": ts, "open": price, "high": price + 1, "low": price - 1,
        "close": price + 0.5, "volume": np.full(n, 10.0),
    })


class TestIngestion:

    @pytest.mark.integration
    def test_persist_is_idempotent(self, db):
        rows = _rows(30, 1_700_000_000_000)
        assert store.persist_funding("BTC", rows) == 30
        assert store.persist_funding("BTC", rows) == 0

    @pytest.mark.integration
    def test_symbol_is_normalised_to_the_perpetual_pair(self, db):
        store.persist_funding("ETH", _rows(3, 1_700_000_000_000))
        assert store.load_funding("ETHUSDT")
        assert store.load_funding("ETH") == store.load_funding("ETHUSDT")

    @pytest.mark.integration
    def test_a_malformed_row_does_not_become_a_zero_funding(self, db):
        """Descartar la fila mala es correcto; colarla como cero afirmaría que
        ese periodo no costó nada, que es una afirmación distinta."""
        rows = _rows(3, 1_700_000_000_000) + [{"fundingTime": None, "fundingRate": "x"}]
        assert store.persist_funding("SOL", rows) == 3

    @pytest.mark.integration
    def test_load_respects_the_requested_range(self, db):
        start = 1_700_000_000_000
        store.persist_funding("ADA", _rows(30, start))
        subset = store.load_funding("ADA", start_ms=start + 5 * _H8,
                                    end_ms=start + 9 * _H8)
        assert len(subset) == 5


class TestAttachToCandles:

    @pytest.mark.integration
    def test_three_settlements_land_in_one_daily_candle(self, db):
        start = 1_700_000_000_000
        store.persist_funding("BTC", _rows(9, start))
        out = store.attach_funding(_ohlcv(3, start), "BTC", "1d")
        assert "funding_rate" in out.columns
        # 3 liquidaciones de 1 bp por vela diaria.
        assert out["funding_rate"].iloc[0] == pytest.approx(0.0003)

    @pytest.mark.integration
    def test_no_history_means_no_column_not_a_column_of_zeros(self, db):
        """Una columna de ceros AFIRMA que el funding fue nulo. Lo que ocurre en
        realidad es que no se sabe, y el backtest debe poder distinguirlo."""
        out = store.attach_funding(_ohlcv(3, 1_700_000_000_000), "DOGE", "1d")
        assert "funding_rate" not in out.columns

    @pytest.mark.integration
    def test_the_engine_charges_the_attached_column(self, db):
        """Comprobación de extremo a extremo: la misma estrategia sobre el mismo
        tramo rinde menos con el funding adjunto. Si saliera igual, el coste no
        se estaría aplicando de verdad."""
        from core.domain.services.technical_analysis_service import backtest_signals

        start = 1_700_000_000_000
        store.persist_funding("BTC", _rows(90, start, rate=0.001))
        df = _ohlcv(30, start)
        signals = np.zeros(30, dtype=int)
        signals[0] = 1

        free = backtest_signals(df, signals)
        charged = backtest_signals(store.attach_funding(df, "BTC", "1d"), signals)

        assert charged["total_funding_pct"] > 0
        assert charged["total_return_pct"] < free["total_return_pct"]


class TestCoverage:

    @pytest.mark.integration
    def test_absence_of_history_is_stated_loudly(self, db):
        out = store.coverage("XRP")
        assert out["settlements"] == 0
        assert "NO incluyen su coste" in out["note"]

    @pytest.mark.integration
    def test_describes_the_regime_when_there_is_history(self, db):
        store.persist_funding("BTC", _rows(30, 1_700_000_000_000, rate=0.0002))
        out = store.coverage("BTC")
        assert out["settlements"] == 30
        assert out["pct_paid_by_longs"] == 100.0
        assert out["annualized_cost_bps"] > 0


class TestLifecycleSync:

    class _Client:
        def __init__(self, symbols):
            self._symbols = symbols

        def futures_exchange_info(self):
            return {"symbols": self._symbols}

    @pytest.mark.integration
    def test_fills_the_listing_date_from_the_catalogue(self, db):
        from core.infrastructure.persistence.models import CryptoAsset

        CryptoAsset.objects.create(symbol="BTC", name="Bitcoin")
        client = self._Client([
            {"baseAsset": "BTC", "onboardDate": 1_569_398_400_000, "status": "TRADING"},
        ])
        out = store.SyncAssetLifecycleUseCase(binance_client=client).execute()

        assert out["updated"] == 1
        assert CryptoAsset.objects.get(symbol="BTC").listed_at is not None

    @pytest.mark.integration
    def test_a_symbol_that_left_the_catalogue_is_marked_delisted(self, db):
        from core.infrastructure.persistence.models import CryptoAsset

        CryptoAsset.objects.create(symbol="LUNA", name="Terra")
        client = self._Client([
            {"baseAsset": "LUNA", "onboardDate": 1_600_000_000_000, "status": "BREAK"},
        ])
        out = store.SyncAssetLifecycleUseCase(binance_client=client).execute()

        asset = CryptoAsset.objects.get(symbol="LUNA")
        assert out["newly_delisted"] == 1
        assert asset.delisted_at is not None
        assert asset.is_active is False

    @pytest.mark.integration
    def test_an_asset_that_never_had_a_perpetual_is_not_delisted(self, db):
        """Ausencia del catálogo de futuros no es una baja: hay activos que
        simplemente no cotizan en ese mercado. Marcarlos borraría histórico
        válido de spot."""
        from core.infrastructure.persistence.models import CryptoAsset

        CryptoAsset.objects.create(symbol="OBSCURE", name="Obscure Token")
        client = self._Client([
            {"baseAsset": "BTC", "onboardDate": 1_569_398_400_000, "status": "TRADING"},
        ])
        store.SyncAssetLifecycleUseCase(binance_client=client).execute()

        assert CryptoAsset.objects.get(symbol="OBSCURE").delisted_at is None

    @pytest.mark.integration
    def test_an_already_recorded_delisting_is_not_overwritten(self, db):
        """La fecha real de baja, si alguna vez se conoce, vale más que la de
        detección. Re-sincronizar no debe pisarla."""
        from django.utils import timezone
        from core.infrastructure.persistence.models import CryptoAsset

        original = timezone.now() - timezone.timedelta(days=400)
        CryptoAsset.objects.create(symbol="FTT", name="FTX Token",
                                   delisted_at=original, delisting_reason="dead")
        client = self._Client([
            {"baseAsset": "FTT", "onboardDate": 1_600_000_000_000, "status": "BREAK"},
        ])
        store.SyncAssetLifecycleUseCase(binance_client=client).execute()

        asset = CryptoAsset.objects.get(symbol="FTT")
        assert asset.delisted_at == original
        assert asset.delisting_reason == "dead"

    @pytest.mark.integration
    def test_the_report_admits_the_date_is_detection_not_reality(self, db):
        from core.infrastructure.persistence.models import CryptoAsset

        CryptoAsset.objects.create(symbol="BTC", name="Bitcoin")
        client = self._Client([{"baseAsset": "BTC", "onboardDate": 1_569_398_400_000,
                                "status": "TRADING"}])
        out = store.SyncAssetLifecycleUseCase(binance_client=client).execute()
        assert "DETECCIÓN" in out["note"]
