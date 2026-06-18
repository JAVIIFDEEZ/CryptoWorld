"""
strategy_nsga.py — Optimización multi-objetivo (NSGA-II) sobre StrategySpecs.

Alternativa al GA escalar (strategy_generator.evolve): en vez de un único fitness,
optimiza VARIOS objetivos en conflicto a la vez (p. ej. maximizar el Sharpe OOS,
minimizar el drawdown y minimizar el sobreajuste) y devuelve la FRONTERA DE PARETO
— el conjunto de estrategias en las que no se puede mejorar un objetivo sin empeorar
otro. Así el usuario elige el compromiso (más retorno vs menos riesgo) en vez de
imponérselo el algoritmo.

Implementa NSGA-II (Deb et al. 2002): ordenación por no-dominancia en frentes,
distancia de aglomeración (crowding) para la diversidad a lo largo de la frontera,
selección por torneo con el operador de comparación aglomerada y selección
ambiental elitista (padres+hijos → mejores N).

Reutiliza los operadores de cruce y mutación del GA escalar. Capa de dominio:
Python puro (sin dependencias externas de optimización).
"""

import copy
import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np

from core.domain.services.strategy_generator import (
    GAConfig, _initial_population, crossover, mutate,
)
from core.domain.services.strategy_spec import random_spec, spec_hash

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NSGAConfig:
    """Parámetros de NSGA-II (todos los objetivos se MAXIMIZAN; el caller invierte
    el signo de los que se minimizan, p. ej. drawdown)."""
    population_size: int = 40
    generations: int = 15
    crossover_rate: float = 0.7
    mutation_rate: float = 0.4
    tournament_size: int = 2
    seed_fraction: float = 0.25
    seed: int = 42


def dominates(a: tuple, b: tuple) -> bool:
    """a domina a b (maximización): a ≥ b en todos los objetivos y > en al menos uno."""
    return all(x >= y for x, y in zip(a, b)) and any(x > y for x, y in zip(a, b))


def fast_non_dominated_sort(objs: list[tuple]) -> list[list[int]]:
    """Ordena los índices en frentes de Pareto: F[0] = no dominados, F[1] = los que
    solo domina F[0], etc. (algoritmo de NSGA-II)."""
    n = len(objs)
    dominated: list[list[int]] = [[] for _ in range(n)]   # a quién domina cada i
    dom_count = [0] * n                                    # por cuántos es dominado i
    fronts: list[list[int]] = [[]]

    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            if dominates(objs[p], objs[q]):
                dominated[p].append(q)
            elif dominates(objs[q], objs[p]):
                dom_count[p] += 1
        if dom_count[p] == 0:
            fronts[0].append(p)

    i = 0
    while fronts[i]:
        nxt: list[int] = []
        for p in fronts[i]:
            for q in dominated[p]:
                dom_count[q] -= 1
                if dom_count[q] == 0:
                    nxt.append(q)
        i += 1
        fronts.append(nxt)
    return fronts[:-1]  # el último está vacío


def crowding_distance(front: list[int], objs: list[tuple]) -> dict[int, float]:
    """Distancia de aglomeración de cada individuo del frente: suma normalizada de
    las distancias a sus vecinos en cada objetivo. Los extremos = infinito (se
    conservan para no encoger la frontera)."""
    if not front:
        return {}
    dist = {i: 0.0 for i in front}
    m = len(objs[front[0]])
    for k in range(m):
        ordered = sorted(front, key=lambda i: objs[i][k])
        lo, hi = objs[ordered[0]][k], objs[ordered[-1]][k]
        span = hi - lo
        dist[ordered[0]] = dist[ordered[-1]] = float("inf")
        if span <= 0:
            continue
        for j in range(1, len(ordered) - 1):
            dist[ordered[j]] += (objs[ordered[j + 1]][k] - objs[ordered[j - 1]][k]) / span
    return dist


