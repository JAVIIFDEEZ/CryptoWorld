"""
test_short_direction.py — Los cortos como parte de la gramática, no como añadido.

El motor de ejecución ya sabía vender en corto (test_short_execution.py). Lo que
se comprueba aquí es lo otro: que el GENERADOR sepa buscar en ese lado. Son
cosas distintas y la segunda es la que puede fallar en silencio — un spec corto
mal cableado no da error, da un backtest de una estrategia que no es la que
describe.

Los cuatro riesgos que cubren estos tests, en orden de gravedad:

  1. **Que el lado corto no se ejecute.** Un spec "short" cuyas señales no
     llegasen al motor daría cero operaciones y el gating lo descartaría por
     falta de muestra. Se leería como «no hay edge en cortos» cuando lo que hay
     es un cable suelto.
  2. **Que medio genoma no evolucione.** En un spec "both" los bloques cortos
     son cuatro de los cuatro bloques; si los operadores genéticos siguen
     mirando solo `entry`/`exit`, el lado corto entra en el sorteo inicial y ya
     no cambia nunca.
  3. **Que un lado malo apruebe escondido detrás del otro.** Es el riesgo con
     dinero real: el agregado sale bien y nadie mira de dónde.
  4. **Que los cortos se cuelen donde no se han pedido.** Una ejecución
     configurada en largos tiene que producir exactamente lo de siempre.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import strategy_generator as G
from core.domain.services.strategy_evaluation import (
    GatingThresholds, _isolate_side, _leak_probe, _segment_backtest,
    _sides_stand_alone, side_performance, spec_complexity,
)
from core.domain.services.strategy_spec import (
    DIRECTIONS, compile_long_signals, compile_short_signals, compile_sides,
    condition_blocks, describe_spec, max_warmup, mirror_spec, random_spec,
    seed_specs, spec_direction, spec_hash, validate_spec,
)


def _df(n=1200, seed=7, drift=0.0):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.012, n)))
    spread = np.abs(rng.normal(0, 0.006, n)) + 0.002
    return pd.DataFrame({
        "timestamp": [1_600_000_000_000 + i * 3_600_000 for i in range(n)],
        "open": close, "high": close * (1 + spread), "low": close * (1 - spread),
        "close": close, "volume": np.ones(n) * 1000,
    })


def _rsi_long():
    return seed_specs()[0]


def _rsi_short():
    return {**mirror_spec(_rsi_long()), "direction": "short"}


def _rsi_both():
    base, mirrored = _rsi_long(), mirror_spec(_rsi_long())
    return {**base, "direction": "both",
            "short_entry": mirrored["entry"], "short_exit": mirrored["exit"]}


class TestGrammar:

    @pytest.mark.unit
    @pytest.mark.parametrize("mode", DIRECTIONS + ("auto",))
    def test_random_specs_are_always_legal(self, mode):
        rng = np.random.default_rng(3)
        for _ in range(200):
            assert validate_spec(random_spec(rng, mode))

    @pytest.mark.unit
    def test_a_fixed_mode_produces_only_that_direction(self):
        rng = np.random.default_rng(5)
        for mode in DIRECTIONS:
            assert {spec_direction(random_spec(rng, mode)) for _ in range(50)} == {mode}

    @pytest.mark.unit
    def test_auto_reaches_all_three_directions(self):
        """Si "auto" no llegara a algún lado, sería un modo fijo con más pasos."""
        rng = np.random.default_rng(5)
        assert {spec_direction(random_spec(rng, "auto")) for _ in range(300)} == set(DIRECTIONS)

    @pytest.mark.unit
    def test_a_long_spec_serializes_exactly_as_before(self):
        """El campo `direction` solo se escribe cuando dice algo.

        Importa por el hash: si un spec largo lo llevara explícito, su hash
        cambiaría y los libros de estrategias ya guardados dejarían de ser
        comparables con los nuevos."""
        rng = np.random.default_rng(11)
        for _ in range(50):
            assert "direction" not in random_spec(rng, "long")

    @pytest.mark.unit
    def test_short_blocks_only_exist_in_both(self):
        """En "short" los bloques principales YA son el lado corto: un
        `short_entry` ahí sería material inerte, y dos specs distintos
        describirían la misma estrategia."""
        spec = _rsi_short()
        spec["short_entry"] = spec["entry"]
        spec["short_exit"] = spec["exit"]
        assert not validate_spec(spec)

    @pytest.mark.unit
    def test_both_requires_both_short_blocks(self):
        spec = _rsi_both()
        del spec["short_exit"]
        assert not validate_spec(spec)

    @pytest.mark.unit
    def test_description_names_the_side(self):
        assert describe_spec(_rsi_long()).startswith("ENTRAR si")
        assert describe_spec(_rsi_short()).startswith("CORTO si")
        both = describe_spec(_rsi_both())
        assert "LARGO si" in both and "CORTO si" in both


class TestMirror:
    """El espejo se usa para SEMBRAR. Si refleja mal, el warm start estorba."""

    @pytest.mark.unit
    def test_a_threshold_reflects_within_its_own_range(self):
        """RSI de rango (15, 85): «< 30» es «> 70» visto desde el otro extremo."""
        c = mirror_spec(_rsi_long())["entry"]["conditions"][0]
        assert c["op"] == "gt" and c["threshold"] == 70.0

    @pytest.mark.unit
    def test_non_directional_oscillators_are_left_alone(self):
        """«ADX > 25» significa «hay tendencia». Su contrario no es «ADX < 30»:
        es «ADX > 25» otra vez. Reflejarlo rompería la condición, no la
        invertiría."""
        spec = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "ADX", "params": {"window": 14},
                 "op": "gt", "threshold": 25.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
                 "op": "gt", "threshold": 70.0}]},
        }
        mirrored = mirror_spec(spec)
        assert mirrored["entry"]["conditions"][0] == spec["entry"]["conditions"][0]
        assert mirrored["exit"]["conditions"][0]["op"] == "lt"

    @pytest.mark.unit
    def test_neutral_patterns_have_no_opposite(self):
        """Un doji no tiene lado. Inventarle uno sería fabricar una condición."""
        spec = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "pattern", "pattern": "DOJI", "params": {}, "lookback": 2}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "pattern", "pattern": "SWEEP_LOW", "params": {"window": 20},
                 "lookback": 2}]},
        }
        mirrored = mirror_spec(spec)
        assert mirrored["entry"]["conditions"][0]["pattern"] == "DOJI"
        assert mirrored["exit"]["conditions"][0]["pattern"] == "SWEEP_HIGH"

    @pytest.mark.unit
    def test_mirroring_twice_returns_the_original(self):
        """Propiedad de involución: si no volviera al original, el espejo estaría
        perdiendo información por el camino."""
        rng = np.random.default_rng(17)
        for _ in range(60):
            spec = random_spec(rng, "long")
            assert spec_hash(mirror_spec(mirror_spec(spec))) == spec_hash(spec)

    @pytest.mark.unit
    def test_mirrored_specs_are_legal(self):
        rng = np.random.default_rng(19)
        for _ in range(80):
            assert validate_spec(mirror_spec(random_spec(rng, "long")))


class TestCompilation:

    @pytest.mark.unit
    def test_a_long_spec_has_no_short_side(self):
        """`None`, no un array de ceros: es lo que deja al motor tomar
        exactamente la misma ruta que antes de que existieran los cortos."""
        assert compile_short_signals(_df(200), _rsi_long()) is None

    @pytest.mark.unit
    def test_a_short_spec_drives_the_short_side_with_its_main_blocks(self):
        df = _df()
        assert not compile_long_signals(df, _rsi_short()).any()
        assert (compile_short_signals(df, _rsi_short()) != 0).any()

    @pytest.mark.unit
    def test_both_sides_come_from_their_own_blocks(self):
        df = _df()
        sides = compile_sides(df, _rsi_both())
        assert np.array_equal(sides.long, compile_long_signals(df, _rsi_long()))
        assert np.array_equal(sides.short, compile_short_signals(df, _rsi_short()))

    @pytest.mark.unit
    def test_slicing_takes_both_sides_together(self):
        """Recortar uno y olvidar el otro daría un tramo con largos del prefijo
        y cortos del histórico entero: un número plausible y equivocado."""
        sides = compile_sides(_df(), _rsi_both()).head(400)
        assert len(sides.long) == 400 and len(sides.short) == 400

    @pytest.mark.unit
    def test_signals_are_prefix_stable_on_both_sides(self):
        """La causalidad de la que depende la reutilización del walk-forward
        tiene que valer también para los bloques cortos."""
        df = _df()
        rng = np.random.default_rng(23)
        for _ in range(15):
            spec = random_spec(rng, "auto")
            full = compile_sides(df, spec)
            for k in (400, 900):
                prefix = compile_sides(df.iloc[:k], spec)
                assert np.array_equal(full.long[:k], prefix.long)
                if full.short is None:
                    assert prefix.short is None
                else:
                    assert np.array_equal(full.short[:k], prefix.short)

    @pytest.mark.unit
    def test_the_leak_probe_sees_the_short_blocks(self):
        """Sin esto, los bloques cortos de un spec "both" quedarían sin auditar:
        podrían mirar al futuro y el control diría que está limpio."""
        df = _df(400)
        spec = _rsi_both()
        probe = _leak_probe(df, spec)
        other = dict(spec)
        other["short_entry"] = mirror_spec(_rsi_long())["exit"]
        assert not np.array_equal(probe, _leak_probe(df, other))


class TestExecution:

    @pytest.mark.unit
    def test_a_short_spec_actually_opens_short_trades(self):
        """El riesgo nº 1: si las señales no llegasen al motor, esto daría cero
        operaciones y el gating lo leería como «no hay edge en cortos»."""
        trades = _segment_backtest(_df(), _rsi_short())["trades"]
        assert trades and {t["side"] for t in trades} == {"short"}

    @pytest.mark.unit
    def test_a_both_spec_trades_on_both_sides(self):
        trades = _segment_backtest(_df(), _rsi_both())["trades"]
        assert {t["side"] for t in trades} == {"long", "short"}

    @pytest.mark.unit
    def test_the_two_sides_compete_for_the_same_position(self):
        """El motor mantiene UNA posición: los lados no suman sus operaciones,
        se las disputan. Es una propiedad del modelo de ejecución, no un
        defecto, y conviene tenerla fijada — la atribución por lado se lee mal
        si se espera que sumen."""
        df = _df()
        n_long = len(_segment_backtest(df, _rsi_long())["trades"])
        n_short = len(_segment_backtest(df, _rsi_short())["trades"])
        n_both = len(_segment_backtest(df, _rsi_both())["trades"])
        assert n_both <= n_long + n_short

    @pytest.mark.unit
    def test_a_long_only_spec_is_untouched_by_all_of_this(self):
        """El riesgo nº 4. Lo ya validado tiene que dar exactamente lo mismo."""
        df = _df()
        spec = _rsi_long()
        with_sides = _segment_backtest(df, spec)
        legacy = _segment_backtest(df, spec, signals=compile_long_signals(df, spec))
        assert with_sides["trades"] == legacy["trades"]
        assert with_sides["total_return_pct"] == legacy["total_return_pct"]


class TestEvolution:

    @pytest.mark.unit
    def test_mutation_reaches_the_short_blocks(self):
        """El riesgo nº 2: medio genoma congelado no rompe nada, solo hace que
        el lado corto nunca mejore."""
        rng = np.random.default_rng(29)
        spec = _rsi_both()
        touched = set()
        for _ in range(400):
            child = G.mutate(spec, rng, "auto")
            if spec_direction(child) != "both":
                continue
            for block in ("entry", "exit", "short_entry", "short_exit"):
                if child[block] != spec[block]:
                    touched.add(block)
        assert {"short_entry", "short_exit"} <= touched

    @pytest.mark.unit
    def test_direction_only_mutates_when_the_run_allows_it(self):
        """Con la dirección fija por configuración, cambiarla sería desobedecer
        al usuario, no explorar."""
        rng = np.random.default_rng(31)
        spec = _rsi_long()
        assert all(spec_direction(G.mutate(spec, rng)) == "long" for _ in range(200))

    @pytest.mark.unit
    def test_direction_mutation_visits_every_side(self):
        rng = np.random.default_rng(37)
        cur = _rsi_long()
        seen = set()
        for _ in range(200):
            cur = G._mutate_direction(cur, rng)
            assert validate_spec(cur)
            seen.add(spec_direction(cur))
        assert seen == set(DIRECTIONS)

    @pytest.mark.unit
    def test_going_from_short_to_both_keeps_the_short_side_short(self):
        """Los bloques principales de un "short" son el lado corto; en "both"
        pasan a ser el largo. Sin la mudanza, el material cambiaría de lado en
        silencio y la estrategia se convertiría en su contraria."""
        rng = np.random.default_rng(41)
        spec = _rsi_short()
        for _ in range(200):
            child = G._mutate_direction(spec, rng)
            if spec_direction(child) == "both":
                assert child["short_entry"] == spec["entry"]
                assert child["short_exit"] == spec["exit"]
                return
        pytest.fail("la mutación nunca llegó a 'both'")

    @pytest.mark.unit
    def test_mutation_always_changes_something(self):
        """Un operador sin dónde morder consumía la mutación de la generación y
        devolvía el padre idéntico. Comparar el hash convierte esos turnos
        perdidos en mutaciones reales."""
        rng = np.random.default_rng(43)
        for mode in ("long", "auto"):
            for _ in range(150):
                spec = random_spec(rng, mode)
                assert spec_hash(G.mutate(spec, rng, mode)) != spec_hash(spec)

    @pytest.mark.unit
    def test_crossover_does_not_mix_directions(self):
        """Un bloque calibrado para comprar caídas no significa lo mismo
        gobernando la apertura de un corto: eso no es recombinación, es ruido."""
        rng = np.random.default_rng(47)
        child = G.crossover(_rsi_long(), _rsi_short(), rng)
        assert spec_hash(child) == spec_hash(_rsi_long())

    @pytest.mark.unit
    def test_crossover_recombines_the_short_side_too(self):
        rng = np.random.default_rng(53)
        a, b = random_spec(rng, "both"), random_spec(rng, "both")
        seen = set()
        for _ in range(60):
            child = G.crossover(a, b, rng)
            assert validate_spec(child) and spec_direction(child) == "both"
            seen.add((child["short_entry"] == a["short_entry"],
                      child["short_exit"] == a["short_exit"]))
        assert len(seen) > 1, "el lado corto viaja pegado, no se recombina"

    @pytest.mark.unit
    def test_seeds_are_oriented_to_the_side_being_searched(self):
        """Sembrar una búsqueda de cortos con las clásicas largas arrancaría el
        GA desde lógicas que en ese lado pierden por construcción."""
        assert all(spec_direction(s) == "short" for s in G._directional_seeds("short"))
        assert all(spec_direction(s) == "both" for s in G._directional_seeds("both"))
        assert G._directional_seeds("long") == seed_specs()
        short_rsi = G._directional_seeds("short")[0]["entry"]["conditions"][0]
        assert short_rsi["op"] == "gt" and short_rsi["threshold"] == 70.0

    @pytest.mark.unit
    def test_the_initial_population_respects_the_configured_side(self):
        rng = np.random.default_rng(59)
        for mode in DIRECTIONS:
            pop = G._initial_population(G.GAConfig(population_size=30, direction=mode), rng)
            assert {spec_direction(s) for s in pop} == {mode}
            assert all(validate_spec(s) for s in pop)


class TestPerSideGating:
    """El riesgo nº 3, que es el que cuesta dinero."""

    @pytest.mark.unit
    def test_complexity_counts_the_short_blocks(self):
        """Si solo se contaran los bloques largos, la familia con el doble de
        grados de libertad sería además la más barata de complejidad — y la
        presión de parsimonia premiaría justo lo que debería penalizar."""
        assert spec_complexity(_rsi_both()) == 2 * spec_complexity(_rsi_long())

    @pytest.mark.unit
    def test_warmup_counts_the_short_blocks(self):
        """Si el lado corto usa una ventana más larga, la estrategia necesita
        ese calentamiento aunque el lado largo no lo pida."""
        spec = _rsi_both()
        spec["short_entry"] = {"combine": "AND", "conditions": [
            {"type": "compare",
             "a": {"indicator": "SMA", "params": {"window": 20}},
             "b": {"indicator": "SMA", "params": {"window": 200}}, "op": "below"}]}
        assert max_warmup(spec) >= 200

    @pytest.mark.unit
    def test_isolating_a_side_gives_a_real_one_sided_strategy(self):
        both = _rsi_both()
        long_only, short_only = _isolate_side(both, "long"), _isolate_side(both, "short")
        assert spec_direction(long_only) == "long"
        assert spec_direction(short_only) == "short"
        assert condition_blocks(short_only) == ("entry", "exit")
        assert short_only["entry"] == both["short_entry"]

    @pytest.mark.unit
    def test_one_sided_specs_have_nothing_to_break_down(self):
        df = _df()
        trades = _segment_backtest(df, _rsi_long())["trades"]
        assert side_performance(df, _rsi_long(), trades) == {}
        assert _sides_stand_alone({}, GatingThresholds()) == (True, [])

    @pytest.mark.unit
    def test_the_breakdown_attributes_every_trade(self):
        df = _df()
        spec = _rsi_both()
        trades = _segment_backtest(df, spec)["trades"]
        sides = side_performance(df, spec, trades)
        assert sides["long"]["n_trades"] + sides["short"]["n_trades"] == len(trades)
        assert set(sides) == {"long", "short"}

    @pytest.mark.unit
    def test_a_losing_side_blocks_the_strategy(self):
        """El caso que motiva todo esto: brillante en un lado, desastroso en el
        otro, agregado aceptable. Por promedio aprobaría."""
        th = GatingThresholds()
        breakdown = {
            "long": {"n_trades": 40, "standalone_oos_sharpe": 1.8},
            "short": {"n_trades": 30, "standalone_oos_sharpe": -0.9},
        }
        ok, reasons = _sides_stand_alone(breakdown, th)
        assert not ok
        assert len(reasons) == 1 and "corto" in reasons[0]

    @pytest.mark.unit
    def test_a_decorative_side_blocks_the_strategy(self):
        """Un lado que apenas opera no aporta muestra, solo grados de libertad:
        nada de lo que se mida sobre él significa algo."""
        ok, reasons = _sides_stand_alone(
            {"long": {"n_trades": 40, "standalone_oos_sharpe": 1.8},
             "short": {"n_trades": 2, "standalone_oos_sharpe": 3.0}},
            GatingThresholds(),
        )
        assert not ok and "apenas opera" in reasons[0]

    @pytest.mark.unit
    def test_two_healthy_sides_pass(self):
        ok, reasons = _sides_stand_alone(
            {"long": {"n_trades": 40, "standalone_oos_sharpe": 1.1},
             "short": {"n_trades": 22, "standalone_oos_sharpe": 0.4}},
            GatingThresholds(),
        )
        assert ok and reasons == []
