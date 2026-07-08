/**
 * services/analysisService.ts — Servicio para activos y análisis técnico avanzado.
 *
 * Encapsula las llamadas HTTP a:
 *   GET  /api/assets              — listar activos
 *   POST /api/analysis/calculate  — cálculo individual de indicador
 *   POST /api/analysis/signals    — panel multi-indicador con semáforos
 *   POST /api/analysis/predict    — predicción ML
 *   POST /api/analysis/patterns   — detección de patrones de velas
 *   POST /api/analysis/backtest   — backtesting de estrategias
 *   GET  /api/analysis/strategies — listar estrategias disponibles
 */

import apiClient from './api'

// ── Tipos ──────────────────────────────────────────────────────────

export interface CryptoAsset {
  id: number
  symbol: string
  name: string
  current_price: string
  market_cap: string | null
  volume_24h: string | null
  price_change_24h: string | null
  is_bullish_24h: boolean
  logo_url: string | null
  coingecko_id: string | null
}

export type AnalysisType = 'RSI' | 'MACD' | 'SMA' | 'EMA' | 'BOLLINGER'
export type IntervalType = '1m' | '5m' | '15m' | '1h' | '4h' | '1d'

export interface AnalysisRequest {
  asset_symbol: string
  analysis_type: AnalysisType
  interval?: IntervalType
  limit?: number
}

export interface AnalysisResult {
  id: number
  asset_symbol: string
  analysis_type: string
  status: string
  result: Record<string, unknown> | null
}

// Señales
export interface SignalIndicator {
  name: string
  value: number | string
  signal: string
}

export interface SignalsSummary {
  verdict: string
  score: number
  buy_count: number
  sell_count: number
  neutral_count: number
  total: number
}

export interface SignalsResult {
  asset_symbol: string
  interval: string
  indicators: SignalIndicator[]
  summary: SignalsSummary
  last_price: number
  error?: string
}

// Predicción
export interface FeatureImportance {
  feature: string
  importance: number
}

// Explicabilidad local: contribución de cada feature a ESTA predicción
export interface PredictionDriver {
  feature: string
  contribution: number
}

export interface PredictionResult {
  prediction: string
  confidence: number
  prob_up?: number
  neutral_band?: number
  horizon: number
  model?: string
  calibrated?: boolean
  brier_score?: number | null
  cv_accuracy?: number
  cv_std?: number
  oos_accuracy?: number
  baseline_accuracy?: number
  edge?: number
  precision_up?: number
  recall_up?: number
  f1_up?: number
  auc?: number | null
  n_oos?: number
  n_train?: number
  n_splits?: number
  up_rate?: number
  verdict?: 'EDGE' | 'WEAK' | 'NO_EDGE'
  verdict_text?: string
  features_importance?: FeatureImportance[]
  drivers?: PredictionDriver[]
  elapsed_ms?: number
  disclaimer?: string
  asset_symbol?: string
  interval?: string
  message?: string
  error?: string
}

// Historial real de predicciones (verificadas a posteriori)
export interface PredictionTrackRecordItem {
  id: number
  asset_symbol: string
  interval: string
  horizon: number
  predicted: string
  confidence: number
  verdict: string
  status: 'pending' | 'correct' | 'incorrect' | 'unresolved'
  actual_direction: string | null
  actual_return_pct: number | null
  created_at: string
  resolve_at: string
}

export interface PredictionTrackRecord {
  total: number
  resolved: number
  pending: number
  correct: number
  accuracy: number | null
  by_verdict: Record<string, { n: number; accuracy: number }>
  recent: PredictionTrackRecordItem[]
}

// Monitorización de drift del modelo (prometido OOS vs realizado en vivo)
export interface PredictionMonitoringBucket {
  from: string
  to: string
  n: number
  accuracy: number
}

export interface PredictionMonitoring {
  status: 'ok' | 'watch' | 'drift' | 'insufficient'
  message: string
  expected_accuracy: number | null
  realized_accuracy: number | null
  gap: number | null
  n_resolved: number
  min_sample: number
  series: PredictionMonitoringBucket[]
  by_asset: Record<string, { n: number; accuracy: number }>
  thresholds: { watch: number; drift: number }
}

// Confluencia multi-marco temporal (MTF)
export interface MtfFrame {
  interval: string
  weight: number
  verdict?: string
  score?: number
  max_score?: number
  normalized?: number
  buy_count?: number
  neutral_count?: number
  sell_count?: number
  last_price?: number | null
  error?: string
}

