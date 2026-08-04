"""
test_price_patterns.py — Acción del precio como vocabulario del generador.

El catálogo de indicadores describe el mercado con NIVELES. Hay información que
ese vocabulario no puede expresar porque no es un nivel sino un suceso con
estructura: una vela que se traga a la anterior, un mínimo perforado que se
recupera, un hueco sin negociar. Un generador que solo combina osciladores no
puede descubrir esas estrategias — no están en su idioma.

Lo que se fija aquí, por encima de todo lo demás:

  · **CAUSALIDAD.** Es fácil escribir un detector de patrones que use la vela
    siguiente para «confirmar» —así se explican en casi toda la literatura— y el
    backtest resultante es ficción. El test que lo comprueba es truncar la serie
    y exigir que el pasado no cambie.
  · **Que cada patrón distinga lo que dice distinguir.** Una barrida de
    liquidez y una ruptura bajista tienen la misma primera mitad; si el detector
    no separa ambas, marca cosas opuestas con la misma señal.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import price_patterns as pp


def _df(rows):
    """rows: lista de (open, high, low, close)."""
    o, h, l, c = zip(*rows)
    return pd.DataFrame({
        "timestamp": [1_700_000_000_000 + i * 3_600_000 for i in range(len(rows))],
        "open": o, "high": h, "low": l, "close": c,
        "volume": [1000.0] * len(rows),
    })


def _random_df(n=400, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    spread = np.abs(rng.normal(0, 0.006, n)) + 0.002
    return pd.DataFrame({
        "timestamp": [1_700_000_000_000 + i * 3_600_000 for i in range(n)],
        "open": close * (1 + rng.normal(0, 0.003, n)),
        "high": close * (1 + spread), "low": close * (1 - spread),
        "close": close, "volume": rng.uniform(500, 1500, n),
    })


class TestCausality:
    """
    El test que más importa de este módulo.

    Si truncar la serie cambia lo que el detector dijo del pasado, es que estaba
    mirando hacia delante. Se comprueba sobre TODOS los patrones del catálogo
    porque basta que uno filtre para que el generador aprenda a explotarlo.
    """

    @pytest.mark.unit
    @pytest.mark.parametrize("name", sorted(pp.PATTERNS))
    def test_truncating_the_future_does_not_change_the_past(self, name):
        df = _random_df()
        cut = 250
        full = pp.detect(df, name)
        partial = pp.detect(df.iloc[:cut].reset_index(drop=True), name)
        assert np.array_equal(full[:cut], partial), f"{name} mira al futuro"

    @pytest.mark.unit
    @pytest.mark.parametrize("name", sorted(pp.PATTERNS))
    def test_every_pattern_returns_one_flag_per_candle(self, name):
        df = _random_df(n=120)
        assert pp.detect(df, name).shape == (120,)

    @pytest.mark.unit
    @pytest.mark.parametrize("name", sorted(pp.PATTERNS))
    def test_no_pattern_crashes_on_a_tiny_series(self, name):
        """Una serie más corta que el calentamiento no debe romper el backtest:
        debe no disparar. Es la misma política que el catálogo de indicadores."""
        out = pp.detect(_random_df(n=3), name)
        assert out.dtype == bool and out.size == 3


class TestCandlePatterns:

    @pytest.mark.unit
    def test_bullish_engulfing_needs_a_real_body_to_engulf(self):
        """Una vela previa casi sin cuerpo se «envuelve» sin esfuerzo: sin este
        requisito el patrón dispararía en cualquier lateral."""
        real = _df([(100, 101, 95, 96), (96, 105, 95, 104)])       # cuerpo previo grande
        doji_prev = _df([(100, 108, 92, 99.9), (99.9, 105, 95, 104)])
        assert pp.bullish_engulfing(real)[1]
        assert not pp.bullish_engulfing(doji_prev)[1]

    @pytest.mark.unit
    def test_engulfing_requires_the_previous_candle_to_be_opposite(self):
        """Envolver a una vela del mismo color no es una vuelta, es continuación."""
        same_color = _df([(95, 101, 94, 100), (94, 106, 93, 105)])
        assert not pp.bullish_engulfing(same_color)[1]

    @pytest.mark.unit
    def test_hammer_is_rejection_from_below_not_just_a_long_candle(self):
        hammer = _df([(100, 101, 90, 100.5)])       # mecha inferior larga
        big_body = _df([(90, 101, 89.5, 100)])      # cuerpo grande, sin rechazo
        assert pp.hammer(hammer)[0]
        assert not pp.hammer(big_body)[0]

    @pytest.mark.unit
    def test_shooting_star_is_the_mirror_of_the_hammer(self):
        star = _df([(100, 110, 99.5, 100.5)])
        assert pp.shooting_star(star)[0]
        assert not pp.hammer(star)[0]

    @pytest.mark.unit
    def test_inside_and_outside_bar_are_mutually_exclusive_when_strict(self):
        inside = _df([(100, 110, 90, 105), (101, 106, 96, 103)])
        outside = _df([(100, 105, 98, 103), (101, 110, 92, 95)])
        assert pp.inside_bar(inside)[1] and not pp.outside_bar(inside)[1]
        assert pp.outside_bar(outside)[1] and not pp.inside_bar(outside)[1]

    @pytest.mark.unit
    def test_doji_thresholds_are_proportional_not_absolute(self):
        """Un 0,1 % significa cosas distintas en BTC y en una altcoin. El umbral
        es una fracción del rango de la propia vela."""
        small = _df([(100, 101, 99, 100.05)])
        big = _df([(10000, 10100, 9900, 10005)])
        assert pp.doji(small)[0] and pp.doji(big)[0]


class TestStructure:

    @pytest.mark.unit
    def test_fvg_marks_the_candle_that_completes_the_gap(self):
        """El hueco suele dibujarse sobre la vela del medio; marcarlo ahí
        exigiría conocer la tercera. La señal va donde la información existe."""
        df = _df([(100, 101, 99, 100), (101, 106, 100.5, 105), (106, 108, 102, 107)])
        out = pp.fvg_bullish(df)
        assert out[2] and not out[1]     # low[2]=102 > high[0]=101

    @pytest.mark.unit
    def test_no_fvg_when_the_ranges_overlap(self):
        df = _df([(100, 105, 99, 104), (104, 106, 103, 105), (105, 107, 104, 106)])
        assert not pp.fvg_bullish(df).any()

    @pytest.mark.unit
    def test_liquidity_sweep_is_not_a_breakout(self):
        """Misma primera mitad, conclusión opuesta: la barrida VUELVE dentro,
        la ruptura se queda fuera. Un detector que no los separe marca dos
        cosas contrarias con la misma señal."""
        base = [(100, 101, 99, 100)] * 12
        sweep = _df(base + [(100, 100.5, 95, 100.2)])      # perfora y cierra dentro
        breakout = _df(base + [(100, 100.5, 95, 96.0)])    # perfora y cierra fuera
        assert pp.liquidity_sweep_low(sweep, window=10)[-1]
        assert not pp.liquidity_sweep_low(breakout, window=10)[-1]

    @pytest.mark.unit
    def test_sweep_compares_against_the_PREVIOUS_range_not_its_own(self):
        """Sin desplazar el rango, toda vela que marca un nuevo mínimo cumpliría
        su propia condición de ruptura: una tautología que dispararía siempre."""
        df = _random_df(n=200)
        out = pp.liquidity_sweep_low(df, window=20)
        assert out.mean() < 0.5, "la barrida dispara demasiado: rango sin desplazar"

    @pytest.mark.unit
    def test_crt_takes_the_previous_candle_and_closes_inside_it(self):
        taken = _df([(100, 105, 95, 102), (102, 106, 94, 100)])   # perfora ambos, cierra dentro
        contained = _df([(100, 105, 95, 102), (102, 104, 96, 103)])
        assert pp.crt(taken)[1]
        assert not pp.crt(contained)[1]

    @pytest.mark.unit
    def test_order_block_signals_on_the_return_not_on_the_block(self):
        """El bloque solo se sabe a posteriori; marcar su propia vela sería
        mirar el futuro. La señal llega cuando el precio VUELVE."""
        rows = [
            (100, 101, 99, 98),        # 0: vela bajista → candidata a bloque
            (98, 104, 97, 103),        # 1: impulso
            (103, 108, 102, 107),      # 2:
            (107, 110, 106, 109),      # 3: confirma (rompe el máximo del 0)
            (109, 110, 100, 100.5),    # 4: vuelve al rango del bloque
        ]
        out = pp.order_block_bullish(_df(rows), impulse=3)
        assert not out[0], "marcó la vela del bloque: eso es mirar el futuro"
        assert out[4]

    @pytest.mark.unit
    def test_a_mitigated_order_block_does_not_fire_twice(self):
        """Un bloque ya visitado ha cumplido su función. Dejarlo activo
        convertiría una zona en una fábrica de señales repetidas."""
        rows = [(100, 101, 99, 98), (98, 104, 97, 103), (103, 108, 102, 107),
                (107, 110, 106, 109), (109, 110, 100, 100.5),
                (100, 101, 99.5, 100.2), (100, 101, 99.5, 100.2)]
        out = pp.order_block_bullish(_df(rows), impulse=3)
        assert out.sum() == 1


class TestAmdAndOrb:

    @pytest.mark.unit
    def test_power_of_three_needs_all_three_phases(self):
        """Acumulación, manipulación y distribución. Sin compresión inicial no
        hay acumulación, y sin ella la secuencia es solo un movimiento más."""
        # Acumulación estrecha (0-1), barrida abajo (2-3), cierre arriba (4-6).
        rows = [(100, 100.5, 99.5, 100), (100, 100.5, 99.5, 100),
                (100, 100.4, 96.0, 97.0), (97, 98.0, 95.0, 97.5),
                (97, 101.0, 96.5, 100.0), (100, 102.0, 99.0, 101.5),
                (101, 103.0, 100.5, 102.5)]
        assert pp.power_of_three(_df(rows), window=6).any()

    @pytest.mark.unit
    def test_the_accumulation_phase_does_not_overlap_the_manipulation(self):
        """
        Las tres fases se calculan con ventanas móviles desplazadas, y el
        desplazamiento de la acumulación lleva un «+1» que es fácil de perder al
        optimizar: sin él, la última vela de la acumulación se cuela también en
        la manipulación, y la barrida se compara contra un mínimo que ya la
        incluye — con lo que casi nunca dispara.

        Este caso está construido para que la barrida ocurra en la PRIMERA vela
        de la fase de manipulación: si las fases se solapan, deja de detectarse.
        """
        rows = [
            (100, 100.5, 99.5, 100.0),   # 0 ┐ acumulación (tercio = 2 velas)
            (100, 100.5, 99.5, 100.0),   # 1 ┘
            (100, 100.4, 96.0, 97.0),    # 2 ← manipulación: barre el 99.5
            (97, 98.5, 96.5, 98.0),      # 3
            (98, 100.0, 97.5, 99.5),     # 4
            (99, 101.0, 98.5, 100.5),    # 5
            (100, 103.0, 100.0, 102.5),  # 6 ← distribución: cierra sobre 100.5
        ]
        assert pp.power_of_three(_df(rows), window=6)[6]

    @pytest.mark.unit
    def test_no_power_of_three_without_the_manipulation_leg(self):
        rows = [(100, 100.5, 99.5, 100)] * 2 + [
            (100, 101, 99.8, 100.8), (101, 102, 100.5, 101.5),
            (101, 103, 101, 102.5), (102, 104, 102, 103.5), (103, 105, 103, 104.5)]
        assert not pp.power_of_three(_df(rows), window=6).any()

    @pytest.mark.unit
    def test_orb_fires_once_per_day(self):
        """Un ORB que dispara diez veces en una sesión no es una ruptura: es una
        tendencia ya en marcha, y entrar en la décima no es lo mismo."""
        n = 48
        close = np.concatenate([np.full(6, 100.0), np.linspace(101, 130, n - 6)])
        df = pd.DataFrame({
            "timestamp": [1_700_000_000_000 + i * 3_600_000 for i in range(n)],
            "open": close, "high": close + 1, "low": close - 1, "close": close,
            "volume": [1000.0] * n,
        })
        out = pp.opening_range_break_up(df, bars=3)
        days = np.asarray(df["timestamp"]) // 86_400_000
        for d in np.unique(days):
            assert out[days == d].sum() <= 1

    @pytest.mark.unit
    def test_orb_without_timestamps_does_not_invent_sessions(self):
        df = _df([(100, 101, 99, 100)] * 30).drop(columns=["timestamp"])
        assert not pp.opening_range_break_up(df, bars=3).any()


class TestFibonacciZone:

    @pytest.mark.unit
    def test_discount_and_premium_are_opposite_halves_of_the_swing(self):
        """El catálogo ya tiene el NIVEL de Fibonacci como serie cruzable; esto
        es la ZONA, que es un estado y no se puede expresar con un cruce."""
        n = 80
        # Sube de 100 a 200 y retrocede al 70 % (zona de descuento).
        close = np.concatenate([np.linspace(100, 200, 60), np.linspace(200, 130, 20)])
        df = pd.DataFrame({
            "timestamp": [1_700_000_000_000 + i * 3_600_000 for i in range(n)],
            "open": close, "high": close + 0.5, "low": close - 0.5, "close": close,
            "volume": [1000.0] * n,
        })
        disc = pp.fib_discount(df, window=60)
        prem = pp.fib_premium(df, window=60)
        assert disc.any()
        assert not (disc & prem).any(), "una vela no puede estar en ambas zonas"


class TestLookbackWindow:

    @pytest.mark.unit
    def test_window_looks_backward_only(self):
        flags = np.array([False, True, False, False, False])
        out = pp.occurred_within(flags, 3)
        assert list(out) == [False, True, True, True, False]

    @pytest.mark.unit
    def test_a_window_of_one_changes_nothing(self):
        flags = np.array([False, True, False])
        assert np.array_equal(pp.occurred_within(flags, 1), flags)

    @pytest.mark.unit
    def test_the_window_is_what_makes_two_patterns_combinable(self):
        """Sin ventana, la Y de dos sucesos puntuales es casi siempre falsa, y
        el generador descartaría la familia por estéril en vez de por mala."""
        df = _random_df(n=400)
        a = pp.detect(df, "CRT")
        b = pp.detect(df, "INSIDE_BAR")
        same_bar = (a & b).sum()
        within_5 = (pp.occurred_within(a, 5) & pp.occurred_within(b, 5)).sum()
        assert within_5 > same_bar


class TestCatalogue:

    @pytest.mark.unit
    def test_every_pattern_declares_its_warmup(self):
        """El calentamiento de un patrón no se deduce de sus parámetros: una
        envolvente no tiene ninguno y aun así necesita dos velas."""
        for name, meta in pp.PATTERNS.items():
            assert meta.get("warmup", 0) >= 1, name

    @pytest.mark.unit
    def test_every_pattern_has_a_readable_label(self):
        """Una estrategia que el usuario no puede leer no la puede juzgar."""
        assert set(pp.PATTERNS) <= set(pp.PATTERN_LABELS)

    @pytest.mark.unit
    def test_unknown_pattern_never_fires_instead_of_crashing(self):
        assert not pp.detect(_random_df(n=50), "NO_EXISTE").any()

    @pytest.mark.unit
    def test_the_requested_families_are_all_present(self):
        """Lista explícita: si alguien recorta el catálogo, este test lo dice."""
        for family in ("HAMMER", "BULL_ENGULF", "FIB_DISCOUNT", "CRT", "ORB_UP",
                       "FVG_BULL", "OB_BULL", "PO3_BULL", "SWEEP_LOW"):
            assert family in pp.PATTERNS
