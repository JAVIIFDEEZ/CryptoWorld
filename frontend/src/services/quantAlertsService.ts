/**
 * services/quantAlertsService.ts — API del motor de alertas cuantitativas.
 *
 * A diferencia de las alertas de precio, evalúan cualquier métrica del sistema
 * (técnica, confluencia 360°, on-chain, riesgo de cartera) con disparo por
 * flanco y cooldown.
 *
 * Endpoints:
 *   GET/POST   /api/quant-alerts/            → listar (?catalog=1) / crear
 *   PATCH/DEL  /api/quant-alerts/:id/        → actualizar-toggle / borrar
 *   GET        /api/quant-alerts/firings/    → últimos disparos
 */

import apiClient from './api'

export type QuantOperator = 'gt' | 'lt' | 'cross_up' | 'cross_down'
export type MetricScope = 'asset' | 'portfolio'

export interface QuantMetric {
  key: string
  label: string
  unit: string
  category: string
  scope: MetricScope
  hint: string
}

export interface QuantAlert {
  id: number
  asset_symbol: string | null
  asset_name: string | null
  metric: string
  metric_label: string
  metric_unit: string
  scope: MetricScope
  timeframe: string
  operator: QuantOperator
  threshold: number
  cooldown_minutes: number
  is_active: boolean
  last_value: number | null
  last_fired_at: string | null
  note: string
  created_at: string
}

export interface QuantFiring {
  id: number
  alert_id: number
  metric: string
  metric_label: string
  asset_symbol: string | null
  value: number
  threshold: number
  operator: QuantOperator
  message: string
  seen: boolean
  fired_at: string
}

export interface CreateQuantAlertPayload {
  metric: string
  operator: QuantOperator
  threshold: number
  asset_symbol?: string
  timeframe?: string
  cooldown_minutes?: number
  note?: string
}

export const OPERATOR_LABELS: Record<QuantOperator, string> = {
  gt: 'Mayor o igual que (≥)',
  lt: 'Menor que (<)',
  cross_up: 'Cruza al alza',
  cross_down: 'Cruza a la baja',
}

export const quantAlertsService = {
  /** Lista alertas; con catalog=true trae también el catálogo de métricas. */
  list: async (catalog = false): Promise<{ alerts: QuantAlert[]; metrics?: QuantMetric[] }> => {
    const { data } = await apiClient.get(`/quant-alerts/${catalog ? '?catalog=1' : ''}`)
    return data
  },

  create: async (payload: CreateQuantAlertPayload): Promise<QuantAlert> => {
    const { data } = await apiClient.post('/quant-alerts/', payload)
    return data
  },

  update: async (id: number, payload: Partial<CreateQuantAlertPayload> & { is_active?: boolean }): Promise<QuantAlert> => {
    const { data } = await apiClient.patch(`/quant-alerts/${id}/`, payload)
    return data
  },

  remove: async (id: number): Promise<void> => {
    await apiClient.delete(`/quant-alerts/${id}/`)
  },

  firings: async (limit = 30): Promise<QuantFiring[]> => {
    const { data } = await apiClient.get(`/quant-alerts/firings/?limit=${limit}`)
    return data.firings
  },
}