def evolve_nsga(objectives_fn: Callable[[dict], tuple], config: NSGAConfig | None = None) -> dict:
    """
    Evoluciona la población con NSGA-II y devuelve la frontera de Pareto.

    `objectives_fn(spec) -> tuple` con los objetivos a MAXIMIZAR (mayor es mejor en
    cada componente; invierte el signo de los que minimices). Se cachea por hash de
    spec, así un individuo no se reevalúa.

    Devuelve:
        {
          "pareto": [{spec, objectives, hash}, ...],   # frente no dominado final
          "history": [{generation, fronts, best_per_obj, n_pareto}, ...],
          "evaluations": int,
        }
    """
    cfg = config or NSGAConfig()
    rng = np.random.default_rng(cfg.seed)
    cache: dict[str, tuple] = {}

    def objs_of(spec: dict) -> tuple:
        h = spec_hash(spec)
        if h not in cache:
            cache[h] = tuple(float(x) for x in objectives_fn(spec))
        return cache[h]

    ga_cfg = GAConfig(population_size=cfg.population_size, seed_fraction=cfg.seed_fraction, seed=cfg.seed)
    pop = _initial_population(ga_cfg, rng)
    history: list[dict] = []

    def make_offspring(parents: list[dict], ranks: dict, crowd: dict) -> list[dict]:
        children: list[dict] = []
        while len(children) < cfg.population_size:
            p1 = _tournament(parents, ranks, crowd, rng)
            if rng.random() < cfg.crossover_rate:
                p2 = _tournament(parents, ranks, crowd, rng)
                child = crossover(p1, p2, rng)
            else:
                child = copy.deepcopy(p1)
            if rng.random() < cfg.mutation_rate:
                child = mutate(child, rng)
            children.append(child)
        return children

    for gen in range(cfg.generations):
        objs = [objs_of(s) for s in pop]
        fronts = fast_non_dominated_sort(objs)
        ranks = {i: r for r, fr in enumerate(fronts) for i in fr}
        crowd = {}
        for fr in fronts:
            crowd.update(crowding_distance(fr, objs))

        n_obj = len(objs[0]) if objs else 0
        history.append({
            "generation": gen,
            "n_fronts": len(fronts),
            "n_pareto": len(fronts[0]) if fronts else 0,
            "best_per_objective": [round(max(o[k] for o in objs), 4) for k in range(n_obj)] if objs else [],
        })

        if gen == cfg.generations - 1:
            break

        offspring = make_offspring(pop, ranks, crowd)
        # Selección ambiental: padres + hijos → mejores N por (frente, crowding)
        combined = _dedup(pop + offspring, rng, cfg.population_size * 2)
        c_objs = [objs_of(s) for s in combined]
        c_fronts = fast_non_dominated_sort(c_objs)
        next_pop: list[dict] = []
        for fr in c_fronts:
            if len(next_pop) + len(fr) <= cfg.population_size:
                next_pop.extend(combined[i] for i in fr)
            else:
                cd = crowding_distance(fr, c_objs)
                room = cfg.population_size - len(next_pop)
                chosen = sorted(fr, key=lambda i: cd[i], reverse=True)[:room]
                next_pop.extend(combined[i] for i in chosen)
                break
        pop = next_pop if next_pop else combined[:cfg.population_size]

    # Frontera de Pareto final (frente 0), deduplicada
    final_objs = [objs_of(s) for s in pop]
    fronts = fast_non_dominated_sort(final_objs)
    seen: set[str] = set()
    pareto = []
    for i in sorted(fronts[0], key=lambda i: final_objs[i][0], reverse=True) if fronts else []:
        h = spec_hash(pop[i])
        if h in seen:
            continue
        seen.add(h)
        pareto.append({"spec": pop[i], "objectives": [round(x, 4) for x in final_objs[i]], "hash": h})

    return {"pareto": pareto, "history": history, "evaluations": len(cache)}


def _tournament(pop: list[dict], ranks: dict, crowd: dict, rng: np.random.Generator) -> dict:
    """Torneo binario con el operador de comparación aglomerada: gana el de menor
    rango de frente; a igual rango, el de mayor distancia de aglomeración."""
    i, j = (int(x) for x in rng.integers(0, len(pop), size=2))
    ri, rj = ranks.get(i, 1_000), ranks.get(j, 1_000)
    if ri != rj:
        return pop[i] if ri < rj else pop[j]
    return pop[i] if crowd.get(i, 0.0) >= crowd.get(j, 0.0) else pop[j]


def _dedup(pop: list[dict], rng: np.random.Generator, target: int) -> list[dict]:
    """Elimina specs duplicados (mismo hash) y rellena con aleatorios hasta target."""
    seen: set[str] = set()
    unique: list[dict] = []
    for spec in pop:
        h = spec_hash(spec)
        if h not in seen:
            seen.add(h)
            unique.append(spec)
    while len(unique) < target:
        spec = random_spec(rng)
        h = spec_hash(spec)
        if h not in seen:
            seen.add(h)
            unique.append(spec)
    return unique[:target]
