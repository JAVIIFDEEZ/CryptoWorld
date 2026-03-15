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

export interface LoginRequires2FAResponse {
  requires_2fa: true
  pre_auth_token: string
}

export interface LoginSuccessResponse extends AuthResponse {
  requires_2fa: false
}

export type LoginResponse = LoginSuccessResponse | LoginRequires2FAResponse

export interface RegisterResponse {
  id: number
  email: string
  username: string
}

export interface UserMeResponse {
  id: number
  email: string
  username: string
  is_active: boolean
  is_email_verified: boolean
  is_2fa_enabled: boolean
  date_joined: string
}

export interface Setup2FAResponse {
  totp_secret: string
  qr_code_uri: string
  qr_code_base64: string
  message: string
}

// ── Servicio ───────────────────────────────────────────────────────

export const authService = {
  /**
   * Autenticar usuario y obtener tokens JWT.
   * POST /api/auth/login
   */
  async login(payload: LoginPayload): Promise<LoginResponse> {
    const { data } = await apiClient.post<LoginResponse>('/auth/login/', payload)
    return data
  },

  /**
   * Completar login cuando el backend pide segundo factor.
   * POST /api/auth/2fa/login/
   */
  async verify2FALogin(pre_auth_token: string, totp_code: string): Promise<AuthResponse> {
    const { data } = await apiClient.post<AuthResponse>('/auth/2fa/login/', {
      pre_auth_token,
      totp_code,
    })
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

  /**
   * Confirmar email desde el token recibido por correo.
   * GET /api/auth/verify-email/?token=...
   */
  async verifyEmail(token: string): Promise<{ message: string }> {
    const { data } = await apiClient.get<{ message: string }>('/auth/verify-email/', {
      params: { token },
    })
    return data
  },

  /**
   * Reenviar email de verificación.
   * POST /api/auth/verify-email/resend/
   */
  async resendVerificationEmail(email: string): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>('/auth/verify-email/resend/', { email })
    return data
  },

  /**
   * Obtener estado actual del usuario autenticado.
   * GET /api/auth/me/
   */
  async me(): Promise<UserMeResponse> {
    const { data } = await apiClient.get<UserMeResponse>('/auth/me/')
    return data
  },

  /**
   * Iniciar setup de 2FA (devuelve QR y secreto).
   * POST /api/auth/2fa/setup/
   */
  async setup2FA(): Promise<Setup2FAResponse> {
    const { data } = await apiClient.post<Setup2FAResponse>('/auth/2fa/setup/')
    return data
  },

  /**
   * Confirmar y activar 2FA con un código TOTP válido.
   * POST /api/auth/2fa/enable/
   */
  async enable2FA(totp_code: string): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>('/auth/2fa/enable/', { totp_code })
    return data
  },

  /**
   * Desactivar 2FA con código TOTP vigente.
   * POST /api/auth/2fa/disable/
   */
  async disable2FA(totp_code: string): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>('/auth/2fa/disable/', { totp_code })
    return data
  },
}
