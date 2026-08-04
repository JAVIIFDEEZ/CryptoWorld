"""
tests/integration/test_chain_metrics_store.py — Almacén histórico on-chain.

El módulo de blockchain no persistía nada: cada panel consultaba en vivo y
mostraba una foto. Tres consecuencias que el usuario sufre:

  · si la fuente falla, el panel queda VACÍO — y una API pública sin clave, con
    ~1 petición/minuto de límite, falla a menudo;
  · no hay tendencias, porque «el gas está a 12 Gwei» no dice nada sin saber a
    cuánto ha estado;
  · no hay gráficas, porque un punto no se dibuja.

Se fija aquí que el almacén exista, que el repliegue diga que es viejo en vez de
disfrazarlo de actual, y que el percentil no se calcule con cuatro lecturas.
"""

import time

import pytest

from core.application.use_cases import chain_metrics_store as store

_MIN = 60_000


def _now():
    return int(time.time() * 1000)


class TestPersistence:

    @pytest.mark.integration
    def test_persist_and_read_back(self, db):
        assert store.persist_metrics("ethereum", {"gas_average": 12.5, "gas_fast": 20.0}) == 2
        assert store.latest("ethereum")["metrics"]["gas_average"] == 12.5

    @pytest.mark.integration
    def test_same_bucket_is_idempotent(self, db):
        """Sin cubos, cada visita de cada usuario crearía una fila y el almacén
        crecería con el TRÁFICO en vez de con el tiempo."""
        ts = _now()
        assert store.persist_metrics("ethereum", {"gas_average": 12.5}, ts_ms=ts) == 1
        assert store.persist_metrics("ethereum", {"gas_average": 13.0}, ts_ms=ts + 1000) == 0

    @pytest.mark.integration
    def test_a_new_bucket_creates_a_new_point(self, db):
        ts = _now()
        store.persist_metrics("ethereum", {"gas_average": 12.5}, ts_ms=ts)
        store.persist_metrics("ethereum", {"gas_average": 13.0},
                              ts_ms=ts + store.BUCKET_MS + 1000)
        assert len(store.load_series("ethereum", "gas_average")) == 2

    @pytest.mark.integration
    def test_non_numeric_values_are_dropped_not_stored_as_zero(self, db):
        """Un `None` o un `NaN` dentro de una tabla de series contamina cualquier
        percentil posterior, y esos huecos son difíciles de rastrear."""
        n = store.persist_metrics("ethereum", {
            "gas_average": 12.5, "block_time_sec": None,
            "chain_id": "ethereum", "flag": True, "bad": float("nan"),
        })
        assert n == 1
        assert set(store.latest("ethereum")["metrics"]) == {"gas_average"}

    @pytest.mark.integration
    def test_chains_do_not_mix(self, db):
        store.persist_metrics("ethereum", {"gas_average": 12.5})
        store.persist_metrics("base", {"gas_average": 0.02})
        assert store.latest("base")["metrics"]["gas_average"] == 0.02


class TestFreshness:

    @pytest.mark.integration
    def test_latest_reports_the_age_of_the_data(self, db):
        """`age_seconds` es lo que convierte el repliegue en honesto: quien lo
        consuma debe poder decir «hace 3 horas» en vez de presentarlo como
        actual."""
        store.persist_metrics("ethereum", {"gas_average": 12.5},
                              ts_ms=_now() - 180 * _MIN)
        snap = store.latest("ethereum")
        assert snap["age_seconds"] >= 175 * 60

    @pytest.mark.integration
    def test_an_empty_store_says_so_instead_of_inventing_a_zero(self, db):
        snap = store.latest("gnosis")
        assert snap["metrics"] == {} and snap["age_seconds"] is None


class TestPercentile:

    @staticmethod
    def _fill(chain, metric, values):
        base = _now() - len(values) * store.BUCKET_MS
        for i, v in enumerate(values):
            store.persist_metrics(chain, {metric: v}, ts_ms=base + i * store.BUCKET_MS)

    @pytest.mark.integration
    def test_percentile_needs_enough_history(self, db):
        """Un percentil sobre seis lecturas es un número con apariencia de rigor
        y nada detrás — peor que no darlo."""
        self._fill("ethereum", "gas_average", [10.0] * 6)
        assert store.percentile_of("ethereum", "gas_average", 10.0) is None

    @pytest.mark.integration
    def test_percentile_places_the_value_in_its_own_history(self, db):
        self._fill("ethereum", "gas_average", [float(i) for i in range(100)])
        low = store.percentile_of("ethereum", "gas_average", 5.0)
        high = store.percentile_of("ethereum", "gas_average", 95.0)
        assert low["percentile"] < 15.0
        assert high["percentile"] > 85.0

    @pytest.mark.integration
    def test_ties_land_in_the_middle_not_at_an_extreme(self, db):
        """Con gas plano —una L2, por ejemplo— contar solo los estrictamente
        menores daría 0 y contarlos todos daría 100 para el MISMO dato."""
        self._fill("base", "gas_average", [0.02] * 60)
        assert store.percentile_of("base", "gas_average", 0.02)["percentile"] == 50.0

    @pytest.mark.integration
    def test_the_percentile_carries_its_sample_size(self, db):
        self._fill("ethereum", "gas_average", [float(i) for i in range(80)])
        out = store.percentile_of("ethereum", "gas_average", 40.0)
        assert out["n_points"] == 80 and out["days"] == 30


