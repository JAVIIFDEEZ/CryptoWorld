/**
 * services/strategyGeneratorService.ts — Generador genético de estrategias.
 *
 * El generador corre como tarea Celery (evolución del GA + gating de robustez,
 * cientos de backtests), así que el flujo es asíncrono: launch() lanza la tarea
 * y devuelve un job_id; getStatus() consulta el estado hasta tener el informe
 * con el ranking de finalistas robustas.
 */

import apiClient from './api'

// ── Petición ───────────────────────────────────────────────────────

export type GenPreset = 'fast' | 'balanced' | 'thorough'

/**
 * Lado del mercado que una ejecución puede explorar.
 *
 * `both` es UNA estrategia que opera los dos lados con bloques distintos para
 * cada uno; `auto` deja que la dirección evolucione como un gen más y la
 * decide por estrategia. No son lo mismo: con `both` todo el libro es
 * bidireccional, con `auto` el libro sale mezclado.
 */
export type GenDirection = 'long' | 'short' | 'both' | 'auto'

export interface GenerateRequest {
  asset_symbol: string
  interval?: string
  limit?: number
  initial_capital?: number
  preset?: GenPreset
  optimizer?: 'single' | 'nsga'
  /** Lado del mercado que la búsqueda puede explorar (por defecto, solo largos). */
  direction?: GenDirection
  /** Semilla reproducible del GA (misma semilla + mismos datos → misma evolución). */
  seed?: number
}

/**
 * Qué aportó cada lado de una estrategia bidireccional.
 *
 * Dos medidas que responden a preguntas distintas: la ATRIBUCIÓN (operaciones y
 * P&L en la ejecución conjunta) dice de dónde salió el resultado; el
 * AISLAMIENTO (`standalone_oos_sharpe`) dice si ese lado se sostendría solo.
 * Hacen falta las dos porque los dos lados compiten por la misma posición —el
 * motor mantiene una a la vez—, así que un lado puede parecer flojo solo
 * porque el otro le quitó los turnos buenos.
 */
export interface SidePerformance {
  n_trades: number
  share_of_trades_pct: number
  sum_pnl_pct: number
  mean_pnl_pct: number
  win_rate_pct: number
  /** `null` cuando el lado no perdió nunca: con pocas operaciones eso no es un infinito, es falta de muestra. */
  profit_factor: number | null
  standalone_oos_sharpe: number
  standalone_folds: number
  standalone_trades: number
  standalone_sharpe: number
  /** ¿El Sharpe de ESTE lado se distingue de cero, o es magnitud sin incertidumbre? */
  significance?: { significant: boolean; note: string; confidence_interval?: Record<string, number | null> }
  /** Cuánto dinero admite este lado por su cuenta. */
  capacity?: CapacityEstimate
  /**
   * Cuello de botella de la estrategia entera: los dos lados comparten una sola
   * posición, así que la capacidad conjunta no es la suma — la marca el lado más
   * estrecho de los que operan de verdad.
   */
  binding_capacity_usd?: number | null
}

export type SideBreakdown = { long: SidePerformance; short: SidePerformance }

/**
 * Una candidata que falló UN SOLO control del gating, y por cuánto.
 *
 * `gap_ratio` es el margen RELATIVO a la escala del propio control — lo único
 * que hace comparables un recuento de operaciones, un cociente de eficiencia y
 * un porcentaje de retorno. Es `null` cuando el control no se mide en una
 * escala (el de «cada lado se sostiene solo»), que no es lo mismo que estar
 * lejos.
 *
 * Nada de esto mueve un umbral. El veredicto es el que era.
 */
export interface NearMiss {
  spec_hash: string
  description: string
  fitness: number
  direction?: GenDirection
  check: string
  label: string
  observed: number | null
  required: number | null
  gap: number | null
  gap_ratio: number | null
  /** Solo en el control por lado: qué lado falló y por qué, en texto. */
  reasons?: string[]
  note: string
}

/**
 * ¿Hay desglose por lado?
 *
 * El backend manda `{}` en las estrategias de un solo lado —no hay nada que
 * desglosar—, así que la comprobación no es «existe el campo» sino «tiene los
 * dos lados dentro».
 */
export function hasSideBreakdown(
  sides?: SideBreakdown | Record<string, never> | null,
): sides is SideBreakdown {
  return !!sides && 'long' in sides && 'short' in sides
}

export interface ParetoPoint {
  spec_hash: string
  description: string
  oos_sharpe: number
  max_drawdown_pct: number
  overfit_gap: number
}

// ── Respuestas ─────────────────────────────────────────────────────

export type JobStatus = 'PENDING' | 'STARTED' | 'RETRY' | 'SUCCESS' | 'FAILURE'

export interface LaunchResponse {
  job_id: string
  status: JobStatus
  poll_url: string
}

/**
 * Una condición compilable del StrategySpec.
 *
 * `pattern` es la que no encaja con las demás: no compara dos números, afirma
 * que ocurrió un SUCESO (una envolvente, una barrida de liquidez, un hueco de
 * valor) dentro de las últimas `lookback` velas. Por eso no lleva `op` — un
 * suceso ocurre o no ocurre, no hay operador que invertir.
 */
export interface SpecCondition {
  type: 'threshold' | 'cross' | 'compare' | 'slope' | 'pattern'
  indicator?: string
  params?: Record<string, number>
  op?: string
  threshold?: number
  bars?: number
  a?: { indicator: string; params: Record<string, number> }
  b?: { indicator: string; params: Record<string, number> }
  /** Solo en `pattern`: nombre del patrón de acción del precio. */
  pattern?: string
  /** Solo en `pattern`: velas de vigencia del suceso. */
  lookback?: number
  /**
   * Niega la condición. Solo existe en tipos de ESTADO: el complemento de un
   * suceso puntual sería cierto casi siempre y no diría nada.
   */
  negate?: boolean
}

