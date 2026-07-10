"""
generate_strategies.py — Caso de uso: generador de estrategias por GA (Módulo 2).

Orquesta el algoritmo genético (dominio) con la suite de robustez (Módulo 1) y
materializa el principio anti data-snooping:

  ┌──────────────── serie temporal OHLCV ────────────────┐
  │  EVOLUCIÓN (1-holdout)              │  VALIDACIÓN FINAL │
  │  · fitness = Sharpe OOS walk-forward (penaliza        │  (intacta: NO se
  │    sobreajuste y bajo nº de trades)                    │   ve en la
  │  · gating de robustez (PBO, lookahead, MC, eficiencia)│   evolución ni en
  │                                                        │   el walk-forward)
  └────────────────────────────────────────────────────────────────────────┘

La partición de validación final (holdout) NO interviene ni en el fitness del GA
ni en el walk-forward ni en el gating: los finalistas se re-evalúan sobre ella
solo para REPORTAR su rendimiento en datos jamás vistos. La selección y el
ranking se deciden con métricas de la zona de evolución, de modo que el holdout
nunca contamina la elección (eso sería, en sí mismo, data-snooping).

`generate_strategies(df, ...)` es puro (solo dominio) y testeable sin red ni
Celery. `GenerateStrategiesUseCase` lo envuelve obteniendo el OHLCV y persistiendo
los finalistas robustos como StrategyDefinition (Módulo 0).
"""

import logging
from dataclasses import asdict, dataclass

import numpy as np

from core.domain.services import backtest_metrics as metrics
from core.domain.services.backtest_execution import CostModel
from core.domain.services.strategy_evaluation import (
    GatingThresholds,
    equity_curve,
    evaluate_fitness,
    gate_spec,
    holdout_performance,
    returns_series,
)
from core.domain.services.strategy_generator import GAConfig, evolve
from core.domain.services.strategy_nsga import NSGAConfig, evolve_nsga
from core.domain.services.strategy_spec import describe_spec, spec_hash

logger = logging.getLogger(__name__)

# Velas mínimas: tras reservar el holdout, la zona de evolución aún necesita
# varios tramos walk-forward con tamaño suficiente.
MIN_CANDLES = 300


@dataclass(frozen=True)
class GenerationConfig:
    """Parámetros del generador (GA + gating + partición), todos configurables."""
    holdout_fraction: float = 0.2      # tramo de validación final reservado
    top_k: int = 5                     # nº de finalistas robustos a reportar
    max_gating_attempts: int = 12      # tope de candidatos a pasar por el gating (coste)
    commission_bps: float = 10.0       # comisión por lado (realismo de costes)
    slippage_bps: float = 5.0          # deslizamiento por lado
    optimizer: str = "single"          # "single" (fitness escalar) | "nsga" (multi-objetivo)
    parsimony: float = 0.0             # presión de simplicidad (por condición > 3)
    # ── Rendimiento del generador (más estrategias rentables por ejecución) ──
    max_restarts: int = 1              # rondas de evolución con semilla fresca hasta llenar el cupo
    refine_neighbors: int = 0          # vecinos jitter para refinar cada finalista (0 = off)
    correlation_threshold: float = 0.7  # |ρ| máx. entre finalistas del libro (decorrelación)
    ga: GAConfig = GAConfig()
    gating: GatingThresholds = GatingThresholds()


