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
  /** Puede operar el panel. */
  is_staff: boolean
  /** Además, puede conceder y revocar privilegios. */
  is_superuser: boolean
  /** `is_staff || is_superuser` — atajo para pintar el badge de admin. */
  is_admin: boolean
  date_joined: string
  last_login: string | null
}

/** Envolvente de paginación que devuelven los listados de la API. */
export interface Paginated<T> {
  count: number
  page: number
  page_size: number
  total_pages: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface CreateAdminPayload {
  email: string
  username: string
  password: string
  /**
   * Conceder también privilegios de superusuario. Por omisión la cuenta
   * se crea solo como staff: el privilegio máximo se pide explícitamente.
   */
  is_superuser?: boolean
}

export interface UpdateUserPayload {
  is_active?: boolean
  /** Requiere ser superusuario. */
  is_staff?: boolean
  /** Requiere ser superusuario. */
  is_superuser?: boolean
  is_email_verified?: boolean
}

/** Contadores globales de usuarios (GET /api/admin/users/stats/). */
export interface AdminUserStats {
  total: number
  verified: number
  admins: number
  superusers: number
  blocked: number
  with_2fa: number
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
  /** Solo presente para administradores. */
  components?: {
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
   * GET /api/admin/users/?search=&page=
   *
   * El endpoint va paginado: devuelve la envolvente completa para que el
   * panel pueda mostrar el total y navegar entre páginas en lugar de
   * asumir que la primera respuesta contiene todos los usuarios.
   */
  async listUsers(search = '', page = 1, pageSize = 50): Promise<Paginated<AdminUser>> {
    const { data } = await apiClient.get<Paginated<AdminUser>>('/admin/users/', {
      params: {
        ...(search ? { search } : {}),
        page,
        page_size: pageSize,
      },
    })
    return data
  },

  /**
   * Contadores globales de usuarios.
   * GET /api/admin/users/stats/
   *
   * Necesario desde que el listado va paginado: los totales ya no se
   * pueden derivar en el cliente a partir de la página cargada.
   */
  async getUserStats(): Promise<AdminUserStats> {
    const { data } = await apiClient.get<AdminUserStats>('/admin/users/stats/')
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