/**
 * Etiquetas cortas de los patrones para las vistas gráficas.
 *
 * El backend ya manda una descripción larga en español; esto es para donde solo
 * caben tres palabras (cuentas de la hélice, cajas del diagrama 2D). Un patrón
 * que no esté aquí cae a su propio nombre, que sigue siendo legible — nunca a
 * `undefined`, que es lo que salía antes de existir esta tabla.
 */
export const PATTERN_SHORT_LABELS: Record<string, string> = {
  BULL_ENGULF: 'envolvente ↑',
  BEAR_ENGULF: 'envolvente ↓',
  HAMMER: 'martillo',
  SHOOTING_STAR: 'estrella fugaz',
  DOJI: 'doji',
  INSIDE_BAR: 'vela interior',
  OUTSIDE_BAR: 'vela envolvente',
  FVG_BULL: 'FVG ↑',
  FVG_BEAR: 'FVG ↓',
  SWEEP_LOW: 'barrida ↓',
  SWEEP_HIGH: 'barrida ↑',
  OB_BULL: 'order block ↑',
  OB_BEAR: 'order block ↓',
  CRT: 'CRT',
  PO3_BULL: 'AMD ↑',
  PO3_BEAR: 'AMD ↓',
  ORB_UP: 'ORB ↑',
  ORB_DOWN: 'ORB ↓',
  FIB_DISCOUNT: 'fib descuento',
  FIB_PREMIUM: 'fib premium',
}

/** Etiqueta corta y legible de cualquier condición, para vistas gráficas. */
export function conditionLabel(c: SpecCondition): string {
  const text = conditionText(c)
  return c.negate ? `¬${text}` : text
}

/** Cómo se lee el combinador de un bloque en una vista compacta. */
export function combineLabel(block: SpecBlock): string {
  return block.combine === 'K_OF_N' ? `${block.k ?? 2} de ${block.conditions.length}` : block.combine
}

function conditionText(c: SpecCondition): string {
  if (c.type === 'pattern') {
    const name = PATTERN_SHORT_LABELS[c.pattern ?? ''] ?? c.pattern ?? 'patrón'
    return c.lookback && c.lookback > 1 ? `${name} ≤${c.lookback}v` : name
  }
  if (c.type === 'threshold') return `${c.indicator} ${c.op === 'gt' ? '>' : '<'} ${c.threshold}`
  if (c.type === 'slope') return `${c.indicator} ${c.op === 'rising' ? '↗' : '↘'} ${c.bars}v`
  if (c.type === 'compare') return `${c.a?.indicator} ${c.op === 'above' ? '>' : '<'} ${c.b?.indicator}`
  return `${c.a?.indicator} ${c.op === 'cross_above' ? '↗' : '↘'} ${c.b?.indicator}`
}

/**
 * Bloque de condiciones.
 *
 * `K_OF_N` es confirmación parcial —«al menos k de estas n»—, que no se puede
 * escribir encadenando Y y O sin anidar. `k` solo viaja con ese combinador.
 */
export interface SpecBlock {
  combine: 'AND' | 'OR' | 'K_OF_N'
  k?: number
  conditions: SpecCondition[]
}

export interface StrategySpec {
  entry: SpecBlock
  exit: SpecBlock
  /** Ausente = largo. Los specs guardados antes de existir los cortos lo omiten. */
  direction?: 'long' | 'short' | 'both'
  /** Solo en `both`: el lado corto, con bloques propios evolucionados aparte. */
  short_entry?: SpecBlock
  short_exit?: SpecBlock
}

export interface GenerationPower {
  candles: number
  interval: string
  span_days: number
  evolution_candles: number
  wf_splits: number
  bars_per_fold: number
  days_per_fold: number
  trades_observed: number | null
  /** Operaciones por tramo walk-forward: la unidad que decide si el Sharpe de
   *  ese tramo significa algo. Por debajo de ~10, apenas discrimina. */
  trades_per_fold: number | null
  reliability: 'high' | 'low' | 'insufficient'
  limits: string[]
  note: string
}

export interface GatingChecks {
  min_trades: boolean
  no_lookahead: boolean
  wf_efficiency: boolean
  pbo: boolean
  mc_p5_positive: boolean
  /**
   * Cada lado activo se sostiene solo. Sin este control, una estrategia que
   * gana mucho en largo y pierde en corto aprueba por promedio: el agregado
   * sale bien y nadie mira de dónde. En estrategias de un solo lado no hay
   * nada que exigir y pasa siempre.
   */
  sides_stand_alone?: boolean
}

/**
 * Estado de una estrategia guardada.
 *
 * `validated` exige holdout positivo — datos jamás vistos —, no solo haber
 * pasado el gating. Una que pasa el gating pero pierde fuera es `candidate`:
 * robusta en la búsqueda, aún sin confirmar.
 */
export type StrategyStatus = 'candidate' | 'validated' | 'rejected' | 'archived'

/** Punto de la curva E[max Sharpe] frente al número de pruebas. */
export interface ExpectedMaxSharpePoint {
  trials: number
  expected_max_sharpe: number
}

export interface ExpectedMaxSharpeCurve {
  curve: ExpectedMaxSharpePoint[]
  variance: number
  n_trials: number
  observed_sharpe: number | null
  expected_max_at_n: number
  /** Pruebas a partir de las cuales el azar iguala el Sharpe observado. null = nunca. */
  trials_to_match_by_chance: number | null
}

export interface DeflatedSharpe {
  dsr: number | null
  sr_per_period?: number
  sr0_threshold?: number
  n_trials?: number
  n_trials_sampled?: number
  trial_sr_variance?: number
  note?: string
}

