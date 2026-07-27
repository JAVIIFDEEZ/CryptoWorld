"""
tests/unit/domain/test_strategy_nsga.py — Optimización multi-objetivo (NSGA-II).

Verifica las primitivas (dominancia, ordenación por frentes, crowding) y que
evolve_nsga devuelve una frontera de Pareto de specs legales.
"""

import numpy as np
import pytest

from core.domain.services import strategy_nsga as nsga
from core.domain.services.strategy_spec import validate_spec


class TestPrimitives:

    @pytest.mark.unit
    def test_dominance(self):
        assert nsga.dominates((2, 2), (1, 1)) is True
        assert nsga.dominates((2, 1), (1, 1)) is True       # mejor en uno, igual en otro
        assert nsga.dominates((2, 1), (1, 2)) is False      # trade-off: no domina
        assert nsga.dominates((1, 1), (1, 1)) is False      # iguales

    @pytest.mark.unit
    def test_non_dominated_sort_fronts(self):
        objs = [(2, 2), (1, 1), (2, 1), (1, 2)]
        fronts = nsga.fast_non_dominated_sort(objs)
        assert fronts[0] == [0]                  # (2,2) domina a todos
        assert set(fronts[1]) == {2, 3}          # trade-offs
        assert fronts[2] == [1]                  # (1,1) dominado por todos

    @pytest.mark.unit
    def test_crowding_extremes_are_infinite(self):
        objs = [(0.0, 1.0), (0.5, 0.5), (1.0, 0.0)]
        cd = nsga.crowding_distance([0, 1, 2], objs)
        assert cd[0] == float("inf") and cd[2] == float("inf")
        assert 0.0 <= cd[1] < float("inf")       # el central tiene distancia finita


class TestEvolveNSGA:

    @pytest.mark.unit
    def test_returns_valid_pareto_front(self):
        # Objetivos en conflicto a partir de la estructura del spec: nº de
        # condiciones de entrada vs de salida (subir uno tiende a no subir el otro).
        def objectives(spec):
            return (len(spec["entry"]["conditions"]), -len(spec["exit"]["conditions"]))

        res = nsga.evolve_nsga(objectives, nsga.NSGAConfig(population_size=24, generations=8, seed=1))
        assert len(res["pareto"]) >= 1
        assert all(validate_spec(p["spec"]) for p in res["pareto"])
        assert all(len(p["objectives"]) == 2 for p in res["pareto"])
        # La frontera no está dominada internamente
        objs = [tuple(p["objectives"]) for p in res["pareto"]]
        for a in objs:
            assert not any(nsga.dominates(b, a) for b in objs if b != a)

    @pytest.mark.unit
    def test_history_and_caching(self):
        calls = {"n": 0}

        def objectives(spec):
            calls["n"] += 1
            return (float(len(spec["entry"]["conditions"])), float(-len(spec["exit"]["conditions"])))

        res = nsga.evolve_nsga(objectives, nsga.NSGAConfig(population_size=20, generations=6, seed=4))
        assert len(res["history"]) == 6
        assert calls["n"] == res["evaluations"]   # cada spec distinto se evalúa una vez
