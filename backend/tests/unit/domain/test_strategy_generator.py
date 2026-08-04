"""
tests/unit/domain/test_strategy_generator.py — Motor genético (Módulo 2, PASO 3).

Verifica el criterio del PASO 7: el GA mejora el fitness a lo largo de las
generaciones en un caso sintético con señal conocida, mantiene la población
legal y preserva la diversidad. Se usa un fitness sintético (no el backtest)
para aislar el motor.
"""

import numpy as np
import pytest

from core.domain.services import strategy_generator as ga
from core.domain.services.strategy_spec import validate_spec


def _known_signal_fitness(spec: dict) -> float:
    """
    Fitness sintético con óptimo conocido: premia entrar con RSI<umbral bajo y
    salir con RSI>umbral alto (la lógica de reversión a la media). Un GA que
    funciona debe converger hacia esa estructura.

    Una condición NEGADA no cuenta: «NO (RSI<30)» es lo contrario de lo que se
    premia, y puntuarla igual dejaría el óptimo mal definido — el GA podría
    subir de nota escribiendo justo la estrategia opuesta.
    """
    def counts(c: dict, op: str) -> bool:
        return (c.get("type") == "threshold" and c.get("indicator") == "RSI"
                and c["op"] == op and not c.get("negate"))

    score = 0.0
    for c in spec["entry"]["conditions"]:
        if counts(c, "lt"):
            score += 2.0 - c["threshold"] / 100.0
    for c in spec["exit"]["conditions"]:
        if counts(c, "gt"):
            score += 1.0 + c["threshold"] / 100.0
    return score


class TestEvolution:

    @pytest.mark.unit
    def test_best_fitness_improves_across_generations(self):
        cfg = ga.GAConfig(population_size=30, generations=12, seed=1)
        res = ga.evolve(_known_signal_fitness, cfg)
        history = res["history"]
        best = [h["best"] for h in history]
        # Elitismo ⇒ el mejor nunca empeora
        assert all(b2 >= b1 for b1, b2 in zip(best, best[1:]))
        # En un problema con señal, debe mejorar estrictamente de principio a fin
        assert best[-1] > best[0]

    @pytest.mark.unit
    def test_final_population_is_all_legal(self):
        res = ga.evolve(_known_signal_fitness, ga.GAConfig(population_size=24, generations=6, seed=2))
        assert len(res["population"]) >= 5
        assert all(validate_spec(p["spec"]) for p in res["population"])

    @pytest.mark.unit
    def test_best_spec_uses_the_rewarded_structure(self):
        res = ga.evolve(_known_signal_fitness, ga.GAConfig(population_size=40, generations=15, seed=3))
        best_spec = res["best"]["spec"]
        has_rsi_lt = any(
            c.get("indicator") == "RSI" and c.get("op") == "lt"
            for c in best_spec["entry"]["conditions"]
        )
        assert has_rsi_lt, "el GA debería descubrir la entrada RSI<umbral premiada"

    @pytest.mark.unit
    def test_fitness_is_cached_by_hash(self):
        calls = {"n": 0}

        def counting_fitness(spec):
            calls["n"] += 1
            return _known_signal_fitness(spec)

        cfg = ga.GAConfig(population_size=20, generations=8, seed=4)
        res = ga.evolve(counting_fitness, cfg)
        # Cada spec distinto se evalúa una sola vez: nº de llamadas == nº de hashes únicos
        assert calls["n"] == res["evaluations"]

    @pytest.mark.unit
    def test_determinism_same_seed(self):
        a = ga.evolve(_known_signal_fitness, ga.GAConfig(seed=7, generations=5, population_size=20))
        b = ga.evolve(_known_signal_fitness, ga.GAConfig(seed=7, generations=5, population_size=20))
        assert a["best"]["hash"] == b["best"]["hash"]
        assert a["best"]["fitness"] == b["best"]["fitness"]


