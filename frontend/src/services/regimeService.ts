/**
 * services/regimeService.ts — Correlaciones cross-asset y régimen de mercado.
 *
 * Endpoint: GET /api/market/regime/
 */

import apiClient from './api'

export interface CorrelationPair {
  a: string
  b: string
  corr: number
}

export interface Correlations {
  status: 'OK' | 'INSUFICIENTE'
  symbols: string[]
  matrix: number[][]
  avg_correlation: number | null
  most_correlated?: CorrelationPair[]
  least_correlated?: CorrelationPair[]
  days?: number
}

export interface RegimeClassification {
  regime: 'RISK_ON' | 'RISK_OFF' | 'ROTACION' | 'NEUTRAL' | 'UNKNOWN'
  label: string
  correlation_state: string
}

export interface MarketRegime {
  status: 'OK' | 'INSUFICIENTE'
  correlations?: Correlations
  btc_trend_pct?: number
  breadth_pct?: number
  regime?: RegimeClassification
  basket?: string[]
  note?: string
}

export interface LeadLagPair {
  leader: string
  follower: string
  lag: number
  corr: number
}

export interface LeadLagLeader {
  symbol: string
  leads: number
}

export interface LeadLag {
  status: 'OK' | 'INSUFICIENTE'
  symbols?: string[]
  pairs?: LeadLagPair[]
  leaders?: LeadLagLeader[]
  max_lag?: number
  note?: string
}

export const regimeService = {
  get: async (): Promise<MarketRegime> => {
    const { data } = await apiClient.get<MarketRegime>('/market/regime/')
    return data
  },

  leadLag: async (): Promise<LeadLag> => {
    const { data } = await apiClient.get<LeadLag>('/market/lead-lag/')
    return data
  },
}