/**
 * Control de sobreajuste de una finalista.
 *
 * `source` es lo que decide qué significan estos números:
 *   · `search_trials`    — calculados sobre los genomas que la búsqueda evaluó
 *     de verdad: miden sobreajuste de selección y deflactan por el nº real de
 *     pruebas. Es el modo válido.
 *   · `parameter_jitter` — calculados sobre perturbaciones de la propia
 *     estrategia: miden estabilidad paramétrica, NO sobreajuste de selección.
 */
export interface OverfittingControl {
  source: 'search_trials' | 'parameter_jitter'
  pbo: { pbo: number | null; n_configs?: number; note?: string }
  deflated_sharpe: DeflatedSharpe
  effective_trials: { n_trials: number; effective_trials: number; clustered: boolean }
  expected_max_sharpe_curve: ExpectedMaxSharpeCurve
  note: string
}

/**
 * Validación cruzada combinatoria purgada (CPCV).
 *
 * El walk-forward recorre UN camino histórico y devuelve un punto. Esto es la
 * nube de la que ese punto era una muestra: todas las combinaciones de k
 * bloques del histórico. La cifra honesta es el percentil bajo — qué rinde la
 * estrategia cuando el troceo NO la favorece —, no la media.
 */
export interface CpcvDistribution {
  n_paths: number
  n_blocks: number
  blocks_per_path?: number
  sharpe_mean?: number
  sharpe_median?: number
  sharpe_p5?: number
  sharpe_p25?: number
  sharpe_p75?: number
  sharpe_min?: number
  sharpe_max?: number
  pct_paths_positive?: number
  embargo_pct?: number
  embargo_bars?: number
  blocks?: { block: number; candles: number; sharpe: number; n_trades: number }[]
  note?: string
  purge_note?: string
}

/**
 * Significancia de una métrica: magnitud e incertidumbre juntas.
 *
 * «Sharpe 1.8» no es una afirmación completa: medido sobre 60 velas es
 * compatible con que el Sharpe verdadero sea 0, y sobre 3 000 no lo es.
 */
export interface Significance {
  confidence_interval: {
    sharpe: number | null
    ci_lower?: number
    ci_upper?: number
    confidence?: number
    observations?: number
    /** Si el intervalo NO incluye el cero, la magnitud sí es concluyente. */
    excludes_zero?: boolean
    note?: string
  }
  probabilistic_sharpe: {
    psr: number | null
    benchmark_sharpe?: number
    /** Observaciones que harían falta para afirmar el edge con 95 %. */
    min_track_record_length?: number | null
    note?: string
  }
  significant: boolean
  note: string
}

/**
 * Capacidad: cuánto dinero admite el edge antes de que su propio impacto de
 * mercado se lo coma. Es una propiedad tan real de la estrategia como su
 * Sharpe — y la que ningún backtest retail reporta.
 */
export interface CapacityEstimate {
  capacity_usd: number | null
  base_sharpe_per_period?: number
  adv_usd?: number
  n_orders?: number
  curve?: {
    aum_usd: number
    participation_pct: number
    impact_bps_per_order: number
    net_sharpe: number
    sharpe_retained_pct: number
    feasible: boolean
  }[]
  note?: string
}

/**
 * Overlay de convicción: el spec decide DÓNDE entrar, el meta-modelo CUÁNTO.
 *
 * `applied: false` no es un fallo — es el resultado correcto cuando el
 * meta-modelo no supera al primario. `reason` dice por qué, y la interfaz debe
 * mostrarlo en lugar de callarlo: filtrar con ruido es peor que no filtrar.
 */
export interface MetaSizing {
  applied: boolean
  reason?: 'insufficient_events' | 'unlabelable' | 'no_edge' | 'short_holdout'
    | 'incompatible_sizing' | 'disabled'
  n_events?: number
  meta_model?: {
    usable?: boolean
    n_events?: number
    n_train?: number
    n_test?: number
    test_start_bar?: number
    accuracy?: number
    /** Aciertos del primario operando TODAS sus señales: la línea base honesta. */
    primary_hit_rate?: number
    /** Aciertos cuando el meta-modelo dice que sí: donde se pone el dinero. */
    meta_precision?: number
    edge_over_primary?: number
    signals_taken_pct?: number
    note?: string
  }
  labels?: { n_events: number; counts?: { target: number; stop: number; timeout: number } }
  sizing?: { mean_size_pct: number; signals_taken: number; signals_total: number; floor: number }
  /** Comparación con y sin convicción en el tramo que el modelo no vio entrenando. */
  out_of_sample?: {
    from_bar: number
    candles: number
    sharpe_flat: number
    sharpe_conviction: number
    sharpe_delta: number
    return_flat_pct: number
    return_conviction_pct: number
    max_drawdown_flat_pct: number
    max_drawdown_conviction_pct: number
    exposure_flat_pct: number
    exposure_conviction_pct: number
    trades_flat: number
    trades_conviction: number
  }
  improves?: boolean
  note: string
}

