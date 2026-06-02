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

export interface PredictionResult {
  prediction: string
  confidence: number
  horizon: number
  model?: string
  cv_accuracy?: number
  cv_std?: number
  features_importance?: FeatureImportance[]
  disclaimer?: string
  asset_symbol?: string
  interval?: string
  message?: string
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
  trades: BacktestTrade[]
  error?: string
}

export interface StrategyInfo {
  key: string
  name: string
  description: string
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

  /** Predicción ML de dirección de precio. */
  async predict(assetSymbol: string, interval: IntervalType = '1h', horizon = 5): Promise<PredictionResult> {
    const { data } = await apiClient.post<PredictionResult>('/analysis/predict/', {
      asset_symbol: assetSymbol,
      interval,
      horizon,
    })
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
  ): Promise<BacktestResult> {
    const { data } = await apiClient.post<BacktestResult>('/analysis/backtest/', {
      asset_symbol: assetSymbol,
      strategy,
      interval,
      limit,
      initial_capital: initialCapital,
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
