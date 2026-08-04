"""
test_pattern_conditions.py — La acción del precio dentro de la gramática.

Tener los detectores no basta: si el generador no puede sortearlos, mutarlos,
validarlos y describirlos, la familia entera es código muerto. Estos tests
cubren el recorrido completo de una condición `pattern` por el mismo camino que
recorren las otras cuatro.

El criterio de fondo: que el gating decida si los patrones aportan. Este módulo
solo garantiza que *puedan* llegar hasta él.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import price_patterns as pp
from core.domain.services.strategy_generator import mutate
from core.domain.services.strategy_spec import (
    PATTERNS,
    PATTERN_LOOKBACK_RANGE,
    catalog_version,
    compile_signals,
    describe_spec,
    jitter_params,
    max_warmup,
    random_spec,
    validate_spec,
)


def _df(n=400, seed=5):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.012, n)))
    spread = np.abs(rng.normal(0, 0.006, n)) + 0.002
    return pd.DataFrame({
        "timestamp": [1_700_000_000_000 + i * 3_600_000 for i in range(n)],
        "open": close * (1 + rng.normal(0, 0.003, n)),
        "high": close * (1 + spread), "low": close * (1 - spread),
        "close": close, "volume": rng.uniform(500, 1500, n),
    })


def _spec(pattern="SWEEP_LOW", params=None, lookback=3):
    return {
        "entry": {"combine": "AND", "conditions": [
            {"type": "pattern", "pattern": pattern,
             "params": params if params is not None else {"window": 20},
             "lookback": lookback},
        ]},
        "exit": {"combine": "OR", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
             "op": "gt", "threshold": 65.0},
        ]},
    }


class TestCompilation:

    @pytest.mark.unit
    def test_a_pattern_spec_compiles_to_signals(self):
        signals = compile_signals(_df(), _spec())
        assert signals.shape == (400,)
        assert set(np.unique(signals)) <= {-1, 0, 1}

    @pytest.mark.unit
    def test_the_lookback_widens_the_entry(self):
        """Es la razón de existir de la ventana: sin ella el suceso es puntual
        y casi nunca coincide con nada más."""
        df = _df()
        narrow = (compile_signals(df, _spec(lookback=1)) == 1).sum()
        wide = (compile_signals(df, _spec(lookback=8)) == 1).sum()
        assert wide >= narrow

    @pytest.mark.unit
    def test_compilation_stays_causal_with_patterns(self):
        """El generador ya tenía esta garantía; añadir un tipo de condición no
        puede romperla. Truncar el futuro no cambia las señales del pasado."""
        df = _df()
        full = compile_signals(df, _spec())
        partial = compile_signals(df.iloc[:250].reset_index(drop=True), _spec())
        # Se compara sin el arranque, donde el recalentamiento de indicadores
        # legítimamente difiere entre la serie completa y la truncada.
        assert np.array_equal(full[100:250], partial[100:])

    @pytest.mark.unit
    def test_patterns_are_cached_per_params_not_per_name(self):
        """Dos ventanas distintas del mismo patrón son series distintas. Un
        caché por nombre devolvería la primera para ambas."""
        df = _df()
        a = compile_signals(df, _spec("SWEEP_LOW", {"window": 10}, 1))
        b = compile_signals(df, _spec("SWEEP_LOW", {"window": 60}, 1))
        assert not np.array_equal(a, b)


class TestValidation:

    @pytest.mark.unit
    def test_a_well_formed_pattern_spec_is_legal(self):
        assert validate_spec(_spec())

    @pytest.mark.unit
    def test_unknown_pattern_is_rejected(self):
        assert not validate_spec(_spec("NO_EXISTE", {}, 3))

    @pytest.mark.unit
    def test_out_of_range_lookback_is_rejected(self):
        assert not validate_spec(_spec(lookback=99))

    @pytest.mark.unit
    def test_missing_or_extra_params_are_rejected(self):
        assert not validate_spec(_spec("SWEEP_LOW", {}, 3))
        assert not validate_spec(_spec("CRT", {"window": 20}, 3))

    @pytest.mark.unit
    def test_parameterless_patterns_take_an_empty_dict(self):
        """Una envolvente es una envolvente: el conjunto vacío es legal."""
        assert validate_spec(_spec("BULL_ENGULF", {}, 2))


class TestEvolution:

    @pytest.mark.unit
    def test_the_random_generator_produces_pattern_conditions(self):
        """Si nunca aparecen en la población inicial, el GA no puede evaluarlas
        y la familia es código muerto por mucho que exista."""
        rng = np.random.default_rng(0)
        specs = [random_spec(rng) for _ in range(200)]
        has_pattern = [s for s in specs
                       if any(c["type"] == "pattern"
                              for side in ("entry", "exit") for c in s[side]["conditions"])]
        assert has_pattern, "el generador nunca sortea una condición de patrón"

    @pytest.mark.unit
    def test_every_random_spec_is_legal(self):
        rng = np.random.default_rng(1)
        assert all(validate_spec(random_spec(rng)) for _ in range(300))

    @pytest.mark.unit
    def test_mutation_never_produces_an_illegal_spec(self):
        """`_mutate_flip_op` no puede invertir el operador de un patrón —no
        tiene—, y antes reventaba con KeyError en vez de saltárselo."""
        rng = np.random.default_rng(2)
        spec = _spec()
        for _ in range(300):
            spec = mutate(spec, rng)
            assert validate_spec(spec)

    @pytest.mark.unit
    def test_mutation_can_change_which_pattern_is_sought(self):
        """Sin mutación dirigida, pasar de «barrida» a «hueco de valor» exigiría
        destruir la condición entera y volver a sortearla."""
        rng = np.random.default_rng(3)
        seen = set()
        spec = _spec()
        for _ in range(400):
            spec = mutate(spec, rng)
            for side in ("entry", "exit"):
                for c in spec[side]["conditions"]:
                    if c["type"] == "pattern":
                        seen.add(c["pattern"])
        assert len(seen) > 1

    @pytest.mark.unit
    def test_jitter_moves_params_and_window_but_not_the_pattern(self):
        """Un vecino perturba magnitudes; cambiar el patrón sería otra
        estructura, no un vecino — y el PBO dejaría de medir sensibilidad
        local."""
        rng = np.random.default_rng(4)
        spec = _spec("SWEEP_LOW", {"window": 30}, 4)
        for _ in range(50):
            near = jitter_params(spec, rng)
            assert near["entry"]["conditions"][0]["pattern"] == "SWEEP_LOW"
            assert validate_spec(near)

    @pytest.mark.unit
    def test_jitter_keeps_the_lookback_inside_its_range(self):
        rng = np.random.default_rng(5)
        lo, hi = PATTERN_LOOKBACK_RANGE
        spec = _spec(lookback=hi)
        for _ in range(80):
            spec = jitter_params(spec, rng)
            assert lo <= spec["entry"]["conditions"][0]["lookback"] <= hi


class TestReporting:

    @pytest.mark.unit
    def test_the_description_is_readable_in_spanish(self):
        """Una estrategia que el usuario no puede leer no la puede juzgar."""
        text = describe_spec(_spec("SWEEP_LOW", {"window": 20}, 4))
        assert "barrida de liquidez" in text
        assert "últimas 4 velas" in text

    @pytest.mark.unit
    def test_a_lookback_of_one_does_not_mention_a_window(self):
        assert "últimas" not in describe_spec(_spec("CRT", {}, 1))

    @pytest.mark.unit
    def test_warmup_comes_from_the_catalogue_not_the_params(self):
        """Una envolvente no tiene parámetros y aun así necesita dos velas:
        deducir el calentamiento de los parámetros daría 1."""
        assert max_warmup(_spec("BULL_ENGULF", {}, 1)) >= PATTERNS["BULL_ENGULF"]["warmup"]

    @pytest.mark.unit
    def test_the_catalogue_fingerprint_covers_the_patterns(self):
        """Añadir un patrón cambia lo que el generador puede descubrir. Si no
        entrase en la huella, dos ejecuciones con la misma semilla dejarían de
        ser comparables sin que nada lo dijera."""
        before = catalog_version()
        PATTERNS["__TEMP__"] = {"compute": pp.crt, "params": {}, "warmup": 2}
        try:
            assert catalog_version() != before
        finally:
            PATTERNS.pop("__TEMP__")
        assert catalog_version() == before
