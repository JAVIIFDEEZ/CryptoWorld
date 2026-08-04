"""
test_grammar_expansion.py — Negación y confirmación parcial («k de n»).

Dos ampliaciones que no mejoran cómo se valida una estrategia sino **cuántas
puede expresar el generador**:

  · **Negación.** La ausencia de un estado es información tan legítima como su
    presencia. «El precio NO está en zona de premium» o «no ha habido barrida en
    5 velas» eran inexpresables salvo que existiera por casualidad un indicador
    espejo. Con `negate`, cada condición de estado cuenta por dos.
  · **`k de n`.** La lógica de confirmación parcial —«al menos 2 de estas 3»— no
    se puede escribir encadenando Y y O sin anidar. Era una familia entera
    inalcanzable, no difícil de alcanzar.

Y dos reglas que impiden que la ampliación se convierta en ruido: no se puede
negar un suceso puntual (su complemento es cierto casi siempre), y `k de n` solo
existe con 3+ condiciones (con dos, es un AND o un OR escrito de otra forma).
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services.strategy_generator import mutate
from core.domain.services.strategy_spec import (
    MIN_NEGATABLE_LOOKBACK,
    NEGATABLE,
    catalog_version,
    compile_signals,
    describe_spec,
    random_spec,
    validate_spec,
)


def _df(n=400, seed=9):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.013, n)))
    spread = np.abs(rng.normal(0, 0.006, n)) + 0.002
    return pd.DataFrame({
        "timestamp": [1_700_000_000_000 + i * 3_600_000 for i in range(n)],
        "open": close, "high": close * (1 + spread), "low": close * (1 - spread),
        "close": close, "volume": rng.uniform(500, 1500, n),
    })


def _rsi(op="lt", threshold=35.0, **extra):
    return {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
            "op": op, "threshold": threshold, **extra}


def _spec(entry_block, exit_block=None):
    return {
        "entry": entry_block,
        "exit": exit_block or {"combine": "OR", "conditions": [_rsi("gt", 70.0)]},
    }


class TestNegation:

    @pytest.mark.unit
    def test_negation_inverts_the_condition(self):
        df = _df()
        plain = compile_signals(df, _spec({"combine": "AND", "conditions": [_rsi()]}))
        negated = compile_signals(
            df, _spec({"combine": "AND", "conditions": [_rsi(negate=True)]}))
        assert not np.array_equal(plain, negated)
        # Donde una entra, la otra no puede entrar (salvo que mande la salida).
        assert not ((plain == 1) & (negated == 1)).any()

    @pytest.mark.unit
    def test_a_negated_state_is_expressible_and_legal(self):
        assert validate_spec(_spec({"combine": "AND", "conditions": [_rsi(negate=True)]}))

    @pytest.mark.unit
    def test_a_point_event_cannot_be_negated(self):
        """El complemento de «hubo un cruce en esta vela» es cierto el 99 % del
        tiempo: una condición siempre verdadera disfrazada, que dentro de un Y
        reduce en silencio un bloque de tres condiciones a uno de dos."""
        cross = {"type": "cross", "op": "cross_above",
                 "a": {"indicator": "EMA", "params": {"window": 12}},
                 "b": {"indicator": "EMA", "params": {"window": 26}},
                 "negate": True}
        assert not validate_spec(_spec({"combine": "AND", "conditions": [cross]}))

    @pytest.mark.unit
    def test_a_pattern_needs_a_window_to_be_negatable(self):
        """Con ventana corta un patrón sigue siendo un suceso; con ventana
        suficiente, «no ha habido barrida en N velas» describe un régimen."""
        short = {"type": "pattern", "pattern": "SWEEP_LOW", "params": {"window": 20},
                 "lookback": 1, "negate": True}
        long_ = {**short, "lookback": MIN_NEGATABLE_LOOKBACK}
        assert not validate_spec(_spec({"combine": "AND", "conditions": [short]}))
        assert validate_spec(_spec({"combine": "AND", "conditions": [long_]}))

    @pytest.mark.unit
    def test_cross_is_the_only_type_left_out(self):
        assert set(NEGATABLE) == {"threshold", "compare", "slope", "pattern"}

    @pytest.mark.unit
    def test_the_description_says_it_is_a_negation(self):
        text = describe_spec(_spec({"combine": "AND", "conditions": [_rsi(negate=True)]}))
        assert "NO (" in text

    @pytest.mark.unit
    def test_negation_appears_in_the_random_population(self):
        rng = np.random.default_rng(0)
        found = 0
        for _ in range(300):
            spec = random_spec(rng)
            found += sum(1 for side in ("entry", "exit")
                         for c in spec[side]["conditions"] if c.get("negate"))
        assert found > 0, "el generador nunca niega una condición"


class TestKofN:

    @pytest.mark.unit
    def test_k_of_n_sits_strictly_between_or_and_and(self):
        """Es la comprobación que justifica la familia: con las mismas tres
        condiciones, «al menos 2» entra menos que un O y más que un Y."""
        df = _df()
        conds = [_rsi("lt", 45.0), _rsi("lt", 40.0),
                 {"type": "compare", "op": "above",
                  "a": {"indicator": "PRICE", "params": {}},
                  "b": {"indicator": "SMA", "params": {"window": 50}}}]

        def entries(block):
            return int((compile_signals(df, _spec(block)) == 1).sum())

        n_or = entries({"combine": "OR", "conditions": conds})
        n_k = entries({"combine": "K_OF_N", "k": 2, "conditions": conds})
        n_and = entries({"combine": "AND", "conditions": conds})
        assert n_and <= n_k <= n_or
        assert n_k != n_and or n_k != n_or, "k de n no aporta lógica nueva aquí"

    @pytest.mark.unit
    def test_k_at_the_extremes_is_rejected_as_a_duplicate_form(self):
        """Con k=1 sería un OR y con k=n un AND: admitirlos daría varios specs
        distintos para la misma estrategia, y el hash dejaría de identificarla."""
        conds = [_rsi(), _rsi("lt", 30.0), _rsi("lt", 25.0)]
        assert not validate_spec(_spec({"combine": "K_OF_N", "k": 1, "conditions": conds}))
        assert not validate_spec(_spec({"combine": "K_OF_N", "k": 3, "conditions": conds}))
        assert validate_spec(_spec({"combine": "K_OF_N", "k": 2, "conditions": conds}))

    @pytest.mark.unit
    def test_k_is_rejected_on_a_plain_and_or_block(self):
        conds = [_rsi(), _rsi("lt", 30.0)]
        assert not validate_spec(_spec({"combine": "AND", "k": 2, "conditions": conds}))

    @pytest.mark.unit
    def test_two_conditions_cannot_use_k_of_n(self):
        conds = [_rsi(), _rsi("lt", 30.0)]
        assert not validate_spec(_spec({"combine": "K_OF_N", "k": 2, "conditions": conds}))

    @pytest.mark.unit
    def test_the_description_states_the_confirmation_rule(self):
        conds = [_rsi(), _rsi("lt", 30.0), _rsi("lt", 25.0)]
        text = describe_spec(_spec({"combine": "K_OF_N", "k": 2, "conditions": conds}))
        assert "al menos 2 de:" in text

    @pytest.mark.unit
    def test_k_of_n_appears_in_the_random_population(self):
        rng = np.random.default_rng(1)
        found = sum(1 for _ in range(300)
                    for side in ("entry", "exit")
                    if (s := random_spec(rng))[side]["combine"] == "K_OF_N")
        assert found > 0


class TestEvolution:

    @pytest.mark.unit
    def test_mutation_never_produces_an_illegal_spec(self):
        rng = np.random.default_rng(2)
        spec = _spec({"combine": "AND", "conditions": [_rsi(), _rsi("lt", 30.0),
                                                       _rsi("lt", 25.0)]})
        for _ in range(500):
            spec = mutate(spec, rng)
            assert validate_spec(spec)

    @pytest.mark.unit
    def test_mutation_can_reach_and_leave_k_of_n(self):
        """Sin operador propio, «k de n» solo podría llegar del sorteo inicial y
        nunca desaparecer: media familia accesible únicamente por azar."""
        rng = np.random.default_rng(3)
        spec = _spec({"combine": "AND", "conditions": [_rsi(), _rsi("lt", 30.0),
                                                       _rsi("lt", 25.0)]})
        seen = set()
        for _ in range(400):
            spec = mutate(spec, rng)
            seen.add(spec["entry"]["combine"])
        assert "K_OF_N" in seen and len(seen) > 1

    @pytest.mark.unit
    def test_mutation_can_toggle_negation(self):
        rng = np.random.default_rng(4)
        spec = _spec({"combine": "AND", "conditions": [_rsi()]})
        seen = set()
        for _ in range(400):
            spec = mutate(spec, rng)
            seen.add(any(c.get("negate") for side in ("entry", "exit")
                         for c in spec[side]["conditions"]))
        assert seen == {True, False}

    @pytest.mark.unit
    def test_every_random_spec_stays_legal(self):
        rng = np.random.default_rng(5)
        assert all(validate_spec(random_spec(rng)) for _ in range(400))


class TestCatalogue:

    @pytest.mark.unit
    def test_the_fingerprint_covers_the_new_grammar(self):
        """Ampliar la gramática cambia lo que el generador puede descubrir: dos
        ejecuciones con la misma semilla dejan de ser comparables, y la huella
        debe delatarlo en vez de que pase inadvertido."""
        import core.domain.services.strategy_spec as spec_mod

        before = catalog_version()
        original = spec_mod.NEGATABLE
        spec_mod.NEGATABLE = ("threshold",)
        try:
            assert catalog_version() != before
        finally:
            spec_mod.NEGATABLE = original
        assert catalog_version() == before
