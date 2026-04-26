/**
 * services/alertsService.ts — API calls para el módulo Alertas de Precio.
 *
 * Endpoints:
 *   GET  /api/alerts/              → Listar alertas del usuario
 *   POST /api/alerts/              → Crear nueva alerta
 *   DELETE /api/alerts/:id/        → Eliminar alerta
 *   PATCH  /api/alerts/:id/toggle/ → Activar/desactivar alerta
 */

import apiClient from './api'

export interface PriceAlert {
  id: number
  asset_symbol: string
  asset_name: string
  condition: 'ABOVE' | 'BELOW'
  threshold_price: number
  current_price: number | null
  is_active: boolean
  is_triggered: boolean
  triggered_at: string | null
  notes: string
  created_at: string
}

export interface CreateAlertPayload {
  asset_symbol: string
  condition: 'ABOVE' | 'BELOW'
  threshold_price: number
  notes?: string
}

export const alertsService = {
  /** Listar todas las alertas (active_only=true para solo activas) */
  getAlerts: async (activeOnly = false): Promise<PriceAlert[]> => {
    const params = activeOnly ? '?active_only=true' : ''
    const { data } = await apiClient.get(`/alerts/${params}`)
    return data
  },

  /** Crear una nueva alerta de precio */
  createAlert: async (payload: CreateAlertPayload): Promise<PriceAlert> => {
    const { data } = await apiClient.post('/alerts/', payload)
    return data
  },

  /** Eliminar una alerta */
  deleteAlert: async (alertId: number): Promise<void> => {
    await apiClient.delete(`/alerts/${alertId}/`)
  },

  /** Activar o desactivar una alerta */
  toggleAlert: async (alertId: number): Promise<PriceAlert> => {
    const { data } = await apiClient.patch(`/alerts/${alertId}/toggle/`)
    return data
  },
}