# Presets de cómputo: el GA hace cientos de walk-forwards, así que el usuario
# elige cuánto exhaustividad/espera quiere. Los tres activan el grado
# StrategyQuant: hipermutación anti-estancamiento y presión de parsimonia;
# balanced/thorough añaden el modelo de islas con migración.
_PRESETS = {
    "fast": GenerationConfig(
        top_k=3, max_gating_attempts=6, parsimony=0.03,
        max_restarts=1, refine_neighbors=0,
        ga=GAConfig(population_size=24, generations=8, elitism=3, random_injection=2,
                    stagnation_patience=3),
        gating=GatingThresholds(wf_splits=3, pbo_neighbors=8, mc_sims=200),
    ),
    "balanced": GenerationConfig(
        top_k=5, max_gating_attempts=12, parsimony=0.03,
        max_restarts=2, refine_neighbors=5,
        ga=GAConfig(population_size=40, generations=15, elitism=4, random_injection=2,
                    islands=2, migration_every=4, stagnation_patience=4),
        gating=GatingThresholds(wf_splits=4, pbo_neighbors=12, mc_sims=400),
    ),
    "thorough": GenerationConfig(
        top_k=6, max_gating_attempts=18, parsimony=0.03,
        max_restarts=3, refine_neighbors=8,
        ga=GAConfig(population_size=60, generations=25, elitism=6, random_injection=3,
                    islands=3, migration_every=4, stagnation_patience=4, hof_size=24),
        gating=GatingThresholds(wf_splits=4, pbo_neighbors=16, mc_sims=800),
    ),
}
DEFAULT_PRESET = "balanced"


def config_for_preset(preset: str) -> GenerationConfig:
    return _PRESETS.get(preset, _PRESETS[DEFAULT_PRESET])


def _json_safe(value):
    """inf/nan → None recursivamente (el payload pasa por JSON DRF/Celery-Redis)."""
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _run_nsga(df_evo, cfg: "GenerationConfig", ppy: float, costs, on_generation=None):
    """
    Optimización multi-objetivo: maximizar Sharpe OOS, minimizar drawdown y
    minimizar sobreajuste. Devuelve los specs de la frontera de Pareto (como
    candidatos a gating), la historia para la visualización, el nº de
    evaluaciones y la frontera con sus objetivos.
    """
    def objectives(spec: dict) -> tuple:
        ev = evaluate_fitness(df_evo, spec, n_splits=cfg.gating.wf_splits, ppy=ppy,
                              costs=costs, parsimony=cfg.parsimony)
        if ev["n_trades"] < 8 or ev["efficiency"] == 0:
            return (-99.0, -99.0, -99.0)            # degeneradas: dominadas por todo
        return (ev["mean_oos_sharpe"], -ev["max_drawdown_pct"] / 100.0, -ev["overfit_gap"])

    nsga_cfg = NSGAConfig(
        population_size=cfg.ga.population_size,
        generations=cfg.ga.generations,
        crossover_rate=cfg.ga.crossover_rate,
        mutation_rate=cfg.ga.mutation_rate,
        seed_fraction=cfg.ga.seed_fraction,
        seed=cfg.ga.seed,
    )
    res = evolve_nsga(objectives, nsga_cfg, on_generation=on_generation)

    candidate_specs = [{"spec": p["spec"], "fitness": p["objectives"][0]} for p in res["pareto"]]
    history = [
        {"generation": h["generation"],
         "best": h["best_per_objective"][0] if h["best_per_objective"] else 0.0,
         "mean": float(h["n_pareto"]),
         "diversity": h["n_pareto"]}
        for h in res["history"]
    ]
    frontier = [
        {"spec_hash": p["hash"], "description": describe_spec(p["spec"]),
         "oos_sharpe": p["objectives"][0],
         "max_drawdown_pct": round(-p["objectives"][1] * 100.0, 2),
         "overfit_gap": round(-p["objectives"][2], 4)}
        for p in res["pareto"]
    ]
    return candidate_specs, history, res["evaluations"], frontier