export interface GatingMetrics {
  n_trades: number
  direction?: GenDirection
  /** Desglose por lado; vacío/ausente en estrategias de un solo lado. */
  sides?: SideBreakdown | Record<string, never>
  /** Si falló `sides_stand_alone`: qué lado y por qué, en texto. */
  side_failures?: string[]
  total_return_pct: number
  max_drawdown_pct: number
  exposure_pct: number
  sharpe: number
  sortino: number
  wf_efficiency: number
  mean_oos_sharpe: number
  pbo: number | null
  overfitting?: OverfittingControl
  deflated_sharpe?: number | null
  cpcv?: CpcvDistribution
  cpcv_sharpe_p5?: number | null
  cpcv_sharpe_median?: number | null
  capacity?: CapacityEstimate
  capacity_usd?: number | null
  significance?: Significance
  meta_sizing?: MetaSizing
  meta_sizing_applied?: boolean
  turnover?: number
  cost_drag_pct?: number
  /** Sangrado por financiación del perpetuo. 0 = sin histórico, no «gratis». */
  funding_drag_pct?: number
  exit_reasons?: Record<string, number>
  monte_carlo: {
    prob_profit_pct: number | null
    return_p5_pct: number | null
    return_p50_pct: number | null
    /**
     * El bootstrap devuelve un percentil 5 con cualquier número de operaciones,
     * y con doce ese número no es una cola estimada con poca precisión: es una
     * cola inventada a partir de doce datos. Cuando esto es `true`, nada de este
     * bloque puede presentarse como medido.
     */
    under_powered?: boolean
    min_trades_for_bootstrap?: number
  }
  lookahead_leaky: boolean
}

export interface HoldoutMetrics {
  return_pct: number
  sharpe: number
  max_drawdown_pct: number
  n_trades: number
  win_rate_pct: number
  turnover?: number
  candles: number
}

export interface Finalist {
  rank: number
  spec: StrategySpec
  spec_hash: string
  description: string
  fitness: number
  passed_gating: boolean
  gating: { checks: GatingChecks; metrics: GatingMetrics }
  evolution_metrics: { fitness: number; wf_efficiency: number; mean_oos_sharpe: number; pbo: number | null }
  holdout_validation: HoldoutMetrics
  /** Refinamiento local: la finalista fue sustituida por un vecino mejor re-validado. */
  refined?: boolean
  refined_from?: string
  fitness_gain?: number
  /** Validación cruzada multi-activo: ¿el edge generaliza a otros símbolos? */
  cross_asset?: {
    n_assets: number
    n_positive_oos: number
    consistency_score: number
    results: CrossAssetRow[]
  }
  /** Cascada de retests estilo StrategyQuant (se reporta, no recorta el cupo). */
  retests?: RetestCascade
  /**
   * Estrategias que superaron EXACTAMENTE los mismos controles pero
   * correlacionan con esta, así que no encabezan el libro decorrelacionado.
   *
   * No son descartes: explotan el mismo edge, y elegir entre ellas —por caída
   * máxima, por nº de operaciones, por rotación— es del usuario. Antes se
   * calculaban enteras y desaparecían.
   */
  variants?: StrategyVariant[]
}

export interface StrategyVariant extends Omit<Finalist, 'rank' | 'variants'> {
  /** |ρ| con la cabeza de libro. 0.72 y 0.99 son situaciones muy distintas. */
  correlation_with_parent: number
}

/**
 * Cascada de retests: cada prueba ataca una forma distinta de sobreajuste.
 *
 * `survived` es true solo si aguanta todas. Una prueba que no pudo ejecutarse
 * (serie corta, pocas operaciones) NO cuenta como fallo: ausencia de evidencia
 * no es evidencia de fragilidad.
 */
export interface RetestCascade {
  survived: boolean
  checks: {
    noise: boolean
    starting_bar: boolean
    skip_trades: boolean
    parameter_sensitivity: boolean
    temporal_stability: boolean
  }
  failed: string[]
  noise: {
    n_runs: number
    base_sharpe?: number
    noisy_sharpe_median?: number
    pct_runs_positive?: number
    degradation_pct?: number
  }
  starting_bar: {
    n_offsets: number
    sharpe_std?: number
    sharpe_min?: number
    pct_offsets_positive?: number
    results?: { offset: number; sharpe: number }[]
  }
  skip_trades: {
    n_runs: number
    full_pnl_pct?: number
    pnl_median_pct?: number
    pnl_p5_pct?: number
    pct_runs_profitable?: number
  }
  parameter_sensitivity: {
    n_neighbors: number
    base_sharpe?: number
    neighbor_sharpe_p5?: number
    pct_neighbors_positive?: number
    median_degradation_pct?: number
  }
  /** ¿El beneficio está repartido en el tiempo, o fue una racha? */
  temporal_stability: {
    n_buckets: number
    bucket_returns_pct?: number[]
    positive_buckets?: number
    pct_buckets_positive?: number
    /** Fracción del beneficio total que aporta el MEJOR periodo. */
    concentration?: number
    best_bucket?: number
    worst_bucket?: number
    stable?: boolean
    note?: string
  }
  /** Dónde vive el edge: reparto del rendimiento por régimen de volatilidad. */
  by_regime?: Record<string, {
    bars: number
    share_pct?: number
    total_return_pct?: number
    sharpe_per_period?: number
    note?: string
  }>
  note: string
}

/** Coordenadas de robustez de una candidata (para el universo 3D). */
export interface Candidate {
  spec_hash: string
  description: string
  fitness: number
  passed_gating: boolean
  direction?: GenDirection
  sides?: SideBreakdown | null
  pbo: number | null
  wf_efficiency: number | null
  oos_sharpe: number | null
  sharpe: number | null
  n_trades: number | null
  total_return_pct: number | null
  max_drawdown_pct: number | null
}

export interface GenerationHistoryPoint {
  generation: number
  best: number
  mean: number
  diversity: number
  island_best?: number[]
  mutation_rate?: number
  stagnation?: number
}

