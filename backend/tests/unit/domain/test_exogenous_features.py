"""
test_exogenous_features.py — La fuga más fácil de cometer y la más difícil de ver.

Alinear una variable exógena a una rejilla de velas parece un problema de
fontanería y es donde se pierde un estudio entero. Un `fillna(method="bfill")`
puesto por comodidad, una media centrada en vez de rezagada, o un `<` donde
debía ir `<=`: cualquiera de las tres mete en la fila `t` información que no
existía al cerrar esa vela, y el modelo sale brillante y no se puede operar.

Nada de eso levanta una excepción. Por eso el test central de este fichero no
comprueba un valor concreto sino una PROPIEDAD: recalcular con los datos
truncados en `k` tiene que dar exactamente lo mismo que calcular con todo y
recortar. Un forward-fill desde el futuro rompe esa igualdad de inmediato.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import exogenous_features as ex

H = 3_600_000


def _bars(n=200, step=H):
    return np.arange(0, n * step, step, dtype=np.int64)


def _funding(n=40, start=0, every=8 * H):
    rng = np.random.default_rng(3)
    return [(start + i * every, float(rng.normal(0.0001, 0.00005))) for i in range(n)]


class TestAsOf:
    """El join que decide si hay fuga o no."""

    @pytest.mark.unit
    def test_before_the_first_event_there_is_no_value(self):
        """Cero sería mentira: no es que la variable valiera cero, es que no se
        estaba observando."""
        out = ex.as_of([100, 200], [150], [1.0], 10**9)
        assert np.isnan(out[0]) and out[1] == 1.0

    @pytest.mark.unit
    def test_an_event_exactly_at_the_close_counts_as_known(self):
        """La frontera es donde vive la fuga. Con `<` se perdería el dato
        publicado justo al cierre —el caso más frecuente cuando las dos series
        comparten rejilla—; con `>=` se leería el futuro."""
        assert ex.as_of([100], [100], [7.0], 10**9)[0] == 7.0

    @pytest.mark.unit
    def test_it_never_takes_a_later_event(self):
        out = ex.as_of([100, 200, 300], [150, 250, 350], [1.0, 2.0, 3.0], 10**9)
        assert np.isnan(out[0])
        assert out[1] == 1.0 and out[2] == 2.0

    @pytest.mark.unit
    def test_a_stale_value_expires_instead_of_propagating_forever(self):
        """Propagar sin límite es técnicamente point-in-time e informativamente
        basura: un funding de hace cuarenta días no describe el mercado de hoy.
        Recorta muestras, y esa es la decisión."""
        out = ex.as_of([100, 100_000], [100], [5.0], max_staleness_ms=1000)
        assert out[0] == 5.0 and np.isnan(out[1])

    @pytest.mark.unit
    def test_unsorted_events_are_handled(self):
        """Los registros vienen de la base de datos y el orden no está
        garantizado por contrato."""
        out = ex.as_of([300], [250, 100, 200], [2.0, 0.0, 1.0], 10**9)
        assert out[0] == 2.0

    @pytest.mark.unit
    def test_no_events_gives_all_nan_not_zeros(self):
        assert np.isnan(ex.as_of([1, 2, 3], [], [], 10**9)).all()


class TestCausality:
    """
    La propiedad de la que depende que este módulo sirva para algo.

    Si calcular con el histórico truncado en `k` no diera lo mismo que calcular
    con todo y recortar, alguna fila estaría mirando hacia delante.
    """

    @pytest.mark.unit
    def test_the_assembled_frame_is_prefix_stable(self):
        bars = _bars(300)
        funding = _funding(60)
        whale = [(i * 7 * H, float((-1) ** i) * 1e6 * (i + 1)) for i in range(40)]
        chain = [(i * 4 * H, 10.0 + i) for i in range(70)]

        full = ex.assemble(bars, funding=funding, whale=whale, chain=chain)
        for k in (60, 150, 240):
            # Truncar TAMBIÉN los eventos: en el instante de la vela k no se
            # conocían los posteriores, y dejarlos sería regalarle al prefijo un
            # dato que en su momento no existía.
            cut = bars[k - 1]
            prefix = ex.assemble(
                bars[:k],
                funding=[f for f in funding if f[0] <= cut],
                whale=[w for w in whale if w[0] <= cut],
                chain=[c for c in chain if c[0] <= cut],
            )
            for col in full.columns:
                a = full[col].to_numpy()[:k]
                b = prefix[col].to_numpy()
                both_nan = np.isnan(a) & np.isnan(b)
                assert (np.isclose(a, b, rtol=1e-9, atol=1e-12) | both_nan).all(), col

    @pytest.mark.unit
    def test_a_future_event_cannot_change_a_past_row(self):
        """La versión directa del mismo control: añadir un movimiento enorme al
        final no puede alterar ni una fila anterior."""
        bars = _bars(100)
        base = ex.assemble(bars, whale=[(10 * H, 1e6)])
        with_future = ex.assemble(bars, whale=[(10 * H, 1e6), (99 * H, 9e9)])
        col = "whale_netflow_usd"
        a, b = base[col].to_numpy()[:60], with_future[col].to_numpy()[:60]
        both_nan = np.isnan(a) & np.isnan(b)
        assert (np.isclose(a, b) | both_nan).all()

    @pytest.mark.unit
    def test_the_zscore_does_not_include_the_current_point(self):
        """Normalizar un punto contra una ventana que él mismo ayuda a formar es
        un sesgo pequeño con series largas y grande con ventanas cortas — y en
        cualquier caso información que en `t` no se tenía."""
        series = np.array([1.0] * 20 + [100.0])
        z = ex.rolling_z(series, window=10)
        # La ventana previa es constante, así que su desviación es cero y el
        # z-score del salto no puede calcularse: lo que NO puede pasar es que
        # salga un número modesto porque el propio 100 haya inflado la sigma.
        assert np.isnan(z[-1]) or abs(z[-1]) > 10


class TestWindowedSum:

    @pytest.mark.unit
    def test_it_adds_only_what_happened_inside_the_window(self):
        out = ex.windowed_sum([10 * H], [1 * H, 5 * H, 20 * H], [1.0, 2.0, 4.0],
                              window_ms=6 * H)
        assert out[0] == 2.0            # solo el de 5 h entra en (4 h, 10 h]

    @pytest.mark.unit
    def test_the_window_is_closed_on_the_right(self):
        """Un movimiento ocurrido exactamente al cierre de la vela ya se
        conocía."""
        assert ex.windowed_sum([100], [100], [3.0], window_ms=50)[0] == 3.0

    @pytest.mark.unit
    def test_no_events_sums_to_zero(self):
        assert (ex.windowed_sum([1, 2], [], [], 100) == 0).all()


class TestAvailability:
    """
    Un NaN significa dos cosas que el modelo no puede distinguir: «esta fuente no
    existe para este activo» y «existe pero aquí no había dato». La bandera lo
    hace explícito.
    """

    @pytest.mark.unit
    def test_every_group_declares_whether_it_has_data(self):
        frame = ex.assemble(_bars(50))
        for group in ex.GROUPS:
            flag = f"{group.name}{ex.AVAILABLE_SUFFIX}"
            assert flag in frame.columns
            assert (frame[flag] == 0).all()

    @pytest.mark.unit
    def test_the_columns_do_not_change_with_the_asset(self):
        """Si un activo sin funding tuviera menos columnas, dos estudios no
        serían comparables entre sí."""
        rich = ex.assemble(_bars(50), funding=_funding(20), whale=[(H, 1e6)])
        poor = ex.assemble(_bars(50))
        assert list(rich.columns) == list(poor.columns)

    @pytest.mark.unit
    def test_coverage_separates_not_measured_from_does_not_help(self):
        frame = ex.assemble(_bars(200), funding=_funding(40))
        cov = ex.coverage(frame)
        assert cov["groups"]["funding"]["usable"]
        assert not cov["groups"]["whale_flow"]["usable"]
        assert cov["usable_groups"] == ["funding"]

    @pytest.mark.unit
    def test_sources_without_persisted_history_are_declared_not_hidden(self):
        """El informe da por hecho que la plataforma «ya posee» open interest,
        long/short y profundidad. Las sabe LEER, no las guarda. Crear columnas
        de NaN en silencio haría que el estudio concluyera «no aportan» cuando
        lo cierto es «no se han medido»."""
        cov = ex.coverage(ex.assemble(_bars(10)))
        assert "open_interest" in cov["missing_history"]
        assert "orderbook_depth" in cov["missing_history"]
        assert all(isinstance(v, str) and v for v in cov["missing_history"].values())


class TestFundingBlock:

    @pytest.mark.unit
    def test_the_level_holds_between_settlements(self):
        """El funding se liquida cada ocho horas: entre liquidaciones, el último
        valor conocido SÍ es el vigente. Repetirlo no es propagar de más."""
        bars = _bars(24)
        out = ex.funding_features(bars, [(0, 0.0002), (8 * H, 0.0005)])
        assert out["funding_rate"][3] == pytest.approx(0.0002)
        assert out["funding_rate"][9] == pytest.approx(0.0005)

    @pytest.mark.unit
    def test_the_three_columns_say_different_things(self):
        """Nivel, anomalía y coste acumulado no son la misma variable con otra
        escala: un funding de 3 bp es alto en calma y bajo en euforia, y el nivel
        a secas no lo distingue."""
        out = ex.funding_features(_bars(300), _funding(60))
        rate, z, cum = out["funding_rate"], out["funding_z30"], out["funding_cum_3d"]
        ok = ~(np.isnan(rate) | np.isnan(z) | np.isnan(cum))
        assert ok.sum() > 50
        assert abs(np.corrcoef(rate[ok], z[ok])[0, 1]) < 0.99
        assert abs(np.corrcoef(rate[ok], cum[ok])[0, 1]) < 0.99

    @pytest.mark.unit
    def test_no_records_marks_the_block_unavailable(self):
        out = ex.funding_features(_bars(10), [])
        assert (out[f"funding{ex.AVAILABLE_SUFFIX}"] == 0).all()
        assert np.isnan(out["funding_rate"]).all()


class TestWhaleBlock:

    @pytest.mark.unit
    def test_outflows_and_inflows_cancel_in_the_net(self):
        out = ex.whale_flow_features(_bars(48), [(H, 5e6), (2 * H, -3e6)])
        assert out["whale_netflow_usd"][3] == pytest.approx(2e6)
        assert out["whale_tx_count"][3] == pytest.approx(2)

    @pytest.mark.unit
    def test_before_the_first_movement_there_is_no_flow_not_zero_flow(self):
        """Un cero diría «no hubo flujo»; lo cierto es «no se estaba
        observando», y el modelo no puede distinguirlos por sí solo."""
        out = ex.whale_flow_features(_bars(48), [(20 * H, 1e6)])
        assert np.isnan(out["whale_netflow_usd"][5])
        assert out[f"whale_flow{ex.AVAILABLE_SUFFIX}"][5] == 0

    @pytest.mark.unit
    def test_the_flow_leaves_the_window_when_it_gets_old(self):
        """Es la diferencia entre un flujo y un nivel: 10 M$ de hace dos días no
        son presión de hoy."""
        out = ex.whale_flow_features(_bars(72), [(1 * H, 9e6)])
        assert out["whale_netflow_usd"][5] == pytest.approx(9e6)
        assert out["whale_netflow_usd"][60] == pytest.approx(0.0)