export interface MtfConfluence {
  asset_symbol: string
  frames: MtfFrame[]
  frames_analyzed: number
  alignment_score: number
  agreement_pct: number
  verdict: 'ALINEADO_ALCISTA' | 'ALINEADO_BAJISTA' | 'MIXTO' | 'NEUTRAL'
  verdict_text: string
  disclaimer?: string
  error?: string
}

// Estructura de precio: soportes/resistencias + divergencias
export interface PriceLevel {
  price: number
  touches: number
  kind: 'support' | 'resistance'
  distance_pct: number
}

export interface Divergence {
  type: 'bearish' | 'bullish'
  detail: string
  price_from: number
  price_to: number
  rsi_from: number
  rsi_to: number
}

export interface PriceStructure {
  asset_symbol: string
  interval: string
  last_price: number
  levels: PriceLevel[]
  nearest_support: PriceLevel | null
  nearest_resistance: PriceLevel | null
  divergences: Divergence[]
  candles_analyzed: number
  data_source: string
  note: string
  error?: string
}

// Patrones
export interface CandlePattern {
  name: string
  index: number
  signal: string
  reliability: string
  description: string
}

export interface PatternsResult {
  asset_symbol: string
  interval: string
  total_candles: number
  patterns: CandlePattern[]
  error?: string
}

// Backtest
export interface BacktestTrade {
  entry_index: number
  exit_index: number
  entry_price: number
  exit_price: number
  pnl_pct: number
  result: string
  exit_reason?: string
}

export interface BacktestResult {
  strategy: string
  strategy_key: string
  description: string
  asset_symbol?: string
  interval?: string
  initial_capital: number
  final_capital: number
  total_return_pct: number
  buy_hold_return_pct: number
  start_date?: string
  end_date?: string
  candles_count?: number
  total_trades: number
  win_rate_pct: number
  avg_win_pct: number
  avg_loss_pct: number
  max_drawdown_pct: number
  total_commission_pct?: number
  turnover?: number
  exit_reasons?: Record<string, number>
  commission_bps?: number
  slippage_bps?: number
  trades: BacktestTrade[]
  error?: string
}

export interface BacktestOptions {
  commission_bps?: number
  slippage_bps?: number
  stop_loss_pct?: number | null
  take_profit_pct?: number | null
}

export interface StrategyInfo {
  key: string
  name: string
  description: string
}

// Motor de confluencia 360° (técnica + ML + on-chain + noticias)
export interface ConfluenceSource {
  available: boolean
  score: number | null
  detail: string
  weight: number
  weight_mode: 'aprendido_activo' | 'aprendido_global' | 'a_priori'
  hit_rate: number | null
  sample: number
}

export interface ConfluenceReading {
  asset_symbol: string
  score: number
  verdict: 'CONFLUENCIA_ALCISTA' | 'CONFLUENCIA_BAJISTA' | 'MIXTO' | 'NEUTRAL' | 'INSUFICIENTE'
  verdict_text: string
  agreement_pct: number
  sources_available: number
  sources: Record<string, ConfluenceSource>
  track_record?: {
    overall: { n: number; hit_rate: number | null; avg_signed_return_pct: number | null }
    by_verdict: Record<string, { n: number; hit_rate: number | null; avg_signed_return_pct: number | null }>
  }
  backtest?: {
    status: 'OK' | 'INSUFICIENTE'
    trades: number
    total_return_pct?: number
    win_rate?: number
    avg_trade_pct?: number
    max_drawdown_pct?: number
    profit_factor?: number | null
    cost_bps?: number
    equity_curve?: number[]
  }
  horizon_hours: number
  note: string
  error?: string
}

// ── Caché en memoria con TTL ───────────────────────────────────────
const _cache = new Map<string, { data: unknown; expires: number }>()
function _cGet<T>(key: string): T | null {
  const entry = _cache.get(key)
  if (!entry || Date.now() > entry.expires) { _cache.delete(key); return null }
  return entry.data as T
}
function _cSet(key: string, data: unknown, ttlMs: number): void {
  _cache.set(key, { data, expires: Date.now() + ttlMs })
}

// ── Servicio ───────────────────────────────────────────────────────