class TestOperators:

    @pytest.mark.unit
    def test_crossover_produces_valid_child(self):
        rng = np.random.default_rng(0)
        from core.domain.services.strategy_spec import seed_specs
        seeds = seed_specs()
        for _ in range(50):
            a, b = rng.choice(len(seeds), 2, replace=False)
            child = ga.crossover(seeds[a], seeds[b], rng)
            assert validate_spec(child)

    @pytest.mark.unit
    def test_mutation_always_returns_valid_spec(self):
        rng = np.random.default_rng(1)
        from core.domain.services.strategy_spec import random_spec
        for _ in range(100):
            spec = random_spec(rng)
            mutated = ga.mutate(spec, rng)
            assert validate_spec(mutated)


class TestStrategyQuantGrade:
    """Capacidades de grado StrategyQuant: islas, hipermutación, hall of fame
    y telemetría por generación (on_generation)."""

    @pytest.mark.unit
    def test_island_model_runs_and_reports(self):
        cfg = ga.GAConfig(population_size=30, generations=10, seed=3,
                          islands=3, migration_every=3, migration_k=2)
        res = ga.evolve(_known_signal_fitness, cfg)
        assert res["islands"] == 3
        # La historia registra el mejor de CADA isla en cada generación
        assert all(len(h["island_best"]) == 3 for h in res["history"])
        # Elitismo global: el mejor sigue sin empeorar
        best = [h["best"] for h in res["history"]]
        assert all(b2 >= b1 for b1, b2 in zip(best, best[1:]))
        assert best[-1] > best[0]

    @pytest.mark.unit
    def test_island_model_deterministic(self):
        cfg = ga.GAConfig(population_size=24, generations=6, seed=11, islands=2)
        a = ga.evolve(_known_signal_fitness, cfg)
        b = ga.evolve(_known_signal_fitness, cfg)
        assert a["best"]["hash"] == b["best"]["hash"]
        assert [h["best"] for h in a["history"]] == [h["best"] for h in b["history"]]

    @pytest.mark.unit
    def test_hall_of_fame_holds_best_ever(self):
        cfg = ga.GAConfig(population_size=24, generations=8, seed=5, hof_size=10)
        res = ga.evolve(_known_signal_fitness, cfg)
        hof = res["hall_of_fame"]
        assert 0 < len(hof) <= 10
        # Ordenado desc y sin duplicados
        fits = [h["fitness"] for h in hof]
        assert fits == sorted(fits, reverse=True)
        assert len({h["hash"] for h in hof}) == len(hof)
        # El campeón del HoF es al menos tan bueno como el mejor de la población final
        assert hof[0]["fitness"] >= res["population"][0]["fitness"]

    @pytest.mark.unit
    def test_hypermutation_kicks_in_on_stagnation(self):
        # Fitness constante: no hay mejora posible ⇒ estancamiento garantizado
        cfg = ga.GAConfig(population_size=20, generations=8, seed=2,
                          stagnation_patience=2, hypermutation_factor=2.0,
                          mutation_rate=0.3)
        res = ga.evolve(lambda spec: 1.0, cfg)
        rates = [h["mutation_rate"] for h in res["history"]]
        assert rates[0] == pytest.approx(0.3, abs=1e-9)      # arranque normal
        assert max(rates) == pytest.approx(0.6, abs=1e-9)    # hipermutación ×2
        assert max(h["stagnation"] for h in res["history"]) >= 2

    @pytest.mark.unit
    def test_on_generation_telemetry(self):
        snapshots = []
        cfg = ga.GAConfig(population_size=20, generations=6, seed=9, islands=2)
        ga.evolve(_known_signal_fitness, cfg, on_generation=snapshots.append)
        assert len(snapshots) == 6
        assert [s["generation"] for s in snapshots] == list(range(6))
        for s in snapshots:
            assert s["generations_total"] == 6
            assert len(s["top"]) > 0
            assert all({"spec", "hash", "fitness"} <= set(t) for t in s["top"])
            assert all(validate_spec(t["spec"]) for t in s["top"])
