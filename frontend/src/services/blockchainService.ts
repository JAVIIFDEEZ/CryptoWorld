/**
 * services/blockchainService.ts — API calls para métricas on-chain.
 *
 * Endpoints:
 *   GET /api/blockchain/metrics/?symbol=BTC&metric=&days=
 *     → Series históricas de BTC (Blockchain.com, solo BTC)
 *
 *   GET /api/blockchain/multichain/?symbol=ETH
 *     → Snapshot de estadísticas actuales multi-chain (Blockchair)
 *     → Chains: BTC, ETH, LTC, DOGE, BCH, XRP, ADA, DOT, XLM, XMR
 */

import apiClient from './api'

export type OnChainMetric =
  | 'active_addresses'
  | 'hashrate'
  | 'tx_count'
  | 'difficulty'
  | 'mempool_size'
  | 'miners_revenue'
  | 'transaction_fees'
  | 'avg_block_size'

export const METRIC_LABELS: Record<OnChainMetric, string> = {
  active_addresses: 'Direcciones activas',
  hashrate: 'Hash Rate',
  tx_count: 'Transacciones diarias',
  difficulty: 'Dificultad de minería',
  mempool_size: 'Tamaño Mempool',
  miners_revenue: 'Ingresos mineros',
  transaction_fees: 'Fees de transacción',
  avg_block_size: 'Tamaño medio de bloque',
}

export interface MetricPoint {
  timestamp: number
  value: number
}

export interface OnChainMetricsResponse {
  symbol: string
  metric: OnChainMetric
  metric_label: string
  description: string
  timespan: string
  total_points: number
  source: string
  data: MetricPoint[]
  error?: string
}

// ── Multi-chain snapshot (Blockchair) ──────────────────────────────

export const MULTICHAIN_SYMBOLS = ['BTC', 'ETH', 'LTC', 'DOGE', 'BCH', 'XRP', 'ADA', 'DOT', 'XLM', 'XMR'] as const
export type MultiChainSymbol = typeof MULTICHAIN_SYMBOLS[number]

export interface MultiChainStatItem {
  key: string
  label: string
  value: number | string | null
  unit: string
}

export interface MultiChainStatsResponse {
  symbol: string
  source: string
  best_block_time: string | null
  best_block_height: number | null
  supported: string[]
  stats: MultiChainStatItem[]
  error?: string
}

export const blockchainService = {
  /** Obtener datos históricos de una métrica on-chain de Bitcoin */
  getMetrics: async (
    metric: OnChainMetric = 'active_addresses',
    days = 30,
  ): Promise<OnChainMetricsResponse> => {
    const params = new URLSearchParams({
      symbol: 'BTC',
      metric,
      days: String(days),
    })
    const { data } = await apiClient.get(`/blockchain/metrics/?${params}`)
    return data
  },

  /** Obtener snapshot de estadísticas actuales para cualquier chain soportada */
  getMultiChainStats: async (symbol: MultiChainSymbol): Promise<MultiChainStatsResponse> => {
    const params = new URLSearchParams({ symbol })
    const { data } = await apiClient.get(`/blockchain/multichain/?${params}`)
    return data
  },
}
