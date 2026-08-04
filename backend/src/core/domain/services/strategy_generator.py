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
    COMPARE_OPS,
    CROSS_OPS,
    OSCILLATORS,
    PATTERNS,
    SLOPE_OPS,
    THRESHOLD_OPS,
    _MAX_CONDITIONS,
    _random_pattern_condition,
    _random_regime,
    _random_risk,
    _random_sizing,
    _sample_params,
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
    # ── Grado StrategyQuant ─────────────────────────────────────────
    islands: int = 1              # subpoblaciones aisladas (modelo de islas)
    migration_every: int = 4      # cada cuántas generaciones migran los elites
    migration_k: int = 2          # nº de elites que migran al anillo siguiente
    stagnation_patience: int = 0  # gens sin mejora antes de hipermutar (0 = off)
    hypermutation_factor: float = 2.0  # multiplicador de mutación bajo estancamiento
    hof_size: int = 16            # hall of fame: mejores-de-siempre únicos


# ═══════════════════════════════════════════════════════════════════
# Operadores genéticos
# ═══════════════════════════════════════════════════════════════════

def crossover(parent_a: dict, parent_b: dict, rng: np.random.Generator) -> dict:
    """
    Cruce uniforme a nivel de bloque: el hijo hereda el bloque de entrada de un
    progenitor y el de salida del otro (elección aleatoria). Los bloques de
    riesgo/sizing/régimen se heredan de un progenitor al azar cada uno — antes
    se perdían siempre en el cruce y el GA no podía conservar una buena gestión
    de riesgo entre generaciones. Como cada bloque es independientemente legal,
    el hijo siempre es un spec válido.
    """
    if rng.random() < 0.5:
        entry, exit_ = parent_a["entry"], parent_b["exit"]
    else:
        entry, exit_ = parent_b["entry"], parent_a["exit"]
    child = {"entry": copy.deepcopy(entry), "exit": copy.deepcopy(exit_)}
    for block in ("risk", "sizing", "regime"):
        donor = parent_a if rng.random() < 0.5 else parent_b
        if donor.get(block):
            child[block] = copy.deepcopy(donor[block])
    return child


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


_OPS_BY_TYPE = {
    "threshold": THRESHOLD_OPS,
    "cross": CROSS_OPS,
    "compare": COMPARE_OPS,
    "slope": SLOPE_OPS,
}


def _mutate_flip_op(spec: dict, rng: np.random.Generator) -> dict:
    """Invierte el operador de una condición (gt↔lt, cross_above↔cross_below,
    above↔below o rising↔falling, según el tipo).

    Las condiciones de patrón no tienen operador que invertir: un suceso ocurre
    o no ocurre. Se excluyen de la selección en lugar de tratarlas aparte,
    porque su mutación propia es `_mutate_pattern`."""
    out = copy.deepcopy(spec)
    conds = [c for side in ("entry", "exit") for c in out[side]["conditions"]
             if c["type"] in _OPS_BY_TYPE]
    if not conds:
        return out
    c = conds[int(rng.integers(0, len(conds)))]
    ops = _OPS_BY_TYPE[c["type"]]
    c["op"] = ops[1] if c["op"] == ops[0] else ops[0]
    return out


def _mutate_pattern(spec: dict, rng: np.random.Generator) -> dict:
    """
    Cambia QUÉ patrón busca una condición de acción del precio.

    Es la mutación estructural de esta familia: el jitter ya afina parámetros y
    ventana, pero sin esto el GA no podría pasar de «barrida de mínimos» a
    «hueco de valor» sin destruir la condición entera y volver a sortearla. Con
    ella puede recorrer la familia conservando el resto del genoma, que es
    justo lo que hace útil una mutación dirigida.

    Si el spec no tiene ninguna condición de patrón, INTRODUCE una sustituyendo
    otra al azar: de lo contrario, un genoma que naciera sin patrones no podría
    adquirirlos nunca por esta vía.
    """
    out = copy.deepcopy(spec)
    targets = [(side, i) for side in ("entry", "exit")
               for i, c in enumerate(out[side]["conditions"]) if c["type"] == "pattern"]
    if targets:
        side, i = targets[int(rng.integers(0, len(targets)))]
        current = out[side]["conditions"][i]["pattern"]
        options = [p for p in PATTERNS if p != current]
        new_name = str(rng.choice(options)) if options else current
        out[side]["conditions"][i] = {
            "type": "pattern",
            "pattern": new_name,
            "params": _sample_params(PATTERNS[new_name]["params"], rng),
            "lookback": out[side]["conditions"][i].get("lookback", 1),
        }
        return out

    side = "entry" if rng.random() < 0.5 else "exit"
    conds = out[side]["conditions"]
    conds[int(rng.integers(0, len(conds)))] = _random_pattern_condition(rng)
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
    _mutate_pattern,
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

