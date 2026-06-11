/**
 * services/adminService.ts — Servicio del panel de administración.
 *
 * Encapsula todas las llamadas HTTP a /api/admin/*. Los componentes
 * del panel no usan apiClient directamente: delegan aquí, igual que
 * el resto de páginas con sus servicios.
 */

import apiClient from './api'

// ── Tipos de las respuestas del backend ────────────────────────────

export interface AdminUser {
  id: number
  email: string
  username: string
  is_active: boolean
  is_email_verified: boolean
  is_2fa_enabled: boolean
  is_admin: boolean
  date_joined: string
  last_login: string | null
}

export interface CreateAdminPayload {
  email: string
  username: string
  password: string
}

export interface UpdateUserPayload {
  is_active?: boolean
  is_admin?: boolean
  is_email_verified?: boolean
}

export interface MarketSyncResult {
  message: string
  assets_created: number
  assets_updated: number
  snapshots_created: number
  errors: string[]
}

export interface SystemHealth {
  status: 'ok' | 'degraded'
  version: string
  service: string
  components: {
    database: 'ok' | 'error'
    cache: 'ok' | 'error'
    celery_broker: 'ok' | 'error'
    email_backend: 'sendgrid' | 'smtp' | 'console'
  }
}

// ── Servicio ───────────────────────────────────────────────────────

export const adminService = {
  /**
   * Listar usuarios del sistema, con búsqueda opcional por email/username.
   * GET /api/admin/users/?search=
   */
  async listUsers(search = ''): Promise<AdminUser[]> {
    const { data } = await apiClient.get<AdminUser[]>('/admin/users/', {
      params: search ? { search } : undefined,
    })
    return data
  },

  /**
   * Crear un nuevo administrador.
   * POST /api/admin/users/
   */
  async createAdmin(payload: CreateAdminPayload): Promise<AdminUser> {
    const { data } = await apiClient.post<{ message: string; user: AdminUser }>(
      '/admin/users/',
      payload,
    )
    return data.user
  },

  /**
   * Actualizar estado de un usuario (bloquear, conceder admin, verificar).
   * PATCH /api/admin/users/<id>/
   */
  async updateUser(userId: number, payload: UpdateUserPayload): Promise<AdminUser> {
    const { data } = await apiClient.patch<{ message: string; user: AdminUser }>(
      `/admin/users/${userId}/`,
      payload,
    )
    return data.user
  },

  /**
   * Reenviar el email de verificación a un usuario no verificado.
   * POST /api/admin/users/<id>/resend-verification/
   */
  async resendVerification(userId: number): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>(
      `/admin/users/${userId}/resend-verification/`,
    )
    return data
  },

  /**
   * Forzar sincronización del catálogo de mercado desde CoinGecko.
   * POST /api/admin/market/sync/
   */
  async syncMarket(perPage: number): Promise<MarketSyncResult> {
    const { data } = await apiClient.post<MarketSyncResult>('/admin/market/sync/', {
      per_page: perPage,
    })
    return data
  },

  /**
   * Estado del sistema: BD, cache, broker Celery y modo del email.
   * GET /api/health/ (público, pero solo se muestra en el panel admin)
   */
  async getSystemHealth(): Promise<SystemHealth> {
    const { data } = await apiClient.get<SystemHealth>('/health/')
    return data
  },
}
