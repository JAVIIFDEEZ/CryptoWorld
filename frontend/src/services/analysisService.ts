/**
 * services/analysisService.ts — Servicio para activos y análisis.
 *
 * Encapsula las llamadas HTTP a:
 *   GET  /api/assets         — listar activos
 *   POST /api/analysis/run   — solicitar análisis técnico
 *
 * Estructura lista para ampliar con más endpoints en fases del TFG:
 *   GET /api/assets/:symbol/history
 *   GET /api/analysis/:id
 *   etc.
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
}

export interface AnalysisRequest {
  asset_symbol: string
  analysis_type: 'RSI' | 'MACD' | 'SMA' | 'EMA' | 'BOLLINGER'
}

export interface AnalysisResult {
  id: number
  asset_symbol: string
  analysis_type: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  result: Record<string, unknown> | null
}

// ── Servicio ───────────────────────────────────────────────────────

export const analysisService = {
  /**
   * Obtener listado de todos los activos criptográficos.
   * GET /api/assets
   * Requiere autenticación JWT.
   */
  async getAssets(): Promise<CryptoAsset[]> {
    const { data } = await apiClient.get<CryptoAsset[]>('/assets/')
    return data
  },

  /**
   * Solicitar la ejecución de un análisis técnico.
   * POST /api/analysis/run
   * Requiere autenticación JWT.
   */
  async runAnalysis(payload: AnalysisRequest): Promise<AnalysisResult> {
    const { data } = await apiClient.post<AnalysisResult>('/analysis/run/', payload)
    return data
  },
}