export const analysisService = {
  async getAssets(): Promise<CryptoAsset[]> {
    const cached = _cGet<CryptoAsset[]>('assets')
    if (cached) return cached
    const { data } = await apiClient.get<CryptoAsset[]>('/assets/')
    _cSet('assets', data, 60_000)  // 60 segundos
    return data
  },

  /** Cálculo individual de indicador con datos reales. */
  async calculateIndicator(payload: AnalysisRequest): Promise<AnalysisResult> {
    const { data } = await apiClient.post<AnalysisResult>('/analysis/calculate/', payload)
    return data
  },

  /** Panel multi-indicador con semáforos y veredicto. */
  async getSignals(assetSymbol: string, interval: IntervalType = '1h'): Promise<SignalsResult> {
    const { data } = await apiClient.post<SignalsResult>('/analysis/signals/', {
      asset_symbol: assetSymbol,
      interval,
    })
    return data
  },

  /** Confluencia multi-marco temporal: señales en 15m/1h/4h/1d con alineación. */
  async getMtfConfluence(assetSymbol: string): Promise<MtfConfluence> {
    const { data } = await apiClient.get<MtfConfluence>('/analysis/mtf/', {
      params: { asset_symbol: assetSymbol },
    })
    return data
  },

  /** Soportes/resistencias por pivotes + divergencias RSI/precio. */
  async getPriceStructure(assetSymbol: string, interval: IntervalType = '1h'): Promise<PriceStructure> {
    const { data } = await apiClient.get<PriceStructure>('/analysis/levels/', {
      params: { asset_symbol: assetSymbol, interval },
    })
    return data
  },

  /** Predicción ML de dirección de precio. El primer cálculo entrena y valida
   * el ensemble (walk-forward) y puede tardar bastante más que el timeout
   * global de 10 s, sobre todo en máquinas modestas; luego queda cacheado
   * 15 min en el backend. Timeout propio holgado para no abortar ese primer
   * entrenamiento. */
  async predict(assetSymbol: string, interval: IntervalType = '1h', horizon = 5): Promise<PredictionResult> {
    const { data } = await apiClient.post<PredictionResult>(
      '/analysis/predict/',
      { asset_symbol: assetSymbol, interval, horizon },
      { timeout: 90_000 },
    )
    return data
  },

  /** Motor de confluencia 360°: fusión de las 4 fuentes con pesos aprendidos. */
  async getConfluence(assetSymbol: string): Promise<ConfluenceReading> {
    const { data } = await apiClient.get<ConfluenceReading>('/analysis/confluence/', {
      params: { symbol: assetSymbol }, timeout: 90_000,
    })
    return data
  },

  /** Historial real de aciertos de las predicciones (bucle de mejora continua). */
  async getPredictionTrackRecord(): Promise<PredictionTrackRecord> {
    const { data } = await apiClient.get<PredictionTrackRecord>('/analysis/predictions/')
    return data
  },

  /** Monitorización de drift del modelo (prometido OOS vs realizado en vivo). */
  async getPredictionMonitoring(): Promise<PredictionMonitoring> {
    const { data } = await apiClient.get<PredictionMonitoring>('/analysis/predictions/monitoring/')
    return data
  },

  /** Detección de patrones de velas japonesas. */
  async detectPatterns(assetSymbol: string, interval: IntervalType = '1h'): Promise<PatternsResult> {
    const { data } = await apiClient.post<PatternsResult>('/analysis/patterns/', {
      asset_symbol: assetSymbol,
      interval,
    })
    return data
  },

  /** Backtesting de una estrategia. */
  async backtest(
    assetSymbol: string,
    strategy: string,
    interval: IntervalType = '1h',
    limit = 1000,
    initialCapital = 10000,
    options: BacktestOptions = {},
  ): Promise<BacktestResult> {
    const { data } = await apiClient.post<BacktestResult>('/analysis/backtest/', {
      asset_symbol: assetSymbol,
      strategy,
      interval,
      limit,
      initial_capital: initialCapital,
      ...options,
    })
    return data
  },

  /** Listar estrategias disponibles para backtesting. */
  async getStrategies(): Promise<StrategyInfo[]> {
    const { data } = await apiClient.get<StrategyInfo[]>('/analysis/strategies/')
    return data
  },

  /** Mantener compatibilidad con el endpoint antiguo. */
  async runAnalysis(payload: { asset_symbol: string; analysis_type: string }): Promise<AnalysisResult> {
    const { data } = await apiClient.post<AnalysisResult>('/analysis/run/', payload)
    return data
  },
}
