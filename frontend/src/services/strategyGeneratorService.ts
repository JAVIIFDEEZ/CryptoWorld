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
  monte_carlo: { prob_profit_pct: number | null; return_p5_pct: number | null; return_p50_pct: number | null }
  lookahead_leaky: boolean
}

export interface HoldoutMetrics {
  return_pct: number
  sharpe: number
  max_drawdown_pct: number
  n_trades: number
  win_rate_pct: number
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
  ga_evolution: { history: GenerationHistoryPoint[]; evaluations: number; best_fitness: number }
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
  generated_at: string | null
  created_at: string
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
}
