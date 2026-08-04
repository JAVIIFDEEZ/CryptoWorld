"""
test_strategy_variants.py — Las correlacionadas dejan de tirarse.

Medido sobre una ejecución real del preset equilibrado: **cinco** estrategias
superaban el gating completo —holdout, CPCV y cascada de retests ya pagados— y
solo **dos** llegaban al informe. Las otras tres desaparecían dejando una línea
de texto con su hash.

El libro decorrelacionado sigue siendo lo correcto para el ranking: cinco formas
del mismo edge no diversifican. Pero correlacionar con otra no invalida una
estrategia — significa que explotan la misma fuente de retorno, y elegir entre
ellas (por caída máxima, por nº de operaciones, por rotación) es del usuario.

Se fija aquí que la variante conserve TODO lo que costó calcularla.
"""

import numpy as np
import pytest

from core.application.use_cases.generate_strategies import decorrelate_finalists


def _finalist(h, fitness, **extra):
    return {"spec_hash": h, "description": f"estrategia {h}", "fitness": fitness,
            "passed_gating": True,
            "gating": {"checks": {"pbo": True}, "metrics": {"sharpe": fitness}},
            "holdout_validation": {"return_pct": 5.0, "sharpe": 1.0},
            **extra}


def _series_fn(mapping):
    return lambda f: mapping[f["spec_hash"]]


@pytest.fixture
def scenario():
    """Tres estrategias: A y B casi idénticas, C independiente."""
    rng = np.random.default_rng(0)
    base = rng.normal(0, 0.01, 200)
    return {
        "A": base,
        "B": base + rng.normal(0, 0.0005, 200),   # clon estadístico de A
        "C": rng.normal(0, 0.01, 200),            # fuente distinta
    }


class TestVariants:

    @pytest.mark.unit
    def test_the_book_still_keeps_only_uncorrelated_sources(self, scenario):
        kept, dropped = decorrelate_finalists(
            [_finalist("A", 3.0), _finalist("B", 2.0), _finalist("C", 1.0)],
            _series_fn(scenario), 0.7)
        assert [f["spec_hash"] for f in kept] == ["A", "C"]
        assert len(dropped) == 1

    @pytest.mark.unit
    def test_the_correlated_one_survives_as_a_variant(self, scenario):
        """Antes desaparecía tras haber pagado su gating completo."""
        kept, _ = decorrelate_finalists(
            [_finalist("A", 3.0), _finalist("B", 2.0), _finalist("C", 1.0)],
            _series_fn(scenario), 0.7)
        parent = next(f for f in kept if f["spec_hash"] == "A")
        assert [v["spec_hash"] for v in parent["variants"]] == ["B"]

    @pytest.mark.unit
    def test_the_variant_keeps_its_full_metrics(self, scenario):
        """Si el usuario la prefiere, la tiene validada y no hay que rehacer
        nada. Guardar solo el hash obligaría a recalcular todo."""
        kept, _ = decorrelate_finalists(
            [_finalist("A", 3.0), _finalist("B", 2.0), _finalist("C", 1.0)],
            _series_fn(scenario), 0.7)
        variant = next(f for f in kept if f["spec_hash"] == "A")["variants"][0]
        assert variant["gating"]["metrics"]["sharpe"] == 2.0
        assert variant["holdout_validation"]["return_pct"] == 5.0
        assert variant["passed_gating"] is True

    @pytest.mark.unit
    def test_the_variant_says_how_correlated_it_is(self, scenario):
        """Sin la cifra, «variante» no es accionable: 0.72 y 0.99 son
        situaciones muy distintas."""
        kept, _ = decorrelate_finalists(
            [_finalist("A", 3.0), _finalist("B", 2.0)], _series_fn(scenario), 0.7)
        variant = kept[0]["variants"][0]
        assert abs(variant["correlation_with_parent"]) >= 0.7

    @pytest.mark.unit
    def test_an_independent_strategy_carries_no_variants(self, scenario):
        kept, _ = decorrelate_finalists(
            [_finalist("A", 3.0), _finalist("B", 2.0), _finalist("C", 1.0)],
            _series_fn(scenario), 0.7)
        assert next(f for f in kept if f["spec_hash"] == "C")["variants"] == []

    @pytest.mark.unit
    def test_variants_attach_to_the_one_they_actually_clash_with(self):
        """Con dos cabezas de libro, cada variante debe colgar de la suya: si
        todas se acumularan en la primera, el informe mentiría."""
        rng = np.random.default_rng(1)
        a = rng.normal(0, 0.01, 200)
        c = rng.normal(0, 0.01, 200)
        series = {"A": a, "C": c,
                  "A2": a + rng.normal(0, 0.0004, 200),
                  "C2": c + rng.normal(0, 0.0004, 200)}
        kept, _ = decorrelate_finalists(
            [_finalist("A", 4.0), _finalist("C", 3.0),
             _finalist("A2", 2.0), _finalist("C2", 1.0)],
            _series_fn(series), 0.7)
        by_hash = {f["spec_hash"]: f for f in kept}
        assert [v["spec_hash"] for v in by_hash["A"]["variants"]] == ["A2"]
        assert [v["spec_hash"] for v in by_hash["C"]["variants"]] == ["C2"]

    @pytest.mark.unit
    def test_the_dropped_list_is_preserved_for_the_audit_trail(self, scenario):
        """Las variantes son para usarlas; `dropped` sigue contando qué se
        apartó del libro y por qué, que es una pregunta distinta."""
        _, dropped = decorrelate_finalists(
            [_finalist("A", 3.0), _finalist("B", 2.0)], _series_fn(scenario), 0.7)
        assert dropped[0]["correlated_with"]["kept_hash"] == "A"

    @pytest.mark.unit
    def test_nothing_validated_is_lost(self, scenario):
        """La propiedad de fondo: toda estrategia que superó el gating sigue en
        el informe, como cabeza de libro o como variante."""
        passed = [_finalist("A", 3.0), _finalist("B", 2.0), _finalist("C", 1.0)]
        kept, _ = decorrelate_finalists(passed, _series_fn(scenario), 0.7)
        surfaced = {f["spec_hash"] for f in kept} | {
            v["spec_hash"] for f in kept for v in f["variants"]}
        assert surfaced == {"A", "B", "C"}
