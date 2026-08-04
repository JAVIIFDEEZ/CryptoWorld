"""
tests/integration/test_multichain_history.py — Blockchair con memoria.

El plan gratuito de Blockchair NO devuelve series históricas: las peticiones de
agregación responden HTTP 430. Así que este caso de uso solo podía dar una foto,
y una foto de «dificultad: 1,2e14» es un número ilegible — sin saber de dónde
viene no dice absolutamente nada.

Con el almacén propio aparecen las dos cosas que faltaban:

  · **Variación** frente a 24 h y 7 días. «Hashrate +12 % en 7 días» sí es
    interpretable.
  · **Repliegue** cuando la fuente cae, en vez de `stats: []` y panel en blanco.

Y una distinción que hay que sostener: «sin histórico suficiente» no es «no ha
cambiado». Lo primero es `None`; lo segundo, 0.
"""

import time

import pytest

from core.application.use_cases import chain_metrics_store as store
from core.application.use_cases.get_multichain_stats import GetMultiChainStatsUseCase

_DAY_MS = 86_400_000


def _now():
    return int(time.time() * 1000)


class _Client:
    """Blockchair simulado: devuelve los campos crudos que espera el caso de uso."""

    def __init__(self, difficulty=1.0e14, hashrate=6.0e20, price=60000.0):
        self._raw = {
            "transactions_24h": 400_000, "blocks_24h": 144,
            "difficulty": difficulty, "hashrate_24h": hashrate,
            "mempool_transactions": 12_000, "mempool_size": 8_000_000,
            "average_transaction_fee_usd_24h": 2.5,
            "median_transaction_fee_usd_24h": 1.1,
            "market_price_usd": price, "market_cap_usd": 1.2e12,
            "market_dominance_percentage": 54.0,
            "best_block_time": "2026-08-04 12:00:00", "best_block_height": 900_000,
        }

    def get_stats(self, symbol):
        return dict(self._raw)


class _DeadClient:
    def get_stats(self, symbol):
        from core.infrastructure.external_apis.blockchair_client import BlockchairClientError
        raise BlockchairClientError("Blockchair no responde")


def _stat(result, key):
    return next(s for s in result["stats"] if s["key"] == key)


class TestPersistence:

    @pytest.mark.integration
    def test_a_read_fills_the_store(self, db):
        GetMultiChainStatsUseCase(client=_Client()).execute("BTC")
        assert store.latest("bc:btc")["metrics"]["difficulty"] == 1.0e14

    @pytest.mark.integration
    def test_blockchair_series_do_not_mix_with_blockscout(self, db):
        """`ethereum` (gas, Blockscout) y `bc:eth` (dificultad, Blockchair) son
        fuentes distintas de la misma red. Mezclarlas daría percentiles
        calculados sobre dos poblaciones diferentes."""
        store.persist_metrics("ethereum", {"gas_average": 12.0})
        GetMultiChainStatsUseCase(client=_Client()).execute("ETH")
        assert "gas_average" not in store.latest("bc:eth")["metrics"]
        assert "difficulty" not in store.latest("ethereum")["metrics"]

    @pytest.mark.integration
    def test_converted_values_are_stored_not_raw_ones(self, db):
        """El hashrate se presenta en TH/s; guardar los H/s crudos haría que la
        serie y la pantalla hablaran de unidades distintas."""
        GetMultiChainStatsUseCase(client=_Client(hashrate=6.0e20)).execute("BTC")
        assert store.latest("bc:btc")["metrics"]["hashrate_24h"] == pytest.approx(6.0e8)