export interface GenerationReport {
  asset_symbol: string
  interval: string
  data_source: string
  preset: string
  /** Lado que se buscó en ESTA ejecución (no el de cada estrategia). */
  direction?: GenDirection
  initial_capital: number
  candles_total: number
  data_partition: {
    evolution_candles: number
    holdout_candles: number
    holdout_fraction: number
    split_index: number
    note: string
  }
  ga_config: Record<string, number>
  gating_thresholds: Record<string, number>
  optimizer?: 'single' | 'nsga'
  ga_evolution: { history: GenerationHistoryPoint[]; evaluations: number; best_fitness: number; islands?: number }
  /** Control de multiplicidad de la ejecución: cuántas pruebas y qué da el azar con ellas. */
  overfitting_control?: {
    evaluated: number
    sampled: number
    capacity: number
    effective_trials: number | null
    best_deflated_sharpe: number | null
    expected_max_sharpe_curve: ExpectedMaxSharpeCurve
    note: string
  }
  hall_of_fame?: { spec_hash: string; description: string; fitness: number }[]
  pareto_frontier?: ParetoPoint[]
  summary: {
    candidates_gated: number
    passed_gating: number
    passed_gating_total?: number
    rejected: number
    restarts?: number
    refined?: number
    correlated_dropped?: number
    /** Validadas que salen de la ejecución: el ranking MÁS sus variantes. */
    strategies_found?: number
    variants?: number
    near_misses?: number
  }
  /**
   * ¿Tenía la ejecución datos suficientes para dar un veredicto?
   *
   * Un libro vacío por falta de MUESTRA y uno por falta de EDGE son
   * conclusiones opuestas, y hasta ahora se presentaban igual.
   */
  power?: GenerationPower
  restarts?: { restart: number; seed: number; gated: number; passed_cumulative: number; evaluations_cumulative: number }[]
  /** Matriz walk-forward del campeón: Sharpe OOS por tramo bajo distintos troceos. */
  walk_forward_matrix?: {
    rows: { n_splits: number; folds: number[]; mean_oos_sharpe: number; efficiency: number }[]
    total_folds: number
    positive_folds: number
    stability_score: number
    note: string
  } | null
  cross_check?: { basket: string[]; note: string }
  correlation_filter?: {
    threshold: number
    dropped: { spec_hash: string; description: string; fitness: number; correlated_with: { kept_hash: string; kept_description: string; corr: number } }[]
    note: string
  }
  ranking: Finalist[]
  candidates: Candidate[]
  rejected: (Candidate & { failed_checks: string[]; near_miss?: NearMiss | null })[]
  /** Rechazadas a las que les faltó un solo control, de más cerca a más lejos. */
  near_misses?: NearMiss[]
  /** Qué fue de cada estrategia que se mostró durante la evolución. */
  showcase?: Showcase
  persisted?: { id: number; spec_hash: string; rank: number; status?: StrategyStatus }[]
  /** Registro append-only de esta ejecución + contexto acumulado del activo. */
  experiment_run?: {
    registered: boolean
    run_id?: number
    catalog_version?: string
    seed?: number | null
    cumulative_runs?: number
    cumulative_evaluations?: number
    note?: string
  }
}

export type JobResult = GenerationReport | { error: string }

// ── Telemetría en vivo de la evolución ─────────────────────────────

/** Candidata visualizable: mejores de la generación con su curva de equity
 *  (calculada SOLO sobre la zona de evolución; el holdout nunca se muestra). */
export interface EvolutionCandidate {
  hash: string
  description: string
  /** Lado del mercado que opera (ausente = largo, como los specs antiguos). */
  direction?: GenDirection
  fitness: number
  equity: number[]
  /**
   * Retorno DENTRO DE MUESTRA sobre la zona de evolución: los mismos datos con
   * los que se seleccionó la estrategia. No es una expectativa, y quien lo
   * muestre tiene que decirlo — es el número que el gating existe para no
   * creerse.
   */
  total_return_pct: number
  max_drawdown_pct: number
  n_trades: number
}

/** Qué fue de una estrategia que se mostró durante la evolución. */
export type Disposition = 'in_book' | 'variant' | 'rejected' | 'not_gated'

export interface ShowcaseRow {
  hash: string
  description: string
  direction?: GenDirection
  fitness: number
  total_return_pct: number
  max_drawdown_pct: number
  n_trades: number
  disposition: Disposition
  detail?: { failed_checks: string[]; near_miss: NearMiss | null } | null
}

/**
 * Rastro de auditoría de la ejecución.
 *
 * Cierra el salto entre lo que se ve durante la evolución —curvas de equity con
 * retornos llamativos— y lo que sale en el informe. Sin él, una candidata que se
 * vio hacer un +33 % puede no volver a aparecer, y desde fuera es imposible
 * distinguir «la descartaron por sobreajuste» de «se perdió por el camino».
 */
export interface Showcase {
  shown: number
  counts: Partial<Record<Disposition, number>>
  rows: ShowcaseRow[]
  note: string
}

export interface EvolutionProgress {
  phase: 'evolving' | 'gating' | 'refining' | 'cross_validating' | 'done'
  generation?: number
  generations_total?: number
  /** Ronda de búsqueda hasta objetivo (semilla fresca por ronda). */
  restart?: number
  restarts_total?: number
  best?: number
  mean?: number
  diversity?: number
  island_best?: number[]
  mutation_rate?: number
  stagnation?: number
  hypermutation?: boolean
  evaluations?: number
  history: GenerationHistoryPoint[]
  top?: EvolutionCandidate[]
  gating?: { current: number; total: number; passed: number; candidate?: string }
  refining?: { current: number; total: number; candidate?: string }
  cross?: { current: number; total: number; basket: string[]; candidate?: string }
  passed?: number
}

export interface StatusResponse {
  job_id: string
  status: JobStatus
  result?: JobResult
  error?: string
  progress?: EvolutionProgress
}

export function isGenerationReport(r: JobResult | undefined): r is GenerationReport {
  return !!r && !('error' in r) && 'ranking' in r
}

// ── Historial persistido ───────────────────────────────────────────

