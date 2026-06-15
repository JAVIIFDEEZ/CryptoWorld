/**
 * services/robustnessService.ts — Suite de robustez de backtest.
 *
 * La suite corre como tarea Celery (cientos de backtests), así que el flujo
 * es asíncrono: launch() lanza la tarea y devuelve un job_id; getStatus()
 * consulta el estado hasta que el informe está listo.
 */

import apiClient from './api'

// ── Petición ───────────────────────────────────────────────────────

export type RobustStrategy =
  | 'rsi_reversal' | 'macd_crossover' | 'bollinger_bounce' | 'sma_crossover' | 'ema_trend'

export type RobustObjective = 'sharpe' | 'sortino' | 'calmar' | 'total_return'

export type RobustPreset = 'fast' | 'balanced' | 'thorough'

export interface RobustnessRequest {
  asset_symbol: string
  strategy: RobustStrategy
  interval?: string
  initial_capital?: number
  objective?: RobustObjective
  preset?: RobustPreset
}

export interface ComparisonRequest {
  asset_symbol: string
  interval?: string
  objective?: RobustObjective
  preset?: RobustPreset
}

// ── Respuestas ─────────────────────────────────────────────────────

export type JobStatus = 'PENDING' | 'STARTED' | 'RETRY' | 'SUCCESS' | 'FAILURE'

export interface LaunchResponse {
  job_id: string
  status: JobStatus
  poll_url: string
}

export type Verdict = 'ROBUSTA' | 'FRÁGIL' | 'SOBREAJUSTADA'

export interface RobustnessMetrics {
  sharpe: number
  sortino: number
  calmar: number
  annualized_return_pct: number
  annualized_volatility_pct: number
  var_95_pct: number
  cvar_95_pct: number
  profit_factor: number | null
  exposure_pct: number
  max_drawdown_pct: number
}

export interface RobustnessReport {
  asset_symbol: string
  strategy: string
  strategy_name: string
  interval: string
  data_source: string
  candles_count: number
  best_params: Record<string, number>
  robustness_score: number
  verdict: Verdict
  explanation: string
  reasons: string[]
  strengths: string[]
  component_scores: Record<string, number>
  metrics: RobustnessMetrics
  diagnostics: {
    deflated_sharpe: { dsr: number | null; sr_per_period?: number; n_trials?: number; skew?: number; kurtosis?: number }
    pbo: { pbo: number | null; n_partitions?: number; n_configs?: number }
    walk_forward_anchored: { efficiency: number | null; mean_is_sharpe: number | null; mean_oos_sharpe: number | null; n_splits: number }
    walk_forward_rolling: { efficiency: number | null; mean_oos_sharpe: number | null; n_splits: number }
    monte_carlo: {
      n_sims: number
      prob_profit_pct: number | null
      return_pct: { p5: number | null; p50: number | null; p95: number | null }
      max_drawdown_pct: { p5: number | null; p50: number | null; p95: number | null }
    }
    permutation: { p_value: number | null; significant: boolean; observed_sharpe?: number }
    lookahead: { is_leaky: boolean; leaks: number; checked: number }
    recursive_instability: { is_unstable: boolean; max_rel_drift: number }
  }
  charts: {
    oos_equity_curve: number[]
    monte_carlo_distribution: number[]
    trial_ranking: { params: Record<string, number>; value: number }[]
  }
}

export interface ComparisonRow {
  strategy: string
  strategy_name: string
  robustness_score?: number
  verdict?: Verdict
  best_params?: Record<string, number>
  sharpe?: number
  max_drawdown_pct?: number
  pbo?: number | null
  dsr?: number | null
  oos_efficiency?: number | null
  error?: string
}

export interface ComparisonReport {
  asset_symbol: string
  interval: string
  objective: string
  preset: string
  ranking: ComparisonRow[]
  best: ComparisonRow
}

/** Resultado de un job que pudo terminar con error de negocio (p. ej. pocas velas). */
export type JobResult = RobustnessReport | ComparisonReport | { error: string }

export interface StatusResponse {
  job_id: string
  status: JobStatus
  result?: JobResult
  error?: string
}

export function isReport(result: JobResult | undefined): result is RobustnessReport {
  return !!result && !('error' in result) && !('ranking' in result)
}

export function isComparison(result: JobResult | undefined): result is ComparisonReport {
  return !!result && 'ranking' in result
}

// ── Servicio ───────────────────────────────────────────────────────

export const robustnessService = {
  /** Lanza la suite para una estrategia y devuelve el job_id (no bloquea). */
  async launch(payload: RobustnessRequest): Promise<LaunchResponse> {
    const { data } = await apiClient.post<LaunchResponse>('/analysis/backtest/robust/', payload)
    return data
  },

  /** Lanza la comparación de las 5 estrategias y devuelve el job_id. */
  async launchComparison(payload: ComparisonRequest): Promise<LaunchResponse> {
    const { data } = await apiClient.post<LaunchResponse>('/analysis/backtest/robust/compare/', payload)
    return data
  },

  /** Consulta el estado/resultado de un job. */
  async getStatus(jobId: string): Promise<StatusResponse> {
    const { data } = await apiClient.get<StatusResponse>(`/analysis/backtest/robust/${jobId}/`)
    return data
  },
}