class TestChange:

    @pytest.mark.integration
    def test_without_history_the_change_is_none_not_zero(self, db):
        """«Sin dato» y «no ha cambiado» son afirmaciones distintas, y un 0
        afirmaría la segunda."""
        out = GetMultiChainStatsUseCase(client=_Client()).execute("BTC")
        assert _stat(out, "difficulty")["change_7d_pct"] is None

    @pytest.mark.integration
    def test_change_is_measured_against_the_oldest_point_in_the_window(self, db):
        """La pregunta es «cuánto ha cambiado desde entonces»; una media
        respondería a otra distinta."""
        store.persist_metrics("bc:btc", {"difficulty": 1.0e14},
                              source="blockchair", ts_ms=_now() - 8 * _DAY_MS)
        store.persist_metrics("bc:btc", {"difficulty": 1.05e14},
                              source="blockchair", ts_ms=_now() - 4 * _DAY_MS)

        out = GetMultiChainStatsUseCase(client=_Client(difficulty=1.2e14)).execute("BTC")
        # +20 % respecto al más antiguo de la ventana de 7 días… que es el de
        # hace 4 días, porque el de hace 8 cae fuera.
        assert _stat(out, "difficulty")["change_7d_pct"] == pytest.approx(14.29, abs=0.1)

    @pytest.mark.integration
    def test_a_window_without_enough_span_reports_nothing(self, db):
        """Comparar contra hace dos horas y llamarlo «7 días» sería mentir sobre
        lo que se mide."""
        store.persist_metrics("bc:btc", {"difficulty": 1.0e14},
                              source="blockchair", ts_ms=_now() - 7_200_000)
        out = GetMultiChainStatsUseCase(client=_Client(difficulty=1.2e14)).execute("BTC")
        assert _stat(out, "difficulty")["change_7d_pct"] is None

    @pytest.mark.integration
    def test_a_drop_is_reported_negative(self, db):
        store.persist_metrics("bc:btc", {"market_price_usd": 100_000.0},
                              source="blockchair", ts_ms=_now() - 6 * _DAY_MS)
        out = GetMultiChainStatsUseCase(client=_Client(price=50_000.0)).execute("BTC")
        assert _stat(out, "market_price_usd")["change_7d_pct"] == pytest.approx(-50.0, abs=0.1)


class TestFallback:

    @pytest.mark.integration
    def test_a_dead_source_no_longer_empties_the_panel(self, db):
        GetMultiChainStatsUseCase(client=_Client()).execute("BTC")
        out = GetMultiChainStatsUseCase(client=_DeadClient()).execute("BTC")

        assert "error" not in out
        assert out["stats"], "el panel se quedaría vacío, que es lo que se venía a arreglar"
        assert _stat(out, "difficulty")["value"] == 1.0e14

    @pytest.mark.integration
    def test_the_fallback_declares_itself_stale(self, db):
        GetMultiChainStatsUseCase(client=_Client()).execute("BTC")
        out = GetMultiChainStatsUseCase(client=_DeadClient()).execute("BTC")

        assert out["stale"] is True
        assert out["source"] == "store"
        assert out["data_age_seconds"] is not None

    @pytest.mark.integration
    def test_the_fallback_keeps_the_display_units(self, db):
        GetMultiChainStatsUseCase(client=_Client()).execute("BTC")
        out = GetMultiChainStatsUseCase(client=_DeadClient()).execute("BTC")
        assert _stat(out, "hashrate_24h")["unit"] == "TH/s"

    @pytest.mark.integration
    def test_with_neither_source_nor_store_the_error_still_surfaces(self, db):
        out = GetMultiChainStatsUseCase(client=_DeadClient()).execute("LTC")
        assert "error" in out and out["stats"] == []

    @pytest.mark.integration
    def test_a_live_read_is_not_marked_stale(self, db):
        out = GetMultiChainStatsUseCase(client=_Client()).execute("BTC")
        assert out["stale"] is False


class TestHistoryEndpoint:

    @pytest.mark.integration
    def test_the_endpoint_serves_blockchair_series_too(self, db, authenticated_client):
        """El endpoint valida contra lo que el almacén TIENE, no contra una lista
        fija: si no, las cadenas de Blockchair quedarían fuera y habría que
        mantener dos catálogos que se desincronizarían."""
        base = _now() - 20 * store.BUCKET_MS
        for i in range(20):
            store.persist_metrics("bc:btc", {"difficulty": 1.0e14 + i},
                                  source="blockchair", ts_ms=base + i * store.BUCKET_MS)

        res = authenticated_client.get("/api/blockchain/history/?chain=bc:btc&metric=difficulty&days=7")
        assert res.status_code == 200
        assert len(res.json()["points"]) == 20

    @pytest.mark.integration
    def test_an_unknown_metric_lists_what_is_available(self, db, authenticated_client):
        store.persist_metrics("bc:btc", {"difficulty": 1.0e14}, source="blockchair")
        res = authenticated_client.get("/api/blockchain/history/?chain=bc:btc&metric=inventada")
        assert res.status_code == 400
        assert "difficulty" in res.json()["available"]