export interface SavedStrategy {
  id: number
  asset_symbol: string | null
  name: string
  spec: StrategySpec
  spec_hash: string
  interval: string
  rank: number
  fitness: number | null
  robustness_metrics: GatingMetrics | null
  gating_checks: GatingChecks | null
  holdout_metrics: HoldoutMetrics | null
  status: string
  is_monitored: boolean
  last_signal: LiveSignal
  last_signal_at: string | null
  generated_at: string | null
  created_at: string
}

// ── Dossier de auditoría de una estrategia guardada ────────────────

export interface DossierWfMatrix {
  rows: { n_splits: number; folds: number[]; mean_oos_sharpe: number; efficiency: number }[]
  total_folds: number
  positive_folds: number
  stability_score: number
  note: string
}

export interface StrategyDossier {
  status: 'OK'
  identity: {
    strategy_id: number
    name: string
    description: string
    spec: StrategySpec
    spec_hash: string
    asset_symbol: string | null
    asset_name: string | null
    interval: string
    rank: number
    fitness: number | null
    status: string
    is_monitored: boolean
    last_signal: string
    last_signal_at: string | null
    generated_at: string | null
    created_at: string | null
  }
  stored_evidence: {
    robustness_metrics: (GatingMetrics & { cross_consistency?: number }) | null
    gating_checks: GatingChecks | null
    holdout_metrics: HoldoutMetrics | null
    note: string
  }
  fresh_analysis: {
    available: boolean
    candles?: number
    data_source?: string
    equity?: { equity: number[]; total_return_pct: number; max_drawdown_pct: number; n_trades: number }
    walk_forward_matrix?: DossierWfMatrix
    note?: string
  }
  track_record: {
    accounts: {
      account_id: number
      started_at: string | null
      is_active: boolean
      initial_capital: number
      equity: number
      total_return_pct: number | null
      realized_pnl: number
      in_position: boolean
      live_enabled: boolean
      decayed: boolean
    }[]
    note: string
  }
  note: string
}

// ── Comparador cara a cara de estrategias guardadas ─────────────────

export interface CompareItem {
  strategy_id: number
  label: string
  asset_symbol: string | null
  interval: string
  description: string
  spec_hash: string
  generated_at: string | null
  stored: {
    fitness: number | null
    sharpe: number | null
    mean_oos_sharpe: number | null
    pbo: number | null
    wf_efficiency: number | null
    n_trades: number | null
    max_drawdown_pct: number | null
    cross_consistency: number | null
    holdout_return_pct: number | null
    holdout_sharpe: number | null
  }
  fresh: {
    available: boolean
    candles?: number
    data_source?: string
    equity?: number[]
    window_return_pct?: number | null
    oos_sharpe?: number | null
    wf_efficiency?: number | null
  }
}

export interface StrategyComparison {
  status: 'OK'
  items: CompareItem[]
  correlation: { labels: string[]; matrix: (number | null)[][]; common_days: number } | null
  verdicts: {
    best_fitness: string | null
    best_holdout: string | null
    best_fresh: string | null
    best_generalization: string | null
    most_diversifying_pair: { a: string; b: string; corr: number } | null
  }
  note: string
}

// ── Análisis profundo de robustez (suite completa + multi-activo) ──

export interface CrossAssetRow {
  symbol: string
  ok: boolean
  oos_sharpe?: number
  sharpe?: number
  total_return_pct?: number
  max_drawdown_pct?: number
  n_trades?: number
  note?: string
}

export interface SpecRobustnessReport {
  spec: StrategySpec
  description: string
  asset_symbol: string
  interval: string
  data_source: string
  candles_count: number
  robustness_score: number
  verdict: 'ROBUSTA' | 'FRÁGIL' | 'SOBREAJUSTADA'
  explanation: string
  reasons: string[]
  strengths: string[]
  component_scores: Record<string, number>
  metrics: { sharpe: number; sortino: number; calmar: number; max_drawdown_pct: number; profit_factor: number | null; exposure_pct: number }
  diagnostics: {
    deflated_sharpe: { dsr: number | null }
    pbo: { pbo: number | null }
    walk_forward_anchored: { efficiency: number | null; mean_oos_sharpe: number | null }
    monte_carlo: { prob_profit_pct: number | null; return_pct: { p5: number | null; p50: number | null } }
    permutation: { p_value: number | null; significant: boolean }
    lookahead: { is_leaky: boolean }
  }
  cross_asset: {
    n_assets: number
    n_positive_oos: number
    consistency_score: number
    results: CrossAssetRow[]
  }
}

export type RobustnessJobResult = SpecRobustnessReport | { error: string }

export interface RobustnessStatusResponse {
  job_id: string
  status: JobStatus
  result?: RobustnessJobResult
}

export function isSpecRobustnessReport(r: RobustnessJobResult | undefined): r is SpecRobustnessReport {
  return !!r && !('error' in r) && 'robustness_score' in r
}

/**
 * Acción que emite una estrategia en vivo.
 *
 * Cuatro, no dos. `SELL` es cerrar un largo y `SHORT` es abrir un corto: se
 * parecen en la superficie y significan lo contrario, así que no pueden
 * compartir etiqueta.
 */
export type LiveSignal = 'BUY' | 'SELL' | 'SHORT' | 'COVER' | 'HOLD'

/** Acción que llega a registrarse como evento (todo menos «sin cambios»). */
export type ActionableSignal = Exclude<LiveSignal, 'HOLD'>

export const SIGNAL_LABELS: Record<LiveSignal, string> = {
  BUY: 'Compra',
  SELL: 'Venta',
  SHORT: 'Apertura en corto',
  COVER: 'Cierre de corto',
  HOLD: 'Sin cambios',
}

