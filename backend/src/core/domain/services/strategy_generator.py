"""
strategy_generator.py — Motor genético sobre StrategySpecs (Módulo 2, PASO 3).

Algoritmo genético clásico (Python puro, sin dependencias externas de GA) que
evoluciona una población de StrategySpecs componibles (Módulo 0). Implementa:
población inicial aleatoria + semillas, selección por torneo, cruce, mutación,
elitismo e inyección de diversidad.

El motor es agnóstico de la función de fitness: recibe `fitness_fn(spec)->float`
inyectada. El caso de uso le pasa el fitness robustez-aware de strategy_evaluation
(Sharpe OOS walk-forward penalizando sobreajuste y bajo nº de trades), de modo
que el GA NUNCA optimiza el retorno in-sample. Esta inyección mantiene el motor
puro y testeable con un fitness sintético.

Capa de dominio: Python puro, sin BD ni framework.
"""

import copy
import logging
from dataclasses import dataclass
from typing import Callable

import numpy as np

from core.domain.services.strategy_spec import (
    COMBINES,
    CROSS_OPS,
    OSCILLATORS,
    THRESHOLD_OPS,
    _MAX_CONDITIONS,
    _random_regime,
    _random_risk,
    _random_sizing,
    jitter_params,
    random_condition,
    random_spec,
    seed_specs,
    spec_hash,
    validate_spec,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GAConfig:
    """Parámetros del algoritmo genético (todos configurables)."""
    population_size: int = 40
    generations: int = 15
    crossover_rate: float = 0.7
    mutation_rate: float = 0.35
    elitism: int = 4              # nº de mejores que pasan intactos
    tournament_size: int = 3
    seed_fraction: float = 0.25   # fracción de la población inicial sembrada con clásicas
    random_injection: int = 2     # specs aleatorios inyectados cada generación (diversidad)
    seed: int = 42


# ═══════════════════════════════════════════════════════════════════
# Operadores genéticos
# ═══════════════════════════════════════════════════════════════════

def crossover(parent_a: dict, parent_b: dict, rng: np.random.Generator) -> dict:
    """
    Cruce uniforme a nivel de bloque: el hijo hereda el bloque de entrada de un
    progenitor y el de salida del otro (elección aleatoria). Como cada bloque es
    independientemente legal, el hijo siempre es un spec válido.
    """
    if rng.random() < 0.5:
        entry, exit_ = parent_a["entry"], parent_b["exit"]
    else:
        entry, exit_ = parent_b["entry"], parent_a["exit"]
    return {"entry": copy.deepcopy(entry), "exit": copy.deepcopy(exit_)}


def _mutate_condition_params(spec: dict, rng: np.random.Generator) -> dict:
    """Perturba los parámetros numéricos de una condición (±10% del rango)."""
    return jitter_params(spec, rng)


def _mutate_threshold(spec: dict, rng: np.random.Generator) -> dict:
    """Mueve el umbral de una condición de tipo threshold dentro de su rango."""
    out = copy.deepcopy(spec)
    thr_conds = [c for side in ("entry", "exit") for c in out[side]["conditions"]
                 if c["type"] == "threshold"]
    if not thr_conds:
        return out
    c = thr_conds[int(rng.integers(0, len(thr_conds)))]
    lo, hi = OSCILLATORS[c["indicator"]]["threshold"]
    span = (hi - lo) * 0.15
    c["threshold"] = round(float(min(hi, max(lo, c["threshold"] + rng.uniform(-span, span)))), 2)
    return out


def _mutate_flip_op(spec: dict, rng: np.random.Generator) -> dict:
    """Invierte el operador de una condición (gt↔lt o cross_above↔cross_below)."""
    out = copy.deepcopy(spec)
    conds = [c for side in ("entry", "exit") for c in out[side]["conditions"]]
    c = conds[int(rng.integers(0, len(conds)))]
    if c["type"] == "threshold":
        c["op"] = THRESHOLD_OPS[1] if c["op"] == THRESHOLD_OPS[0] else THRESHOLD_OPS[0]
    else:
        c["op"] = CROSS_OPS[1] if c["op"] == CROSS_OPS[0] else CROSS_OPS[0]
    return out


def _mutate_flip_combine(spec: dict, rng: np.random.Generator) -> dict:
    """Cambia el combinador AND↔OR de un bloque al azar."""
    out = copy.deepcopy(spec)
    side = "entry" if rng.random() < 0.5 else "exit"
    block = out[side]
    block["combine"] = COMBINES[1] if block["combine"] == COMBINES[0] else COMBINES[0]
    return out


def _mutate_replace_condition(spec: dict, rng: np.random.Generator) -> dict:
    """Sustituye una condición por una nueva condición aleatoria legal."""
    out = copy.deepcopy(spec)
    side = "entry" if rng.random() < 0.5 else "exit"
    conds = out[side]["conditions"]
    conds[int(rng.integers(0, len(conds)))] = random_condition(rng)
    return out


def _mutate_add_condition(spec: dict, rng: np.random.Generator) -> dict:
    """Añade una condición a un bloque (si no ha llegado al máximo)."""
    out = copy.deepcopy(spec)
    side = "entry" if rng.random() < 0.5 else "exit"
    if len(out[side]["conditions"]) < _MAX_CONDITIONS:
        out[side]["conditions"].append(random_condition(rng))
    return out


def _mutate_remove_condition(spec: dict, rng: np.random.Generator) -> dict:
    """Elimina una condición de un bloque (si le queda más de una)."""
    out = copy.deepcopy(spec)
    side = "entry" if rng.random() < 0.5 else "exit"
    if len(out[side]["conditions"]) > 1:
        out[side]["conditions"].pop(int(rng.integers(0, len(out[side]["conditions"]))))
    return out


def _mutate_risk(spec: dict, rng: np.random.Generator) -> dict:
    """Evoluciona la gestión de riesgo: añade, quita o perturba stop/objetivo."""
    out = copy.deepcopy(spec)
    if out.get("risk") and rng.random() < 0.35:
        out.pop("risk")                      # quitar la gestión de riesgo
    else:
        new_risk = _random_risk(rng)         # reemplazar por una nueva (o None)
        if new_risk:
            out["risk"] = new_risk
        else:
            out.pop("risk", None)
    return out


def _mutate_sizing(spec: dict, rng: np.random.Generator) -> dict:
    """Evoluciona el dimensionamiento: cuánto capital arriesgar por operación."""
    out = copy.deepcopy(spec)
    new_sizing = _random_sizing(rng)
    if new_sizing:
        out["sizing"] = new_sizing
    else:
        out.pop("sizing", None)              # volver a invertir todo
    return out


def _mutate_regime(spec: dict, rng: np.random.Generator) -> dict:
    """Evoluciona el filtro de régimen: exigir tendencia (ADX) para entrar, o no."""
    out = copy.deepcopy(spec)
    new_regime = _random_regime(rng)
    if new_regime:
        out["regime"] = new_regime
    else:
        out.pop("regime", None)              # quitar el filtro de régimen
    return out


_MUTATORS: list[Callable[[dict, np.random.Generator], dict]] = [
    _mutate_condition_params,
    _mutate_threshold,
    _mutate_flip_op,
    _mutate_flip_combine,
    _mutate_replace_condition,
    _mutate_add_condition,
    _mutate_remove_condition,
    _mutate_risk,
    _mutate_sizing,
    _mutate_regime,
]


def mutate(spec: dict, rng: np.random.Generator) -> dict:
    """
    Aplica un operador de mutación al azar. Si el resultado no es legal (caso
    raro, p. ej. un cruce que colisiona consigo mismo), reintenta con otro
    operador; si nada funciona, devuelve el spec original intacto.
    """
    order = rng.permutation(len(_MUTATORS))
    for idx in order:
        candidate = _MUTATORS[idx](spec, rng)
        if validate_spec(candidate):
            return candidate
    return spec


# ═══════════════════════════════════════════════════════════════════
# Selección y población
# ═══════════════════════════════════════════════════════════════════

def _tournament(pop: list[dict], fitnesses: list[float], k: int, rng: np.random.Generator) -> dict:
    """Selección por torneo: gana el de mayor fitness entre k candidatos."""
    idx = rng.integers(0, len(pop), size=min(k, len(pop)))
    best = max(idx, key=lambda i: fitnesses[i])
    return pop[best]


def _initial_population(config: GAConfig, rng: np.random.Generator) -> list[dict]:
    """
    Población inicial: una fracción sembrada con las 5 estrategias clásicas y sus
    vecinos (warm start), el resto aleatoria. Se deduplica por hash para arrancar
    con diversidad real.
    """
    pop: list[dict] = []
    seeds = seed_specs()
    n_seeded = min(len(seeds), int(round(config.population_size * config.seed_fraction)))
    pop.extend(seeds[:n_seeded])
    # Vecinos jitter de las semillas para explorar su entorno
    while len(pop) < n_seeded * 2 and len(pop) < config.population_size:
        pop.append(jitter_params(seeds[int(rng.integers(0, len(seeds)))], rng))
    while len(pop) < config.population_size:
        pop.append(random_spec(rng))
    return _dedup(pop, config.population_size, rng)


def _dedup(pop: list[dict], target: int, rng: np.random.Generator) -> list[dict]:
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


# ═══════════════════════════════════════════════════════════════════
# Bucle evolutivo
# ═══════════════════════════════════════════════════════════════════

def evolve(fitness_fn: Callable[[dict], float], config: GAConfig | None = None) -> dict:
    """
    Evoluciona la población y devuelve el resultado ordenado por fitness.

    `fitness_fn(spec) -> float`: mayor es mejor. El fitness se cachea por hash de
    spec, así un mismo individuo no se reevalúa (clave porque cada evaluación es
    un walk-forward completo). El elitismo garantiza que el mejor fitness sea
    monótonamente no decreciente entre generaciones.

    Devuelve:
        {
          "best": {"spec", "fitness", "hash"},
          "population": [{"spec", "fitness", "hash"}, ...]  # ordenada desc
          "history": [{"generation", "best", "mean", "diversity"}, ...],
          "evaluations": int,  # nº de specs distintos evaluados
        }
    """
    cfg = config or GAConfig()
    rng = np.random.default_rng(cfg.seed)
    cache: dict[str, float] = {}

    def fit(spec: dict) -> float:
        h = spec_hash(spec)
        if h not in cache:
            cache[h] = float(fitness_fn(spec))
        return cache[h]

    pop = _initial_population(cfg, rng)
    history: list[dict] = []

    for gen in range(cfg.generations):
        scored = sorted(((fit(s), s) for s in pop), key=lambda x: x[0], reverse=True)
        fitnesses = [f for f, _ in scored]
        ordered = [s for _, s in scored]

        history.append({
            "generation": gen,
            "best": round(fitnesses[0], 4),
            "mean": round(float(np.mean(fitnesses)), 4),
            "diversity": len({spec_hash(s) for s in ordered}),
        })

        # Última generación: no reproducimos, ya tenemos la población final puntuada.
        if gen == cfg.generations - 1:
            pop = ordered
            break

        # Elitismo + inyección de diversidad
        next_pop: list[dict] = [copy.deepcopy(s) for s in ordered[:cfg.elitism]]
        next_pop.extend(random_spec(rng) for _ in range(cfg.random_injection))

        # Resto por torneo → cruce → mutación
        while len(next_pop) < cfg.population_size:
            parent = _tournament(ordered, fitnesses, cfg.tournament_size, rng)
            if rng.random() < cfg.crossover_rate:
                other = _tournament(ordered, fitnesses, cfg.tournament_size, rng)
                child = crossover(parent, other, rng)
            else:
                child = copy.deepcopy(parent)
            if rng.random() < cfg.mutation_rate:
                child = mutate(child, rng)
            next_pop.append(child)

        pop = _dedup(next_pop, cfg.population_size, rng)

    final_scored = sorted(({"fitness": fit(s), "spec": s, "hash": spec_hash(s)} for s in pop),
                          key=lambda d: d["fitness"], reverse=True)
    # Deduplicar la población final por hash conservando el orden (mejor primero)
    seen: set[str] = set()
    population = []
    for item in final_scored:
        if item["hash"] not in seen:
            seen.add(item["hash"])
            item["fitness"] = round(item["fitness"], 4)
            population.append(item)

    return {
        "best": population[0],
        "population": population,
        "history": history,
        "evaluations": len(cache),
    }