def _reproduce_island(
    ordered: list[dict],
    fitnesses: list[float],
    target: int,
    elitism: int,
    injection: int,
    mutation_rate: float,
    cfg: GAConfig,
    rng: np.random.Generator,
) -> list[dict]:
    """Una generación de reproducción dentro de una isla: elitismo + inyección
    de diversidad + torneo → cruce → mutación (con la tasa vigente, que puede
    estar hipermutada por estancamiento)."""
    next_pop: list[dict] = [copy.deepcopy(s) for s in ordered[:elitism]]
    next_pop.extend(random_spec(rng) for _ in range(injection))
    while len(next_pop) < target:
        parent = _tournament(ordered, fitnesses, cfg.tournament_size, rng)
        if rng.random() < cfg.crossover_rate:
            other = _tournament(ordered, fitnesses, cfg.tournament_size, rng)
            child = crossover(parent, other, rng)
        else:
            child = copy.deepcopy(parent)
        if rng.random() < mutation_rate:
            child = mutate(child, rng)
        next_pop.append(child)
    return _dedup(next_pop, target, rng)


def evolve(
    fitness_fn: Callable[[dict], float],
    config: GAConfig | None = None,
    on_generation: Callable[[dict], None] | None = None,
) -> dict:
    """
    Evoluciona la población y devuelve el resultado ordenado por fitness.

    `fitness_fn(spec) -> float`: mayor es mejor. El fitness se cachea por hash de
    spec, así un mismo individuo no se reevalúa (clave porque cada evaluación es
    un walk-forward completo). El elitismo garantiza que el mejor fitness sea
    monótonamente no decreciente entre generaciones.

    Grado StrategyQuant:
      · Modelo de islas: la población se reparte en `islands` subpoblaciones que
        evolucionan aisladas; cada `migration_every` generaciones los
        `migration_k` mejores de cada isla migran a la siguiente (anillo),
        preservando diversidad sin perder convergencia.
      · Hipermutación adaptativa: si el mejor global no mejora durante
        `stagnation_patience` generaciones, la tasa de mutación se multiplica por
        `hypermutation_factor` hasta que vuelva a mejorar (escape de óptimos
        locales; 0 = desactivado).
      · Hall of fame: los `hof_size` mejores specs ÚNICOS vistos en CUALQUIER
        generación, aunque luego se pierdan de la población.

    `on_generation(snapshot)`: callback opcional invocado al puntuar cada
    generación con {generation, generations_total, best, mean, diversity,
    island_best, mutation_rate, stagnation, hypermutation, top, evaluations}
    — es la fuente de la telemetría en vivo de la UI.

    Devuelve:
        {
          "best": {"spec", "fitness", "hash"},
          "population": [{"spec", "fitness", "hash"}, ...]  # ordenada desc
          "hall_of_fame": [{"spec", "fitness", "hash"}, ...],
          "history": [{"generation", "best", "mean", "diversity",
                       "island_best", "mutation_rate", "stagnation"}, ...],
          "evaluations": int,  # nº de specs distintos evaluados
          "islands": int,
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

    n_islands = max(1, min(cfg.islands, cfg.population_size // 6 or 1))
    initial = _initial_population(cfg, rng)
    # Reparto round-robin: cada isla arranca con mezcla de semillas y aleatorios.
    islands: list[list[dict]] = [initial[i::n_islands] for i in range(n_islands)]
    island_sizes = [len(isl) for isl in islands]
    elitism_per_island = max(1, cfg.elitism // n_islands)
    injection_per_island = max(1, cfg.random_injection // n_islands) if cfg.random_injection else 0

    hof: dict[str, dict] = {}      # hash → {"spec","fitness","hash"} mejores-de-siempre
    history: list[dict] = []
    best_ever = -np.inf
    stagnation = 0
    final_pop: list[dict] = []

    for gen in range(cfg.generations):
        # ── Puntuación por isla + actualización del hall of fame ─────
        scored_islands: list[list[tuple[float, dict]]] = []
        for isl in islands:
            scored = sorted(((fit(s), s) for s in isl), key=lambda x: x[0], reverse=True)
            scored_islands.append(scored)
            for f, s in scored[: max(2, elitism_per_island)]:
                h = spec_hash(s)
                if h not in hof or f > hof[h]["fitness"]:
                    hof[h] = {"spec": copy.deepcopy(s), "fitness": float(f), "hash": h}
        if len(hof) > cfg.hof_size:
            keep = sorted(hof.values(), key=lambda d: d["fitness"], reverse=True)[: cfg.hof_size]
            hof = {d["hash"]: d for d in keep}

        all_scored = sorted((p for sc in scored_islands for p in sc),
                            key=lambda x: x[0], reverse=True)
        fitnesses_all = [f for f, _ in all_scored]
        gen_best = fitnesses_all[0]
        island_best = [round(sc[0][0], 4) if sc else 0.0 for sc in scored_islands]

        # ── Estancamiento → hipermutación adaptativa ──────────────────
        if gen_best > best_ever + 1e-12:
            best_ever, stagnation = gen_best, 0
        else:
            stagnation += 1
        hyper = cfg.stagnation_patience > 0 and stagnation >= cfg.stagnation_patience
        mutation_rate = min(0.9, cfg.mutation_rate * (cfg.hypermutation_factor if hyper else 1.0))

        history.append({
            "generation": gen,
            "best": round(gen_best, 4),
            "mean": round(float(np.mean(fitnesses_all)), 4),
            "diversity": len({spec_hash(s) for _, s in all_scored}),
            "island_best": island_best,
            "mutation_rate": round(mutation_rate, 3),
            "stagnation": stagnation,
        })

        if on_generation is not None:
            on_generation({
                "generation": gen,
                "generations_total": cfg.generations,
                "best": round(gen_best, 4),
                "mean": history[-1]["mean"],
                "diversity": history[-1]["diversity"],
                "island_best": island_best,
                "mutation_rate": round(mutation_rate, 3),
                "stagnation": stagnation,
                "hypermutation": hyper,
                "top": [{"spec": s, "hash": spec_hash(s), "fitness": round(f, 4)}
                        for f, s in all_scored[:8]],
                "evaluations": len(cache),
            })

        # Última generación: no reproducimos, ya tenemos la población puntuada.
        if gen == cfg.generations - 1:
            final_pop = [s for _, s in all_scored]
            break

        # ── Reproducción por isla ─────────────────────────────────────
        islands = [
            _reproduce_island(
                [s for _, s in scored], [f for f, _ in scored],
                island_sizes[i], elitism_per_island, injection_per_island,
                mutation_rate, cfg, rng,
            )
            for i, scored in enumerate(scored_islands)
        ]

        # ── Migración en anillo entre islas ───────────────────────────
        if n_islands > 1 and (gen + 1) % cfg.migration_every == 0:
            migrants = [
                [copy.deepcopy(s) for _, s in scored_islands[i][: cfg.migration_k]]
                for i in range(n_islands)
            ]
            for i in range(n_islands):
                dest = (i + 1) % n_islands
                # Los migrantes reemplazan el final de la isla destino (los peores
                # tras la reproducción quedan al final por el dedup-refill).
                islands[dest] = _dedup(
                    migrants[i] + islands[dest], island_sizes[dest], rng,
                )

    final_scored = sorted(({"fitness": fit(s), "spec": s, "hash": spec_hash(s)} for s in final_pop),
                          key=lambda d: d["fitness"], reverse=True)
    # Deduplicar la población final por hash conservando el orden (mejor primero)
    seen: set[str] = set()
    population = []
    for item in final_scored:
        if item["hash"] not in seen:
            seen.add(item["hash"])
            item["fitness"] = round(item["fitness"], 4)
            population.append(item)

    hall_of_fame = sorted(hof.values(), key=lambda d: d["fitness"], reverse=True)
    for item in hall_of_fame:
        item["fitness"] = round(item["fitness"], 4)

    return {
        "best": population[0],
        "population": population,
        "hall_of_fame": hall_of_fame,
        "history": history,
        "evaluations": len(cache),
        "islands": n_islands,
    }