/** Texto del distintivo (cabe en una insignia; la etiqueta larga va en el title). */
export const SIGNAL_BADGES: Record<LiveSignal, string> = {
  BUY: 'COMPRA',
  SELL: 'VENTA',
  SHORT: 'CORTO',
  COVER: 'CIERRE',
  HOLD: 'ESPERA',
}

/**
 * Color del distintivo. El código es la ACCIÓN, no la dirección del mercado:
 * abrir va en color pleno (verde el largo, rosa el corto) y cerrar en un tono
 * apagado, para que de un vistazo se distinga «entrar» de «salir» — que es la
 * confusión que se paga cara cuando además hay dos lados.
 */
export const SIGNAL_STYLES: Record<LiveSignal, string> = {
  BUY: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  SELL: 'bg-red-500/15 text-red-400 border-red-500/30',
  SHORT: 'bg-rose-500/15 text-rose-400 border-rose-500/30',
  COVER: 'bg-sky-500/15 text-sky-400 border-sky-500/30',
  HOLD: 'bg-slate-700/40 text-slate-400 border-slate-600/40',
}

export interface SignalState {
  strategy_id: number
  asset_symbol: string
  interval: string
  description: string
  signal: LiveSignal
  /** Lado que opera la estrategia; `side` dice a cuál se refiere ESTA señal. */
  direction?: 'long' | 'short' | 'both'
  side?: 'long' | 'short' | null
  entry_active: boolean
  exit_active: boolean
  short_entry_active?: boolean
  short_exit_active?: boolean
  conditions: { side: 'entry' | 'exit' | 'short_entry' | 'short_exit'; desc: string; active: boolean }[]
  as_of_ts: number | null
  error?: string
}

export interface SignalEvent {
  id: number
  strategy_id: number
  asset_symbol: string | null
  name: string
  signal: ActionableSignal
  price: number | null
  notified: boolean
  created_at: string
}

// ── Paper trading (cartera virtual que sigue una estrategia) ────────
export interface PaperAccount {
  id: number
  strategy_id: number
  strategy_name: string | null
  asset_symbol: string
  interval: string
  initial_capital: number
  cash: number
  units: number
  entry_price: number | null
  last_price: number | null
  position_value: number
  equity: number
  realized_pnl: number
  total_return_pct: number
  drawdown_pct: number
  in_position: boolean
  is_active: boolean
  decayed: boolean
  decayed_at: string | null
  live_enabled: boolean
  live_connection_id: number | null
  live_is_testnet: boolean | null
  live_cap_usd: number
  live_base_position: number
  live_error: string | null
  live_reconciled_at?: string | null
  live_discrepancy?: number | null
  trades_count: number
  wins: number
  win_rate: number | null
  last_signal: LiveSignal
  last_eval_at: string | null
  started_at: string
}

export interface PaperEquityPoint {
  t: string
  equity: number
  price: number
}

export interface PaperTrade {
  id: number
  side: 'BUY' | 'SELL'
  price: number
  fill_price: number
  units: number
  cost: number
  cash_after: number
  equity_after: number
  pnl: number | null
  pnl_pct: number | null
  created_at: string
}

export interface LiveOrderAudit {
  account_id: number
  slippage?: { n_filled: number; avg_slippage_bps: number | null; modeled_slippage_bps: number }
  blocked_orders?: number
  orders: {
    id: number
    side: 'buy' | 'sell'
    symbol: string
    amount: number
    ref_price: number
    fill_price: number | null
    slippage_bps: number | null
    notional_usd: number
    is_testnet: boolean
    status: 'sent' | 'failed' | 'blocked'
    error: string | null
    broker_order_id: string | null
    created_at: string
  }[]
  orders_sent: number
  orders_failed: number
  live_realized_pnl_usd: number
  pnl_is_estimate: boolean
  paper_realized_pnl_usd: number
  note: string
}

export interface PaperAccountDetail extends PaperAccount {
  trades: PaperTrade[]
  equity_curve: PaperEquityPoint[]
}

// ── Mejor estrategia por activo (campeona) con track record en vivo ─
export interface BestStrategy {
  strategy_id: number
  asset_symbol: string | null
  name: string
  interval: string
  fitness: number | null
  holdout_return_pct: number | null
  holdout_sharpe: number | null
  generated_at: string | null
  is_monitored: boolean
  live: {
    account_id: number
    total_return_pct: number
    realized_pnl: number
    trades_count: number
    is_active: boolean
  } | null
}

// ── Cartera de estrategias campeonas (correlación + equity conjunta) ─
export interface PortfolioMember {
  strategy_id: number
  label: string
  name: string
  asset_symbol: string
  interval: string
  fitness: number | null
  window_return_pct: number | null
  /** Peso asignado por paridad de riesgo jerárquica (HRP). */
  hrp_weight?: number | null
}

/**
 * Asignación por paridad de riesgo jerárquica.
 *
 * Equiponderar da el mismo capital a una estrategia tranquila que a otra que
 * triplica su volatilidad, y trata tres clones del mismo edge como tres
 * apuestas distintas. HRP agrupa por correlación y reparte por varianza
 * inversa, sin invertir la matriz de covarianzas — que es lo que hace que
 * Markowitz amplifique el error de estimación.
 */
export interface HrpAllocation {
  n_assets: number
  weights?: Record<string, number>
  order?: number[]
  ordered_labels?: string[]
  portfolio_volatility?: number
  equal_weight_volatility?: number
  /** 1/HHI: cuántas estrategias aporta REALMENTE la cartera. */
  effective_n_strategies?: number
  mean_correlation?: number
  note?: string
}

export interface StrategyPortfolio {
  members: PortfolioMember[]
  labels: string[]
  correlation_matrix: (number | null)[][]
  avg_correlation: number | null
  common_days: number
  portfolio: {
    equity: { date: string; value: number }[]
    total_return_pct: number
    max_drawdown_pct: number
    sharpe: number
  }
  allocation?: HrpAllocation
  note: string
  error?: string
}