class TestCoverage:

    @pytest.mark.integration
    def test_no_history_is_stated_loudly(self, db):
        out = store.coverage("optimism")
        assert out["points"] == 0
        assert "dependen por completo" in out["note"]

    @pytest.mark.integration
    def test_coverage_reports_span_and_metrics(self, db):
        base = _now() - 10 * store.BUCKET_MS
        for i in range(10):
            store.persist_metrics("ethereum", {"gas_average": 10.0 + i, "gas_fast": 20.0},
                                  ts_ms=base + i * store.BUCKET_MS)
        out = store.coverage("ethereum")
        assert out["points"] == 20 and out["metrics"] == 2


class TestPrune:

    @pytest.mark.integration
    def test_old_points_are_removed_and_recent_ones_kept(self, db):
        store.persist_metrics("ethereum", {"gas_average": 1.0},
                              ts_ms=_now() - 500 * 86_400_000)
        store.persist_metrics("ethereum", {"gas_average": 2.0})
        assert store.prune(older_than_days=400) == 1
        assert store.latest("ethereum")["metrics"]["gas_average"] == 2.0


class TestChainHealthFallback:
    """El comportamiento que el usuario nota: el panel deja de quedarse vacío."""

    class _DeadClient:
        def get_chain_stats(self, chain):
            from core.infrastructure.external_apis.blockscout_client import BlockscoutClientError
            raise BlockscoutClientError("la fuente no responde")

    class _LiveClient:
        def __init__(self, gas):
            self._gas = gas

        def get_chain_stats(self, chain):
            return {"gas_prices": {"slow": self._gas - 2, "average": self._gas,
                                   "fast": self._gas + 4},
                    "network_utilization_percentage": 55.0,
                    "average_block_time": 12000, "coin_price": 3000.0,
                    "transactions_today": 1_200_000}

    @pytest.mark.integration
    def test_a_live_read_fills_the_store(self, db):
        from core.application.use_cases.get_chain_health import GetChainHealthUseCase

        GetChainHealthUseCase(client=self._LiveClient(15.0)).execute("ethereum")
        assert store.latest("ethereum")["metrics"]["gas_average"] == 15.0

    @pytest.mark.integration
    def test_a_dead_source_falls_back_to_the_store_instead_of_an_empty_panel(self, db):
        from core.application.use_cases.get_chain_health import GetChainHealthUseCase

        GetChainHealthUseCase(client=self._LiveClient(15.0)).execute("ethereum")
        out = GetChainHealthUseCase(client=self._DeadClient()).execute("ethereum")

        assert "error" not in out
        assert out["gas_average"] == 15.0
        assert out["source"] == "store"

    @pytest.mark.integration
    def test_the_fallback_never_passes_off_old_data_as_current(self, db):
        """Mostrar un dato de hace tres horas como si fuera de ahora sería PEOR
        que no mostrar nada."""
        from core.application.use_cases.get_chain_health import GetChainHealthUseCase

        GetChainHealthUseCase(client=self._LiveClient(15.0)).execute("ethereum")
        out = GetChainHealthUseCase(client=self._DeadClient()).execute("ethereum")

        assert out["stale"] is True
        assert out["data_age_seconds"] is not None
        assert "antigüedad" in out["note"]

    @pytest.mark.integration
    def test_with_no_store_and_no_source_it_still_reports_the_error(self, db):
        from core.application.use_cases.get_chain_health import GetChainHealthUseCase

        out = GetChainHealthUseCase(client=self._DeadClient()).execute("arbitrum")
        assert "error" in out

    @pytest.mark.integration
    def test_a_live_read_is_marked_as_not_stale(self, db):
        from core.application.use_cases.get_chain_health import GetChainHealthUseCase

        out = GetChainHealthUseCase(client=self._LiveClient(15.0)).execute("ethereum")
        assert out["stale"] is False

    @pytest.mark.integration
    def test_gas_verdict_uses_history_once_there_is_enough_of_it(self, db):
        """Un umbral fijo de 10 Gwei es una constante arbitraria que envejece con
        el mercado; el percentil sobre la propia serie se autocalibra."""
        from core.application.use_cases.get_chain_health import GetChainHealthUseCase

        base = _now() - 80 * store.BUCKET_MS
        for i in range(80):
            store.persist_metrics("ethereum", {"gas_average": 40.0 + i},
                                  ts_ms=base + i * store.BUCKET_MS)

        out = GetChainHealthUseCase(client=self._LiveClient(41.0)).execute("ethereum")
        # 41 Gwei superaría el umbral fijo de 30 → «caro». Contra su propia
        # historia (40–119) está abajo del todo → barato.
        assert out["gas_basis"] == "history"
        assert out["gas_level"] == "cheap"

    @pytest.mark.integration
    def test_without_history_it_falls_back_to_fixed_thresholds_and_says_so(self, db):
        from core.application.use_cases.get_chain_health import GetChainHealthUseCase

        out = GetChainHealthUseCase(client=self._LiveClient(50.0)).execute("ethereum")
        assert out["gas_basis"] == "fixed"
        assert out["gas_level"] == "high"
