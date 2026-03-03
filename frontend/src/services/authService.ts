/**
 * services/authService.ts — Servicio de autenticación.
 *
 * Encapsula todas las llamadas HTTP relacionadas con auth:
 *   - login
 *   - register
 *
 * Principio: los componentes y hooks no hacen llamadas HTTP directas.
 * Delegan en servicios, que a su vez usan la instancia de apiClient.
 *
 * Esto facilita:
 *   - Tests (mockear el servicio, no axios)
 *   - Cambiar endpoints sin tocar componentes
 *   - Añadir lógica compartida (retry, logging, etc.)
 */

import apiClient from './api'

// ── Tipos de las respuestas del backend ────────────────────────────

export interface LoginPayload {
  email: string
  password: string
}

export interface RegisterPayload {
  email: string
  username: string
  password: string
  password_confirm: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  user_id: number
  email: string
  username: string
}

export interface RegisterResponse {
  id: number
  email: string
  username: string
}

// ── Servicio ───────────────────────────────────────────────────────

export const authService = {
  /**
   * Autenticar usuario y obtener tokens JWT.
   * POST /api/auth/login
   */
  async login(payload: LoginPayload): Promise<AuthResponse> {
    const { data } = await apiClient.post<AuthResponse>('/auth/login/', payload)
    return data
  },

  /**
   * Registrar nuevo usuario.
   * POST /api/auth/register
   */
  async register(payload: RegisterPayload): Promise<RegisterResponse> {
    const { data } = await apiClient.post<RegisterResponse>('/auth/register/', payload)
    return data
  },

  /**
   * Renovar el access_token usando el refresh_token.
   * POST /api/auth/token/refresh
   */
  async refreshToken(refreshToken: string): Promise<{ access: string }> {
    const { data } = await apiClient.post<{ access: string }>('/auth/token/refresh/', {
      refresh: refreshToken,
    })
    return data
  },
}
