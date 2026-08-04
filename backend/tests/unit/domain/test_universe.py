"""
test_universe.py — Universo point-in-time y sesgo de supervivencia.

El error que corrige este módulo tiene una propiedad que lo hace peor que el
ruido: **siempre va en la misma dirección**. Los activos que desaparecen son
sistemáticamente los peores, así que reconstruir el pasado con la lista de hoy
infla el rendimiento de cualquier estrategia, y lo infla más cuanto más largo
sea el histórico.

Lo que se fija aquí es que el módulo no pueda dar una falsa sensación de rigor:
si las fechas no están, hay que decirlo, porque un universo point-in-time sin
fechas de alta ni bajas es exactamente la lista de supervivientes con otro
nombre.
"""

from datetime import datetime, timezone

import pytest

from core.domain.services import universe


def dt(year, month=1, day=1):
    return datetime(year, month, day, tzinfo=timezone.utc)


ASSETS = [
    universe.AssetLifecycle("BTC", listed_at=dt(2013)),
    universe.AssetLifecycle("ETH", listed_at=dt(2015)),
    universe.AssetLifecycle("LUNA", listed_at=dt(2019), delisted_at=dt(2022, 5),
                            delisting_reason="dead"),
    universe.AssetLifecycle("FTT", listed_at=dt(2019), delisted_at=dt(2022, 11),
                            delisting_reason="delisted"),
    universe.AssetLifecycle("NEWCOIN", listed_at=dt(2025)),
]


class TestPointInTime:

    @pytest.mark.unit
    def test_includes_the_dead_while_they_were_alive(self):
        """El punto entero del módulo: en 2021 LUNA y FTT cotizaban, y omitirlas
        es exactamente el sesgo que se quiere evitar."""
        members = universe.point_in_time_universe(ASSETS, dt(2021, 6))
        assert "LUNA" in members and "FTT" in members

    @pytest.mark.unit
    def test_excludes_what_had_not_listed_yet(self):
        """El problema inverso, menos comentado: meter en 2021 un activo que
        nació en 2025 le atribuye a esa época un rendimiento que no existía."""
        assert "NEWCOIN" not in universe.point_in_time_universe(ASSETS, dt(2021, 6))

    @pytest.mark.unit
    def test_excludes_what_had_already_died(self):
        assert "LUNA" not in universe.point_in_time_universe(ASSETS, dt(2023, 1))

    @pytest.mark.unit
    def test_unknown_listing_date_does_not_silently_exclude(self):
        """Inventar una fecha de alta excluiría datos reales, y ese error sí
        sería silencioso. La incertidumbre se reporta en `coverage`."""
        unknown = [universe.AssetLifecycle("MYSTERY")]
        assert universe.point_in_time_universe(unknown, dt(2014)) == ["MYSTERY"]

    @pytest.mark.unit
    def test_delisting_day_is_exclusive(self):
        """El día de la baja ya no se puede operar. Un intervalo semiabierto
        evita contar dos veces el activo en la frontera."""
        assert "LUNA" not in universe.point_in_time_universe(ASSETS, dt(2022, 5))


class TestCoverage:

    @pytest.mark.unit
    def test_full_coverage_is_declared_reliable(self):
        assert universe.coverage(ASSETS)["reliable"] is True

    @pytest.mark.unit
    def test_a_universe_without_dates_is_not_dressed_up_as_rigorous(self):
        """Sin fechas, el universo point-in-time coincide con la lista de
        supervivientes. Presentarlo como corrección sería peor que no tenerlo."""
        naive = [universe.AssetLifecycle(s) for s in ("BTC", "ETH", "SOL")]
        out = universe.coverage(naive)
        assert out["reliable"] is False
        assert "NO corrige" in out["note"]

    @pytest.mark.unit
    def test_a_universe_with_no_deaths_is_suspicious(self):
        """Cero bajas en cripto no es un universo limpio: es un universo al que
        nadie le ha registrado las muertes."""
        alive = [universe.AssetLifecycle(s, listed_at=dt(2018))
                 for s in ("BTC", "ETH", "SOL")]
        assert universe.coverage(alive)["reliable"] is False

    @pytest.mark.unit
    def test_empty_universe_is_handled(self):
        assert universe.coverage([])["n_assets"] == 0


class TestSurvivorshipReport:

    @pytest.mark.unit
    def test_quantifies_what_a_naive_backtest_would_omit(self):
        out = universe.survivorship_report(ASSETS, dt(2021, 6), now=dt(2026))
        assert out["n_then"] == 4          # BTC, ETH, LUNA, FTT
        assert out["n_disappeared"] == 2   # LUNA, FTT
        assert out["missing_pct"] == 50.0

    @pytest.mark.unit
    def test_breaks_down_the_reasons(self):
        out = universe.survivorship_report(ASSETS, dt(2021, 6), now=dt(2026))
        assert out["reasons"] == {"dead": 1, "delisted": 1}

    @pytest.mark.unit
    def test_counts_phantoms_that_a_static_universe_would_add(self):
        """NEWCOIN existe hoy pero no en 2021: un universo estático la mete en
        una época a la que no pertenece."""
        out = universe.survivorship_report(ASSETS, dt(2021, 6), now=dt(2026))
        assert out["phantom_pct"] == pytest.approx(25.0)

    @pytest.mark.unit
    def test_the_direction_of_the_bias_is_stated_not_left_to_the_reader(self):
        out = universe.survivorship_report(ASSETS, dt(2021, 6), now=dt(2026))
        assert "favorece a la estrategia" in out["note"]

    @pytest.mark.unit
    def test_a_date_before_anything_listed_is_reported_not_crashed(self):
        assert universe.survivorship_report(ASSETS, dt(2010), now=dt(2026))["n_then"] == 0


class TestAdapter:

    @pytest.mark.unit
    def test_reads_orm_rows_and_dicts_alike(self):
        rows = [{"symbol": "BTC", "listed_at": dt(2013), "delisted_at": None,
                 "delisting_reason": None}]
        assert universe.from_records(rows)[0].symbol == "BTC"

    @pytest.mark.unit
    def test_missing_lifecycle_attributes_do_not_crash_the_adapter(self):
        class Row:
            symbol = "ETH"
        assert universe.from_records([Row()])[0].listed_at is None