// ── Servicio ───────────────────────────────────────────────────────

export const strategyGeneratorService = {
  /** Lanza el generador para un activo y devuelve el job_id (no bloquea). */
  async launch(payload: GenerateRequest): Promise<LaunchResponse> {
    const { data } = await apiClient.post<LaunchResponse>('/strategies/generate/', payload)
    return data
  },

  /** Consulta el estado/resultado de un job de generación. */
  async getStatus(jobId: string): Promise<StatusResponse> {
    const { data } = await apiClient.get<StatusResponse>(`/strategies/generate/${jobId}/`)
    return data
  },

  /** Historial de estrategias robustas guardadas (StrategyDefinition). */
  async listSaved(params?: { asset_symbol?: string; interval?: string; limit?: number }): Promise<SavedStrategy[]> {
    const { data } = await apiClient.get<{ count: number; results: SavedStrategy[] }>('/strategies/', { params })
    return data.results
  },

  /** Dossier de auditoría de una estrategia guardada (documento imprimible). */
  async getDossier(strategyId: number): Promise<StrategyDossier> {
    const { data } = await apiClient.get<StrategyDossier>(`/strategies/${strategyId}/dossier/`)
    return data
  },

  /** Comparador cara a cara de 2-4 estrategias guardadas. */
  async compare(ids: number[]): Promise<StrategyComparison> {
    const { data } = await apiClient.get<StrategyComparison>('/strategies/compare/', {
      params: { ids: ids.join(',') },
    })
    return data
  },

  /** Lanza el análisis profundo de robustez de un spec (suite + multi-activo). */
  async launchRobustness(payload: { spec?: StrategySpec; strategy_id?: number; asset_symbol: string; interval?: string; preset?: GenPreset }): Promise<LaunchResponse> {
    const { data } = await apiClient.post<LaunchResponse>('/strategies/robustness/', payload)
    return data
  },

  /** Consulta el estado/resultado del análisis profundo. */
  async getRobustnessStatus(jobId: string): Promise<RobustnessStatusResponse> {
    const { data } = await apiClient.get<RobustnessStatusResponse>(`/strategies/robustness/${jobId}/`)
    return data
  },

  /** Activa/desactiva la monitorización en vivo de una estrategia guardada. */
  async setMonitor(strategyId: number, active: boolean): Promise<{ strategy_id: number; is_monitored: boolean }> {
    const { data } = await apiClient.post(`/strategies/${strategyId}/monitor/`, { active })
    return data
  },

  /** Señal actual (BUY/SELL/HOLD) de una estrategia guardada. */
  async getSignal(strategyId: number): Promise<SignalState> {
    const { data } = await apiClient.get<SignalState>(`/strategies/${strategyId}/signal/`)
    return data
  },

  /** Historial reciente de señales disparadas por las estrategias monitorizadas. */
  async listSignalEvents(limit = 30): Promise<SignalEvent[]> {
    const { data } = await apiClient.get<{ count: number; results: SignalEvent[] }>('/strategies/signals/recent/', { params: { limit } })
    return data.results
  },

  /** Carteras de paper trading del usuario (siguen una estrategia en vivo). */
  async listPaperAccounts(): Promise<PaperAccount[]> {
    const { data } = await apiClient.get<{ count: number; results: PaperAccount[] }>('/strategies/paper/')
    return data.results
  },

  /** Lanza una cartera virtual que sigue una estrategia generada. */
  async startPaperAccount(strategyId: number, initialCapital?: number): Promise<PaperAccount> {
    const { data } = await apiClient.post<PaperAccount>('/strategies/paper/', {
      strategy_id: strategyId,
      ...(initialCapital ? { initial_capital: initialCapital } : {}),
    })
    return data
  },

  /** Detalle de una cartera con su historial de operaciones. */
  async getPaperAccount(accountId: number): Promise<PaperAccountDetail> {
    const { data } = await apiClient.get<PaperAccountDetail>(`/strategies/paper/${accountId}/`)
    return data
  },

  /** Auditoría de las órdenes reales espejadas por la promoción. */
  async getPaperLiveOrders(accountId: number): Promise<LiveOrderAudit> {
    const { data } = await apiClient.get<LiveOrderAudit>(`/strategies/paper/${accountId}/live/orders/`)
    return data
  },

  /** Activa/desactiva la ejecución REAL de una cartera (promoción con tope). */
  async setPaperLive(accountId: number, payload: { enable: boolean; connection_id?: number; cap_usd?: number }): Promise<{
    id: number; live_enabled: boolean; live_cap_usd?: number; live_is_testnet?: boolean
  }> {
    const { data } = await apiClient.post(`/strategies/paper/${accountId}/live/`, payload)
    return data
  },

  /** Detiene una cartera de paper trading (deja de operar). */
  async stopPaperAccount(accountId: number): Promise<{ id: number; is_active: boolean }> {
    const { data } = await apiClient.delete(`/strategies/paper/${accountId}/`)
    return data
  },

  /** Análisis de cartera de las campeonas: correlaciones + equity conjunta. */
  async getStrategyPortfolio(top = 5): Promise<StrategyPortfolio> {
    const { data } = await apiClient.get<StrategyPortfolio>('/strategies/portfolio/', { params: { top } })
    return data
  },

  /** Mejor estrategia validada de cada activo (campeona) con su track record. */
  async getBestStrategies(interval?: string): Promise<BestStrategy[]> {
    const { data } = await apiClient.get<{ count: number; results: BestStrategy[] }>(
      '/strategies/best/', { params: interval ? { interval } : {} },
    )
    return data.results
  },
}
