/**
 * services/notificationsService.ts — Centro de notificaciones in-app.
 *
 * Feed unificado (señales de estrategia, alertas de ballenas, predicciones
 * resueltas, alertas de precio, kill-switch de ejecución real) agregado en el
 * backend, con contador de no leídas resuelto por un sello de "visto" por usuario.
 */

import apiClient from './api'

export type NotificationKind = 'signal' | 'whale' | 'prediction' | 'price' | 'pressure' | 'live'

export interface NotificationItem {
  id: string
  kind: NotificationKind
  title: string
  body: string
  link: string
  unread: boolean
  created_at: string
}

export interface NotificationsFeed {
  unread: number
  count: number
  items: NotificationItem[]
}

export const notificationsService = {
  /** Feed unificado de notificaciones del usuario + nº de no leídas. */
  async getNotifications(limit = 30): Promise<NotificationsFeed> {
    const { data } = await apiClient.get<NotificationsFeed>('/notifications/', { params: { limit } })
    return data
  },

  /** Marca todas las notificaciones como leídas. */
  async markSeen(): Promise<{ unread: number; seen_at: string }> {
    const { data } = await apiClient.post('/notifications/seen/')
    return data
  },
}
