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

export interface GenerateRequest {
  asset_symbol: string
  interval?: string
  limit?: number
  initial_capital?: number
  preset?: GenPreset
  optimizer?: 'single' | 'nsga'
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

/** Una condición compilable del StrategySpec (umbral o cruce). */
export interface SpecCondition {
  type: 'threshold' | 'cross'
  indicator?: string
  params?: Record<string, number>
  op: string
  threshold?: number
  a?: { indicator: string; params: Record<string, number> }
  b?: { indicator: string; params: Record<string, number> }
}

export interface StrategySpec {
  entry: { combine: 'AND' | 'OR'; conditions: SpecCondition[] }
  exit: { combine: 'AND' | 'OR'; conditions: SpecCondition[] }
}

export interface GatingChecks {
  min_trades: boolean
  no_lookahead: boolean
  wf_efficiency: boolean
  pbo: boolean
  mc_p5_positive: boolean
}

export interface GatingMetrics {
  n_trades: number
  total_return_pct: number
  max_drawdown_pct: number
  exposure_pct: number
  sharpe: number
  sortino: number
  wf_efficiency: number
  mean_oos_sharpe: number
  pbo: number | null
  turnover?: number
  cost_drag_pct?: number
  exit_reasons?: Record<string, number>
  monte_carlo: { prob_profit_pct: number | null; return_p5_pct: number | null; return_p50_pct: number | null }
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
}

/** Coordenadas de robustez de una candidata (para el universo 3D). */
export interface Candidate {
  spec_hash: string
  description: string
  fitness: number
  passed_gating: boolean
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
}

export interface GenerationReport {
  asset_symbol: string
  interval: string
  data_source: string
  preset: string
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
  ga_evolution: { history: GenerationHistoryPoint[]; evaluations: number; best_fitness: number }
  pareto_frontier?: ParetoPoint[]
  summary: { candidates_gated: number; passed_gating: number; rejected: number }
  ranking: Finalist[]
  candidates: Candidate[]
  rejected: (Candidate & { failed_checks: string[] })[]
  persisted?: { id: number; spec_hash: string; rank: number }[]
}

export type JobResult = GenerationReport | { error: string }

export interface StatusResponse {
  job_id: string
  status: JobStatus
  result?: JobResult
  error?: string
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
  last_signal: string
  last_signal_at: string | null
  generated_at: string | null
  created_at: string
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

export interface SignalState {
  strategy_id: number
  asset_symbol: string
  interval: string
  description: string
  signal: 'BUY' | 'SELL' | 'HOLD'
  entry_active: boolean
  exit_active: boolean
  conditions: { side: 'entry' | 'exit'; desc: string; active: boolean }[]
  as_of_ts: number | null
  error?: string
}

export interface SignalEvent {
  id: number
  strategy_id: number
  asset_symbol: string | null
  name: string
  signal: 'BUY' | 'SELL'
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
  trades_count: number
  wins: number
  win_rate: number | null
  last_signal: 'BUY' | 'SELL' | 'HOLD'
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