def _partition(df, holdout_fraction: float):
    """Corte temporal: [evolución | validación final]. El holdout es el tramo
    MÁS RECIENTE, jamás visto durante la evolución (anti data-snooping)."""
    n = len(df)
    split = int(round(n * (1.0 - holdout_fraction)))
    split = max(MIN_CANDLES // 2, min(split, n - 30))  # garantiza ambos tramos usables
    df_evo = df.iloc[:split].reset_index(drop=True)
    df_holdout = df.iloc[split:].reset_index(drop=True)
    return df_evo, df_holdout, split


def decorrelate_finalists(passed: list[dict], series_fn, threshold: float) -> tuple[list, list]:
    """
    Libro decorrelacionado: recorre las finalistas por fitness descendente y
    conserva cada una solo si su serie de retornos tiene |ρ| < `threshold` con
    TODAS las ya conservadas (greedy). Las descartadas son clones estadísticos
    del mismo edge: un libro institucional quiere fuentes de retorno distintas.

    `series_fn(finalist) -> np.ndarray` inyectable (testeable sin backtests).
    Devuelve (conservadas, descartadas_con_motivo).
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    for f in sorted(passed, key=lambda x: x["fitness"], reverse=True):
        r = np.asarray(series_fn(f), dtype=float)
        clash = None
        for k in kept:
            rk = np.asarray(series_fn(k), dtype=float)
            n = min(r.size, rk.size)
            if n < 20:
                continue
            a, b = r[:n], rk[:n]
            if a.std() < 1e-12 or b.std() < 1e-12:
                continue
            corr = float(np.corrcoef(a, b)[0, 1])
            if abs(corr) >= threshold:
                clash = {"kept_hash": k["spec_hash"], "kept_description": k["description"],
                         "corr": round(corr, 3)}
                break
        if clash is None:
            kept.append(f)
        else:
            dropped.append({"spec_hash": f["spec_hash"], "description": f["description"],
                            "fitness": f["fitness"], "correlated_with": clash})
    return kept, dropped


def generate_strategies(
    df,
    interval: str = "1d",
    config: GenerationConfig | None = None,
    initial_capital: float = 10000.0,
    progress_cb=None,
) -> dict:
    """
    Genera estrategias por GA y devuelve el informe con el ranking de finalistas
    que pasan el gating de robustez. Función pura (solo dominio).

    `progress_cb(snapshot)` (opcional): telemetría en vivo. Se invoca al cerrar
    cada generación con la convergencia acumulada y las CURVAS DE EQUITY de los
    mejores candidatos (calculadas SOLO sobre la zona de evolución: el holdout
    jamás aparece en la telemetría), y durante el gating con su avance. Fases:
    "evolving" → "gating" → "done".
    """
    cfg = config or GenerationConfig()
    ppy = metrics.annualization_factor(interval)
    costs = CostModel(commission_bps=cfg.commission_bps, slippage_bps=cfg.slippage_bps)

    # ── PASO 5: partición anti data-snooping ──────────────────────────
    df_evo, df_holdout, split = _partition(df, cfg.holdout_fraction)

    # ── Telemetría en vivo: curvas de equity por candidato (cacheadas) ─
    equity_cache: dict[str, dict] = {}
    live_history: list[dict] = []

    def _candidate_card(entry: dict) -> dict:
        h = entry["hash"]
        if h not in equity_cache:
            equity_cache[h] = equity_curve(df_evo, entry["spec"], costs=costs)
        return {
            "hash": h,
            "description": describe_spec(entry["spec"]),
            "fitness": entry["fitness"],
            **equity_cache[h],
        }

    # Estado de la ronda actual (búsqueda hasta objetivo): las generaciones de
    # rondas sucesivas se encadenan en la historia con un offset para que la
    # convergencia en vivo sea una sola línea temporal continua.
    restart_state = {"n": 1, "total": max(1, cfg.max_restarts), "gen_offset": 0}

    def _on_generation(snap: dict) -> None:
        live_history.append({
            "generation": restart_state["gen_offset"] + snap["generation"],
            "best": snap["best"], "mean": snap["mean"], "diversity": snap["diversity"],
        })
        if progress_cb is None:
            return
        top_cards = [_candidate_card(e) for e in snap.get("top", [])[:6]]
        progress_cb(_json_safe({
            "phase": "evolving",
            "generation": snap["generation"],
            "generations_total": snap["generations_total"],
            "restart": restart_state["n"],
            "restarts_total": restart_state["total"],
            "best": snap["best"],
            "mean": snap["mean"],
            "diversity": snap["diversity"],
            "island_best": snap.get("island_best", []),
            "mutation_rate": snap.get("mutation_rate"),
            "stagnation": snap.get("stagnation", 0),
            "hypermutation": snap.get("hypermutation", False),
            "evaluations": snap.get("evaluations", 0),
            "history": list(live_history),
            "top": top_cards,
        }))

    # ── Fitness compartido entre rondas: un genoma ya evaluado en cualquier
    # ronda no se reevalúa jamás (cada evaluación es un walk-forward completo).
    fitness_memo: dict[str, float] = {}

    def fitness_fn(spec: dict) -> float:
        h = spec_hash(spec)
        if h not in fitness_memo:
            fitness_memo[h] = evaluate_fitness(
                df_evo, spec, n_splits=cfg.gating.wf_splits, ppy=ppy,
                costs=costs, parsimony=cfg.parsimony)["fitness"]
        return fitness_memo[h]

    def _gate_candidate(cand: dict) -> dict:
        """Gating + holdout de una candidata → dict de finalista completo."""
        spec = cand["spec"]
        gate = gate_spec(df_evo, spec, cfg.gating, ppy=ppy, costs=costs)
        holdout = holdout_performance(df_holdout, spec, ppy=ppy, costs=costs)
        return {
            "spec": spec,
            "spec_hash": spec_hash(spec),
            "description": describe_spec(spec),
            "fitness": cand["fitness"],
            "passed_gating": gate["passed"],
            "gating": {"checks": gate["checks"], "metrics": gate["metrics"]},
            "evolution_metrics": {
                "fitness": cand["fitness"],
                "wf_efficiency": gate["metrics"]["wf_efficiency"],
                "mean_oos_sharpe": gate["metrics"]["mean_oos_sharpe"],
                "pbo": gate["metrics"]["pbo"],
            },
            "holdout_validation": holdout,
        }

    # El filtro de correlación puede descartar aprobadas, así que el gating
    # apunta a un pequeño colchón por encima del cupo del ranking.
    cushion = 2 if cfg.correlation_threshold < 1.0 else 0
    target_passed = cfg.top_k + cushion

    # ── PASO 3+4: evolución → gating, en rondas hasta llenar el cupo ──
    # "single": fitness escalar robustez-aware, con BÚSQUEDA HASTA OBJETIVO:
    # si una ronda no llena el cupo de finalistas robustas, se relanza la
    # evolución con semilla fresca (nueva región del espacio) reutilizando el
    # fitness ya calculado. "nsga": multi-objetivo, una única ronda.
    pareto_frontier: list[dict] = []
    hall_of_fame: list[dict] = []
    hof_merged: dict[str, dict] = {}
    n_islands = 1
    ga_history: list[dict] = []
    evaluations = 0
    finalists: list[dict] = []
    gated_hashes: set[str] = set()
    restart_summaries: list[dict] = []
    n_restarts = 1 if cfg.optimizer == "nsga" else max(1, cfg.max_restarts)

    for round_idx in range(n_restarts):
        restart_state["n"] = round_idx + 1
        restart_state["total"] = n_restarts
        restart_state["gen_offset"] = len(live_history)

        if cfg.optimizer == "nsga":
            candidate_specs, nsga_history, evaluations, pareto_frontier = _run_nsga(
                df_evo, cfg, ppy, costs, on_generation=_on_generation)
            ga_history = nsga_history
        else:
            from dataclasses import replace as _dc_replace
            # Semilla fresca por ronda: explora una región distinta del espacio.
            ga_cfg = _dc_replace(cfg.ga, seed=cfg.ga.seed + round_idx * 1009)
            ga_result = evolve(fitness_fn, ga_cfg, on_generation=_on_generation)
            # Pool de candidatas: hall of fame (mejores-de-siempre) primero,
            # luego la población final — el HoF domina a la población sola.
            seen_hashes: set[str] = set()
            candidate_specs = []
            for p in ga_result["hall_of_fame"] + ga_result["population"]:
                if p["hash"] in seen_hashes:
                    continue
                seen_hashes.add(p["hash"])
                candidate_specs.append({"spec": p["spec"], "fitness": p["fitness"]})
            candidate_specs.sort(key=lambda c: c["fitness"], reverse=True)
            # Historia encadenada entre rondas (offset de generación continuo)
            ga_history.extend({**h, "generation": restart_state["gen_offset"] + h["generation"]}
                              for h in ga_result["history"])
            evaluations = len(fitness_memo)
            n_islands = ga_result.get("islands", 1)
            for p in ga_result["hall_of_fame"]:
                if p["hash"] not in hof_merged or p["fitness"] > hof_merged[p["hash"]]["fitness"]:
                    hof_merged[p["hash"]] = p

        # ── Gating de esta ronda (presupuesto propio, sin repetir genomas) ──
        fresh = [c for c in candidate_specs if spec_hash(c["spec"]) not in gated_hashes]
        gating_total = min(cfg.max_gating_attempts, len(fresh))
        attempts = 0
        for cand in fresh:
            passed_so_far = sum(1 for f in finalists if f["passed_gating"])
            if attempts >= cfg.max_gating_attempts or passed_so_far >= target_passed:
                break
            attempts += 1
            if progress_cb is not None:
                progress_cb(_json_safe({
                    "phase": "gating",
                    "restart": restart_state["n"],
                    "restarts_total": n_restarts,
                    "gating": {"current": attempts, "total": gating_total,
                               "passed": passed_so_far,
                               "candidate": describe_spec(cand["spec"])},
                    "history": list(live_history),
                }))
            finalist = _gate_candidate(cand)
            gated_hashes.add(finalist["spec_hash"])
            finalists.append(finalist)

        passed_count = sum(1 for f in finalists if f["passed_gating"])
        restart_summaries.append({
            "restart": round_idx + 1,
            "seed": (cfg.ga.seed + round_idx * 1009) if cfg.optimizer != "nsga" else cfg.ga.seed,
            "gated": attempts,
            "passed_cumulative": passed_count,
            "evaluations_cumulative": evaluations,
        })
        # Cupo lleno (con colchón): no hacen falta más rondas.
        if passed_count >= target_passed:
            break

    hall_of_fame = [
        {"spec_hash": p["hash"], "description": describe_spec(p["spec"]),
         "fitness": p["fitness"]}
        for p in sorted(hof_merged.values(), key=lambda d: d["fitness"], reverse=True)[:10]
    ]

    # ── Refinamiento local de finalistas (hill-climb sobre parámetros) ──
    # Para cada aprobada: prueba vecinos jitter; si uno mejora el fitness Y
    # vuelve a pasar el gating completo, la sustituye. Nunca se cambia una
    # estrategia validada por otra sin validar.
    refined_count = 0
    if cfg.refine_neighbors > 0:
        from core.domain.services.strategy_spec import jitter_params
        refine_rng = np.random.default_rng(cfg.ga.seed + 987)
        passed_idx = [i for i, f in enumerate(finalists) if f["passed_gating"]]
        for pos, i in enumerate(passed_idx):
            base = finalists[i]
            if progress_cb is not None:
                progress_cb(_json_safe({
                    "phase": "refining",
                    "refining": {"current": pos + 1, "total": len(passed_idx),
                                 "candidate": base["description"]},
                    "history": list(live_history),
                }))
            best_alt, best_fit = None, base["fitness"]
            for _ in range(cfg.refine_neighbors):
                neighbor = jitter_params(base["spec"], refine_rng)
                if spec_hash(neighbor) == base["spec_hash"]:
                    continue
                fit = fitness_fn(neighbor)
                if fit > best_fit + 1e-6:
                    best_alt, best_fit = neighbor, fit
            if best_alt is not None:
                candidate = _gate_candidate({"spec": best_alt, "fitness": best_fit})
                if candidate["passed_gating"]:
                    candidate["refined"] = True
                    candidate["refined_from"] = base["spec_hash"]
                    candidate["fitness_gain"] = round(best_fit - base["fitness"], 4)
                    finalists[i] = candidate
                    gated_hashes.add(candidate["spec_hash"])
                    refined_count += 1

    # ── Libro decorrelacionado ─────────────────────────────────────────
    # Entre las aprobadas, conserva solo estrategias con fuentes de retorno
    # DISTINTAS (|ρ| < umbral sobre la zona de evolución): clones estadísticos
    # del mismo edge no añaden valor a un libro.
    passed_all = [f for f in finalists if f["passed_gating"]]
    series_memo: dict[str, np.ndarray] = {}

    def _series(f: dict) -> np.ndarray:
        h = f["spec_hash"]
        if h not in series_memo:
            series_memo[h] = returns_series(df_evo, f["spec"], costs=costs)
        return series_memo[h]

    kept, corr_dropped = decorrelate_finalists(
        passed_all, _series, cfg.correlation_threshold)

    # Ranking: aprobadas y decorrelacionadas, por fitness (métrica de evolución
    # robustez-aware). El holdout se reporta como confirmación intacta.
    passed = sorted(kept, key=lambda f: f["fitness"], reverse=True)[:cfg.top_k]
    rejected = [f for f in finalists if not f["passed_gating"]]
    for rank, f in enumerate(passed, start=1):
        f["rank"] = rank

    # Coordenadas de robustez de CADA candidata evaluada (pase o no el gating):
    # alimentan el grafico 3D "universo de robustez" con la nube completa de
    # puntos, no solo las supervivientes.
    def _coords(f: dict) -> dict:
        m = f["gating"]["metrics"]
        return {
            "spec_hash": f["spec_hash"],
            "description": f["description"],
            "fitness": f["fitness"],
            "passed_gating": f["passed_gating"],
            "pbo": m.get("pbo"),
            "wf_efficiency": m.get("wf_efficiency"),
            "oos_sharpe": m.get("mean_oos_sharpe"),
            "sharpe": m.get("sharpe"),
            "n_trades": m.get("n_trades"),
            "total_return_pct": m.get("total_return_pct"),
            "max_drawdown_pct": m.get("max_drawdown_pct"),
        }

    report = {
        "interval": interval,
        "initial_capital": initial_capital,
        "candles_total": len(df),
        "data_partition": {
            "evolution_candles": len(df_evo),
            "holdout_candles": len(df_holdout),
            "holdout_fraction": cfg.holdout_fraction,
            "split_index": split,
            "note": (
                "El tramo de validación final (holdout) son las velas más recientes. "
                "No interviene en el fitness del GA, ni en el walk-forward, ni en el "
                "gating; los finalistas se miden en él solo para reportar su "
                "rendimiento en datos jamás vistos."
            ),
        },
        "ga_config": asdict(cfg.ga),
        "gating_thresholds": asdict(cfg.gating),
        "optimizer": cfg.optimizer,
        "ga_evolution": {
            "history": ga_history,
            "evaluations": evaluations,
            "best_fitness": max((c["fitness"] for c in candidate_specs), default=0.0),
            "islands": n_islands,
        },
        "hall_of_fame": hall_of_fame,
        "pareto_frontier": pareto_frontier,
        "summary": {
            "candidates_gated": len(finalists),
            "passed_gating": len(passed),
            "passed_gating_total": len(passed_all),
            "rejected": len(rejected),
            "restarts": len(restart_summaries),
            "refined": refined_count,
            "correlated_dropped": len(corr_dropped),
        },
        "restarts": restart_summaries,
        "correlation_filter": {
            "threshold": cfg.correlation_threshold,
            "dropped": corr_dropped,
            "note": ("El ranking es un libro DECORRELACIONADO: entre aprobadas con "
                     "|ρ| ≥ umbral solo se conserva la de mayor fitness — clones "
                     "estadísticos del mismo edge no añaden valor."),
        },
        "ranking": passed,
        "candidates": [_coords(f) for f in finalists],
        "rejected": [
            {
                **_coords(f),
                "failed_checks": [k for k, v in f["gating"]["checks"].items() if not v],
            }
            for f in rejected
        ],
    }
    if progress_cb is not None:
        progress_cb(_json_safe({"phase": "done", "history": list(live_history),
                                "passed": len(passed)}))
    return _json_safe(report)


class GenerateStrategiesUseCase:
    """Carga el OHLCV, ejecuta el generador y persiste los finalistas robustos."""

    def execute(
        self,
        asset_symbol: str,
        interval: str = "1d",
        limit: int = 730,
        initial_capital: float = 10000.0,
        preset: str = DEFAULT_PRESET,
        optimizer: str = "single",
        config: GenerationConfig | None = None,
        persist: bool = True,
        seed: int | None = None,
        progress_cb=None,
    ) -> dict:
        # Import diferido: mantiene generate_strategies (dominio puro) importable
        # sin arrastrar infraestructura/Django.
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from dataclasses import replace

        symbol = asset_symbol.upper()
        result = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=limit)
        if result is None or result.df.empty or len(result.df) < MIN_CANDLES:
            return {
                "error": (
                    f"Se necesitan al menos {MIN_CANDLES} velas para generar "
                    f"estrategias robustas y no hay suficientes datos para {symbol}."
                ),
            }

        cfg = config or config_for_preset(preset)
        if optimizer in ("single", "nsga"):
            cfg = replace(cfg, optimizer=optimizer)
        if seed is not None:
            # Semilla reproducible elegida por el usuario (mismos datos + misma
            # semilla → misma evolución), como en StrategyQuant.
            cfg = replace(cfg, ga=replace(cfg.ga, seed=int(seed)))
        report = generate_strategies(
            result.df, interval=interval, config=cfg, initial_capital=initial_capital,
            progress_cb=progress_cb,
        )
        report["asset_symbol"] = symbol
        report["data_source"] = result.source
        report["preset"] = preset

        if persist:
            report["persisted"] = self._persist(symbol, interval, report)

        logger.info(
            "generate_strategies %s [%s]: %d/%d finalistas pasan el gating",
            symbol, preset, report["summary"]["passed_gating"], report["summary"]["candidates_gated"],
        )
        return report

    @staticmethod
    def _persist(symbol: str, interval: str, report: dict) -> list[dict]:
        """Persiste cada finalista del ranking como StrategyDefinition (Módulo 0)."""
        from django.utils import timezone
        from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition

        asset = CryptoAsset.objects.filter(symbol=symbol).first()
        persisted = []
        for item in report["ranking"]:
            obj = StrategyDefinition.objects.create(
                asset=asset,
                name=item["description"][:255],
                spec=item["spec"],
                spec_hash=item["spec_hash"],
                interval=interval,
                rank=item["rank"],
                fitness=item["fitness"],
                passed_gating=item["passed_gating"],
                robustness_metrics=item["gating"]["metrics"],
                gating_checks=item["gating"]["checks"],
                holdout_metrics=item["holdout_validation"],
                status="validated",
                generated_at=timezone.now(),
            )
            persisted.append({"id": obj.id, "spec_hash": obj.spec_hash, "rank": obj.rank})
        return persisted
