/**
 * services/blockchainService.ts — API calls para métricas on-chain.
 *
 * Endpoint:
 *   GET /api/blockchain/metrics/?symbol=BTC&metric=&days= → Datos históricos
 *
 * Proveedor: Blockchain.com Charts API (solo BTC)
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
}
