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
from core.domain.services import block_sampling
from core.domain.services import generation_power as power
from core.domain.services import meta_sizing
from core.domain.services.backtest_execution import CostModel
from core.domain.services.strategy_evaluation import (
    GatingThresholds,
    equity_curve,
    evaluate_fitness,
    gate_spec,
    holdout_performance,
    retest_cascade,
    returns_series,
    walk_forward_matrix,
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
    cross_check_assets: int = 0        # nº de activos extra donde validar cada finalista (0 = off)
    # ── Búsqueda en dos fases (muestreo por bloques) ──────────────
    # El fitness del GA solo tiene que ORDENAR genomas; el veredicto lo da el
    # gating sobre el histórico COMPLETO. Evaluar el fitness sobre una muestra
    # de bloques repartidos por todo el histórico desacopla el coste de la
    # búsqueda de la longitud de la serie — que es lo que impedía usar años de
    # datos. `search_blocks=0` desactiva el muestreo (histórico entero).
    #
    # APAGADO POR DEFECTO hasta que la evidencia lo respalde. La comprobación
    # que acompaña a la idea (`rank_agreement`) es la que debe autorizarla, y
    # sobre una serie sintética de 12 000 velas dio Spearman −0.38 en su primera
    # versión: el muestreo ordenaba casi al revés que el histórico completo.
    # Encender un atajo cuya validación falla sería exactamente lo que el resto
    # del motor existe para impedir.
    search_blocks: int = 0
    search_scored_bars: int = 1800     # velas puntuables repartidas entre bloques
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
        max_restarts=2, refine_neighbors=5, cross_check_assets=3,
        ga=GAConfig(population_size=40, generations=15, elitism=4, random_injection=2,
                    islands=2, migration_every=4, stagnation_patience=4),
        gating=GatingThresholds(wf_splits=4, pbo_neighbors=12, mc_sims=400),
    ),
    "thorough": GenerationConfig(
        top_k=6, max_gating_attempts=18, parsimony=0.03,
        max_restarts=3, refine_neighbors=8, cross_check_assets=4,
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


class TrialRegistry:
    """
    Muestra de las series de retorno de los genomas que la búsqueda evalúa.

    Es la entrada que faltaba para que el PBO y el Deflated Sharpe midan lo que
    dicen medir. Sin ella, ambos se calculaban sobre perturbaciones de la
    campeona ya elegida —casi clones entre sí—, y de ahí que el DSR saliera ≈1
    para cualquier estrategia: la varianza entre pruebas tendía a cero y con ella
    el umbral que hay que superar.

    Dos decisiones deliberadas:

    · **Muestreo de reservorio, no los mejores.** Quedarse con los top-M
      subestimaría la varianza entre pruebas, que es justo el término que eleva
      el umbral del DSR — se acabaría reproduciendo el mismo sesgo optimista con
      otra forma. El reservorio da una muestra uniforme de TODO lo evaluado.
    · **`total_seen` cuenta aparte del reservorio.** La deflación usa el nº real
      de pruebas (que puede ser miles), mientras el reservorio solo acota la
      memoria y aporta la varianza.
    """

    def __init__(self, capacity: int = 300, seed: int = 42) -> None:
        self._capacity = max(2, capacity)
        self._rng = np.random.default_rng(seed)
        self._reservoir: list[list[float]] = []
        self._hashes: set[str] = set()
        self.total_seen = 0

    def add(self, spec_hash_value: str, bar_returns) -> None:
        """Registra un genoma distinto. Repetir el mismo hash no cuenta: el GA
        cachea por hash y una reevaluación no es una prueba nueva."""
        if spec_hash_value in self._hashes:
            return
        self._hashes.add(spec_hash_value)
        self.total_seen += 1

        series = list(bar_returns) if bar_returns is not None else []
        if len(series) < 8:
            return          # sin serie utilizable, cuenta como prueba pero no entra

        if len(self._reservoir) < self._capacity:
            self._reservoir.append(series)
            return
        # Reservorio (algoritmo R): la prueba k-ésima entra con probabilidad
        # capacity/k, sustituyendo a una al azar. Muestra uniforme sin conocer N.
        j = int(self._rng.integers(0, self.total_seen))
        if j < self._capacity:
            self._reservoir[j] = series

    @property
    def returns(self) -> list:
        return self._reservoir

    def summary(self) -> dict:
        return {
            "evaluated": self.total_seen,
            "sampled": len(self._reservoir),
            "capacity": self._capacity,
        }


def _status_for(finalist: dict) -> str:
    """Estado con el que se guarda una finalista.

    «Validada» solo si ha demostrado algo en datos JAMÁS vistos. Antes se
    marcaba `validated` a todo el ranking sin mirar el holdout, de modo que la
    etiqueta afirmaba más de lo que el dato sostenía: pasar el gating es
    superar controles sobre la misma zona en la que se buscó.

    Una finalista que pasa el gating pero pierde en holdout no es un fracaso —
    es una **candidata**: robusta en la búsqueda, aún sin confirmar fuera. La
    distinción es la que separa un hallazgo de una promesa.
    """
    if not finalist.get("passed_gating"):
        return "candidate"
    holdout = finalist.get("holdout_validation") or {}
    sharpe = holdout.get("sharpe")
    n_trades = holdout.get("n_trades", 0)
    # Sin operaciones en el holdout no hay evidencia ni a favor ni en contra:
    # tampoco basta para llamarlo validado.
    if sharpe is None or n_trades == 0 or sharpe <= 0:
        return "candidate"
    return "validated"


def _overfitting_summary(registry: "TrialRegistry", finalists: list) -> dict:
    """
    Resumen de multiplicidad de la ejecución: cuántas configuraciones se
    probaron, cuántas son realmente independientes y qué Sharpe alcanzaría el
    azar con ese número de intentos.

    Se calcula una sola vez por ejecución (no por finalista) porque el nº de
    pruebas es una propiedad de la búsqueda, no de la estrategia elegida.
    """
    from core.domain.services import backtest_robustness as robustness

    sampled = registry.returns
    effective = robustness.effective_number_of_trials(sampled)

    # La varianza entre pruebas la aporta cualquier finalista ya evaluada: el
    # bloque de sobreajuste que devuelve gate_spec la trae calculada.
    variance = 0.0
    best_dsr = None
    best_sharpe = None
    for f in finalists:
        block = f.get("gating", {}).get("metrics", {}).get("overfitting")
        if not block or block.get("source") != "search_trials":
            continue
        dsr = block.get("deflated_sharpe", {})
        variance = dsr.get("trial_sr_variance", 0.0) or 0.0
        if dsr.get("dsr") is not None and (best_dsr is None or dsr["dsr"] > best_dsr):
            best_dsr = dsr["dsr"]
            best_sharpe = dsr.get("sr_per_period")
        break

    curve = robustness.expected_max_sharpe_curve(
        variance=variance, n_trials=max(registry.total_seen, 1), observed_sharpe=best_sharpe,
    )

    return {
        **registry.summary(),
        "effective_trials": effective.get("effective_trials"),
        "best_deflated_sharpe": best_dsr,
        "expected_max_sharpe_curve": curve,
        "note": (
            f"Se evaluaron {registry.total_seen} configuraciones distintas "
            f"({effective.get('effective_trials')} independientes tras agrupar las "
            "correlacionadas). Con ese número de intentos, el azar produce por sí solo "
            f"un Sharpe por periodo de hasta {curve['expected_max_at_n']}: cualquier "
            "resultado por debajo de ese umbral no se distingue de haber buscado mucho."
        ),
    }


def _run_nsga(df_evo, cfg: "GenerationConfig", ppy: float, costs, on_generation=None,
              registry: "TrialRegistry | None" = None):
    """
    Optimización multi-objetivo: maximizar Sharpe OOS, minimizar drawdown y
    minimizar sobreajuste. Devuelve los specs de la frontera de Pareto (como
    candidatos a gating), la historia para la visualización, el nº de
    evaluaciones y la frontera con sus objetivos.
    """
    def objectives(spec: dict) -> tuple:
        ev = evaluate_fitness(df_evo, spec, n_splits=cfg.gating.wf_splits, ppy=ppy,
                              costs=costs, parsimony=cfg.parsimony,
                              with_returns=registry is not None)
        if registry is not None:
            registry.add(spec_hash(spec), ev.get("bar_returns"))
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


def _rank_agreement(finalists: list[dict]) -> dict:
    """
    ¿El orden que dio la muestra se parece al del histórico completo?

    Es la comprobación que valida —o desmiente— la búsqueda en dos fases. El GA
    ordena por fitness de bloques; el gating vuelve a medir cada finalista sobre
    el histórico entero. Si esos dos órdenes no se parecen, el muestreo estaría
    buscando a ciegas y habría que saberlo.

    Se usa Spearman (correlación de RANGOS), no Pearson: lo que importa es el
    orden, no que las magnitudes coincidan — de hecho no deben coincidir, porque
    son medidas distintas sobre datos distintos.

    Con menos de cuatro finalistas no se calcula: una correlación de rangos sobre
    tres puntos toma pocos valores posibles y ninguno significa nada.
    """
    pairs = [(f["fitness"], f["gating"]["metrics"]["mean_oos_sharpe"])
             for f in finalists
             if f.get("fitness") is not None
             and f.get("gating", {}).get("metrics", {}).get("mean_oos_sharpe") is not None]
    if len(pairs) < 4:
        return {"n": len(pairs), "spearman": None,
                "note": "Muy pocas finalistas para medir si el orden de la muestra "
                        "coincide con el del histórico completo."}

    a = np.argsort(np.argsort([p[0] for p in pairs]))
    b = np.argsort(np.argsort([p[1] for p in pairs]))
    if a.std() < 1e-12 or b.std() < 1e-12:
        return {"n": len(pairs), "spearman": None,
                "note": "Sin dispersión entre finalistas: no hay orden que comparar."}
    rho = float(np.corrcoef(a, b)[0, 1])
    return {
        "n": len(pairs),
        "spearman": round(rho, 3),
        "note": (
            f"Correlación de rangos {rho:.2f} entre el fitness de la muestra y el "
            "Sharpe fuera de muestra del histórico completo. "
            + ("La muestra ordena las candidatas igual que el histórico entero: "
               "buscar sobre ella no pierde información de selección."
               if rho >= 0.5 else
               "El orden de la muestra se parece poco al del histórico completo: "
               "la búsqueda por bloques podría estar dejando fuera buenas "
               "candidatas en esta serie.")
        ),
    }


def decorrelate_finalists(passed: list[dict], series_fn, threshold: float) -> tuple[list, list]:
    """
    Libro decorrelacionado: recorre las finalistas por fitness descendente y
    conserva cada una solo si su serie de retornos tiene |ρ| < `threshold` con
    TODAS las ya conservadas (greedy). Un libro institucional quiere fuentes de
    retorno distintas, no cinco formas de escribir el mismo edge.

    **Las correlacionadas NO se tiran: se adjuntan como VARIANTES** de aquella
    con la que chocan. La razón es medible: en una ejecución típica cinco
    estrategias superan el gating completo —con su holdout, su CPCV y sus
    retests ya pagados— y solo dos llegan al informe. Las otras tres se
    computaban enteras y desaparecían dejando una línea de texto. Correlacionar
    con otra no las invalida; significa que explotan el mismo edge, y elegir
    entre ellas —por caída máxima, por nº de operaciones, por rotación— es una
    decisión del usuario, no un descarte que el motor deba hacer en silencio.

    `series_fn(finalist) -> np.ndarray` inyectable (testeable sin backtests).
    Devuelve (conservadas, descartadas_con_motivo). Cada conservada lleva en
    `variants` las que se le adjuntaron, con sus métricas completas.
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    by_hash: dict[str, dict] = {}
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
            f.setdefault("variants", [])
            kept.append(f)
            by_hash[f["spec_hash"]] = f
        else:
            dropped.append({"spec_hash": f["spec_hash"], "description": f["description"],
                            "fitness": f["fitness"], "correlated_with": clash})
            # La variante conserva TODO lo que costó calcularla: si el usuario la
            # prefiere, la tiene validada y no hay que rehacer nada.
            parent = by_hash.get(clash["kept_hash"])
            if parent is not None:
                parent.setdefault("variants", []).append({
                    **f, "correlation_with_parent": clash["corr"],
                })
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

    # Registro de las pruebas realmente hechas. Alimenta el PBO (sobreajuste de
    # selección) y la deflación del Sharpe por el nº de configuraciones probadas.
    trial_registry = TrialRegistry(seed=cfg.ga.seed)

    # ── Muestra de bloques para la FASE 1 (búsqueda) ─────────────────
    # Se construye UNA VEZ y se usa para todos los genomas: si cambiara entre
    # evaluaciones se estarían comparando estrategias medidas sobre datos
    # distintos, y el ranking sería ruido con aspecto de selección.
    search_blocks = (
        block_sampling.plan_blocks(
            len(df_evo), n_blocks=cfg.search_blocks,
            warmup=200, target_scored=cfg.search_scored_bars)
        if cfg.search_blocks > 0 and len(df_evo) > cfg.search_scored_bars * 1.5
        else None
    )

    def fitness_fn(spec: dict) -> float:
        h = spec_hash(spec)
        if h not in fitness_memo:
            ev = evaluate_fitness(
                df_evo, spec, n_splits=cfg.gating.wf_splits, ppy=ppy,
                costs=costs, parsimony=cfg.parsimony, with_returns=True,
                blocks=search_blocks)
            trial_registry.add(h, ev.get("bar_returns"))
            fitness_memo[h] = ev["fitness"]
        return fitness_memo[h]

    def _gate_candidate(cand: dict) -> dict:
        """Gating + holdout de una candidata → dict de finalista completo."""
        spec = cand["spec"]
        # Los trials de la búsqueda entran aquí: son los que hacen que el PBO
        # mida sobreajuste de selección y que el Sharpe se deflacte por el nº
        # real de configuraciones probadas, no por unos vecinos del campeón.
        gate = gate_spec(df_evo, spec, cfg.gating, ppy=ppy, costs=costs,
                         trial_returns=trial_registry.returns,
                         n_evaluations=trial_registry.total_seen)
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
                df_evo, cfg, ppy, costs, on_generation=_on_generation,
                registry=trial_registry)
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

    # ── Cascada de retests sobre las supervivientes ────────────────
    # Se aplica al RANKING y no a cada intento del gating: son ~15 backtests
    # extra por estrategia, y solo tiene sentido gastarlos en las que ya han
    # pasado todo lo demás. Se reporta, no recorta el cupo.
    for f in passed:
        f["retests"] = retest_cascade(df_evo, f["spec"], ppy=ppy, costs=costs,
                                      seed=cfg.ga.seed)
        # Overlay de convicción, por la MISMA razón: entrenar un meta-modelo
        # cuesta ~1,4 s por candidata y su resultado no decide nada del gating,
        # solo se muestra. Gastarlo en las que ya han sobrevivido a todo lo
        # demás es la diferencia entre segundos y minutos en el preset
        # exhaustivo. Vive dentro de `gating.metrics` para que la interfaz lo
        # encuentre donde ya lo buscaba.
        f["gating"]["metrics"]["meta_sizing"] = meta_sizing.conviction_overlay(
            df_evo, f["spec"], ppy=ppy, costs=costs)
        f["gating"]["metrics"]["meta_sizing_applied"] = \
            f["gating"]["metrics"]["meta_sizing"].get("applied", False)

    # Radiografía de estabilidad temporal del campeón: matriz walk-forward
    # (Sharpe OOS por tramo bajo distintos troceos, solo zona de evolución).
    wf_matrix = walk_forward_matrix(df_evo, passed[0]["spec"], ppy=ppy, costs=costs) \
        if passed else None

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
        # Control de multiplicidad a nivel de ejecución: cuántas pruebas se
        # hicieron de verdad y qué umbral de Sharpe produce el puro azar con ese
        # número. Es el contexto sin el cual cualquier Sharpe es incomparable.
        "overfitting_control": _overfitting_summary(trial_registry, finalists),
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
            # Estrategias VALIDADAS que salen de la ejecución: las del ranking
            # más sus variantes. `passed_gating` solo cuenta el libro
            # decorrelacionado y por eso subestimaba lo encontrado — una
            # variante superó exactamente los mismos controles.
            "strategies_found": len(passed) + sum(len(f.get("variants", [])) for f in passed),
            "variants": sum(len(f.get("variants", [])) for f in passed),
        },
        # ¿Tenía esta ejecución datos suficientes para dar un veredicto?
        # Sin esto, un libro vacío por falta de muestra se presentaba igual que
        # uno vacío por falta de edge, y son conclusiones opuestas: la primera no
        # dice nada sobre el mercado.
        "power": power.assess(
            candles=len(df), interval=interval, wf_splits=cfg.gating.wf_splits,
            evolution_candles=len(df_evo),
            trades_observed=(passed[0]["gating"]["metrics"]["n_trades"] if passed
                             else (max((f["gating"]["metrics"]["n_trades"]
                                        for f in finalists), default=None))),
        ),
        # Fase 1 de la búsqueda: sobre qué se ordenaron las candidatas, y si ese
        # orden se parece al del histórico completo. Sin esta comprobación, el
        # muestreo sería un atajo sin evidencia de que preserva lo que importa.
        "search_sampling": (
            {**block_sampling.describe(search_blocks, len(df_evo)),
             "rank_agreement": _rank_agreement(finalists)}
            if search_blocks else
            {"n_blocks": 0,
             "note": "El fitness se calculó sobre el histórico completo de la "
                     "zona de evolución (sin muestreo)."}
        ),
        "walk_forward_matrix": wf_matrix,
        "restarts": restart_summaries,
        "correlation_filter": {
            "threshold": cfg.correlation_threshold,
            "dropped": corr_dropped,
            "note": ("El ranking es un libro DECORRELACIONADO: entre aprobadas con "
                     "|ρ| ≥ umbral solo una encabeza el libro — cinco formas del "
                     "mismo edge no diversifican. Las demás NO se descartan: "
                     "viajan como `variants` de aquella con la que correlacionan, "
                     "con sus métricas completas, porque superaron exactamente "
                     "los mismos controles y elegir entre ellas es del usuario."),
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
        limit: int | None = None,
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

        # Velas a pedir POR CALENDARIO, no un recuento fijo. El motor pedía 730
        # para todos los marcos —un número elegido cuando solo había gráficos
        # diarios (730 = 2 años)—, con lo que en 1 h se quedaba en 30 días de
        # histórico y cada tramo del walk-forward cubría cinco días. Ahí no hay
        # estrategia que valga: no hay operaciones que medir.
        if limit is None:
            limit = power.recommended_candles(interval)

        # Si el almacén propio no llega, se retro-carga antes de rendirse: los
        # exchanges devuelven como mucho 1000 velas por llamada, así que sin
        # backfill el objetivo de calendario sería inalcanzable por definición.
        self._ensure_history(symbol, interval, limit)

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=limit)
        if result is None or result.df.empty or len(result.df) < MIN_CANDLES:
            available = 0 if result is None or result.df is None else len(result.df)
            return {
                "error": (
                    f"Se necesitan al menos {MIN_CANDLES} velas para generar "
                    f"estrategias robustas y solo hay {available} para {symbol} "
                    f"en {interval}."
                ),
                "candles_available": available,
                "candles_needed": MIN_CANDLES,
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

        # ── Validación cruzada multi-activo de las finalistas ──────────
        # Un edge robusto generaliza a otros símbolos; uno sobreajustado solo
        # funciona donde nació. Evidencia REPORTADA (no recorta el cupo): el
        # consistency_score acompaña a cada finalista en el ranking y en la
        # persistencia. La cesta se carga UNA vez y se comparte.
        if cfg.cross_check_assets > 0 and report.get("ranking"):
            self._cross_validate(report, symbol, interval, cfg, progress_cb)

        if persist:
            # El registro va ANTES de persistir finalistas y fuera de su suerte:
            # una búsqueda que no produjo nada es justo la que no debe perderse
            # (si solo se registran las que dieron algo, el nº de pruebas queda
            # subestimado y con él la deflación del Sharpe).
            report["experiment_run"] = self._register_run(symbol, interval, cfg, report)
            report["persisted"] = self._persist(symbol, interval, report)

        logger.info(
            "generate_strategies %s [%s]: %d/%d finalistas pasan el gating",
            symbol, preset, report["summary"]["passed_gating"], report["summary"]["candidates_gated"],
        )
        return report

    @staticmethod
    def _ensure_history(symbol: str, interval: str, target: int) -> None:
        """
        Retro-carga el almacén hasta el objetivo, si hace falta.

        Los exchanges devuelven como mucho 1000 velas por llamada, así que sin
        backfill cualquier objetivo por encima de eso sería inalcanzable por
        construcción — y el generador se quedaría con 1000 velas creyendo que
        pidió 4000. Es best-effort: si la red falla, se sigue con lo que haya y
        el diagnóstico de potencia lo dirá.
        """
        if target <= 1000:
            return
        try:
            from core.application.use_cases.ohlcv_store import BackfillOhlcvUseCase, coverage
            have = coverage(symbol, interval).get("candles", 0)
            if have >= target:
                return
            # Páginas de 1000: las justas para cubrir el hueco, con un tope para
            # que una ejecución no se convierta en una descarga interminable.
            pages = min(8, (target - have) // 1000 + 1)
            BackfillOhlcvUseCase().execute(symbol=symbol, interval=interval,
                                           target_candles=target, max_pages=pages)
        except Exception:  # noqa: BLE001 — sin red o sin BD se sigue con lo que haya
            logger.info("backfill previo a la generación no disponible para %s %s",
                        symbol, interval, exc_info=True)

    @staticmethod
    def _cross_validate(report: dict, symbol: str, interval: str,
                        cfg: GenerationConfig, progress_cb=None) -> None:
        """Valida cada finalista del ranking en una cesta de otros activos y
        anota su consistency_score (fracción con Sharpe OOS positivo)."""
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.application.use_cases.run_spec_robustness import (
            DEFAULT_CROSS_ASSETS, cross_asset_validation,
        )

        basket = [s for s in DEFAULT_CROSS_ASSETS if s != symbol][: cfg.cross_check_assets]
        history = report.get("ga_evolution", {}).get("history", [])
        dfs = {}
        for s in basket:
            try:
                res = fetch_ohlcv_dataframe(symbol=s, interval=interval, limit=500)
                dfs[s] = res.df if res is not None and not res.df.empty else None
            except Exception as exc:  # noqa: BLE001 — un activo sin datos no rompe la validación
                logger.warning("cross_validate fetch %s/%s: %s", s, interval, exc)
                dfs[s] = None

        ranking = report["ranking"]
        for i, f in enumerate(ranking):
            if progress_cb is not None:
                progress_cb(_json_safe({
                    "phase": "cross_validating",
                    "cross": {"current": i + 1, "total": len(ranking),
                              "basket": basket, "candidate": f["description"]},
                    "history": history,
                }))
            cross = cross_asset_validation(dfs, f["spec"], interval, cfg.gating.wf_splits)
            f["cross_asset"] = cross
            # También en las métricas persistidas (JSON, sin migración).
            f["gating"]["metrics"]["cross_consistency"] = cross["consistency_score"]

        report["cross_check"] = {
            "basket": basket,
            "note": ("Cada finalista se reevalúa (walk-forward OOS) en una cesta de otros "
                     "activos. consistency_score = fracción con Sharpe OOS positivo: un edge "
                     "que generaliza es otra liga de robustez. Evidencia informativa: no "
                     "recorta el cupo del ranking."),
        }
        if progress_cb is not None:
            progress_cb(_json_safe({"phase": "done", "history": history,
                                    "passed": len(ranking)}))

    @staticmethod
    def _register_run(symbol: str, interval: str, cfg: GenerationConfig, report: dict) -> dict:
        """Anota la ejecución en el registro append-only y devuelve el contexto
        acumulado de este activo (cuántas pruebas se le llevan hechas).

        El acumulado se REPORTA, no deflacta: el DSR usa el N de la corrida en
        curso para que el resultado sea reproducible y no cambie de valor al
        re-ejecutar. Aun así, saber que un activo lleva 40.000 configuraciones
        probadas es información de gobernanza que no debe perderse.
        """
        from django.db.models import Count, Sum
        from core.domain.services.strategy_spec import catalog_version
        from core.infrastructure.persistence.models import CryptoAsset, StrategyExperimentRun

        control = report.get("overfitting_control", {}) or {}
        curve = control.get("expected_max_sharpe_curve", {}) or {}
        try:
            run = StrategyExperimentRun.objects.create(
                asset=CryptoAsset.objects.filter(symbol=symbol).first(),
                asset_symbol=symbol,
                interval=interval,
                seed=cfg.ga.seed,
                preset=report.get("preset", ""),
                optimizer=cfg.optimizer,
                catalog_version=catalog_version(),
                candles=report.get("candles_total", 0),
                evaluations=control.get("evaluated", 0),
                effective_trials=control.get("effective_trials") or 0,
                expected_max_sharpe=curve.get("expected_max_at_n"),
                candidates_gated=report["summary"]["candidates_gated"],
                passed_gating=report["summary"]["passed_gating"],
                best_fitness=report["ga_evolution"]["best_fitness"],
                best_deflated_sharpe=control.get("best_deflated_sharpe"),
            )
        except Exception:  # noqa: BLE001 — el registro no puede tumbar una generación válida
            logger.exception("no se pudo registrar la ejecución del generador %s/%s",
                             symbol, interval)
            return {"registered": False}

        history = StrategyExperimentRun.objects.filter(
            asset_symbol=symbol, interval=interval,
        ).aggregate(runs=Count("id"), trials=Sum("evaluations"))

        return {
            "registered": True,
            "run_id": run.id,
            "catalog_version": run.catalog_version,
            "seed": run.seed,
            # Contexto histórico del activo: cuántas veces se ha buscado aquí y
            # con cuántas configuraciones en total.
            "cumulative_runs": history["runs"] or 0,
            "cumulative_evaluations": history["trials"] or 0,
            "note": (
                f"{symbol}/{interval} acumula {history['trials'] or 0} configuraciones "
                f"probadas en {history['runs'] or 0} ejecuciones. El Sharpe deflactado "
                "usa el N de ESTA ejecución (reproducible); el acumulado es contexto "
                "de gobernanza."
            ),
        }

    @staticmethod
    def _persist(symbol: str, interval: str, report: dict) -> list[dict]:
        """Persiste cada finalista del ranking como StrategyDefinition (Módulo 0)."""
        from django.utils import timezone
        from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition

        asset = CryptoAsset.objects.filter(symbol=symbol).first()
        persisted = []
        for item in report["ranking"]:
            status = _status_for(item)
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
                status=status,
                generated_at=timezone.now(),
            )
            persisted.append({"id": obj.id, "spec_hash": obj.spec_hash,
                              "rank": obj.rank, "status": status})
        return persisted
