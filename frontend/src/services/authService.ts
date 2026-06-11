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
  is_admin?: boolean
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

export type PreferredCurrency = 'usd' | 'eur' | 'gbp'

export interface UserMeResponse {
  id: number
  email: string
  pending_email: string | null
  username: string
  is_active: boolean
  is_email_verified: boolean
  is_2fa_enabled: boolean
  is_admin: boolean
  date_joined: string
  preferred_currency: PreferredCurrency
  notify_price_alerts: boolean
  notify_market_digest: boolean
  recovery_codes_remaining: number
}

export interface UpdatePreferencesPayload {
  username?: string
  preferred_currency?: PreferredCurrency
  notify_price_alerts?: boolean
  notify_market_digest?: boolean
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
   *
   * El segundo factor puede ser el código TOTP de la app o un código
   * de recuperación de un solo uso (si se perdió el dispositivo).
   */
  async verify2FALogin(
    pre_auth_token: string,
    factor: { totp_code?: string; recovery_code?: string },
  ): Promise<AuthResponse> {
    const { data } = await apiClient.post<AuthResponse>('/auth/2fa/login/', {
      pre_auth_token,
      ...factor,
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
   * Cerrar sesión: añade el refresh token a la blacklist del backend.
   * POST /api/auth/logout/
   */
  async logout(refreshToken: string): Promise<void> {
    await apiClient.post('/auth/logout/', { refresh_token: refreshToken })
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
   * Cambiar contraseña del usuario autenticado.
   * POST /api/auth/change-password/
   *
   * El backend espera current_password + new_password + new_password_confirm
   * (ChangePasswordSerializer); enviar otros nombres provoca un 400.
   */
  async changePassword(current_password: string, new_password: string): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>('/auth/change-password/', {
      current_password,
      new_password,
      new_password_confirm: new_password,
    })
    return data
  },

  /**
   * Actualizar nombre de usuario y preferencias de cuenta.
   * PATCH /api/auth/me/
   */
  async updatePreferences(payload: UpdatePreferencesPayload): Promise<UserMeResponse> {
    const { data } = await apiClient.patch<UserMeResponse>('/auth/me/', payload)
    return data
  },

  /**
   * Solicitar el cambio de email: envía un enlace de confirmación a la
   * NUEVA dirección; el email de login no cambia hasta confirmar.
   * POST /api/auth/change-email/
   */
  async requestEmailChange(
    new_email: string,
    password: string,
  ): Promise<{ message: string; pending_email: string }> {
    const { data } = await apiClient.post<{ message: string; pending_email: string }>(
      '/auth/change-email/',
      { new_email, password },
    )
    return data
  },

  /**
   * Confirmar el cambio de email con el token recibido en el nuevo correo.
   * POST /api/auth/change-email/confirm/
   */
  async confirmEmailChange(token: string): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>(
      '/auth/change-email/confirm/',
      { token },
    )
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
   * Devuelve los códigos de recuperación: solo viajan en claro esta vez.
   */
  async enable2FA(totp_code: string): Promise<{ message: string; recovery_codes: string[] }> {
    const { data } = await apiClient.post<{ message: string; recovery_codes: string[] }>(
      '/auth/2fa/enable/',
      { totp_code },
    )
    return data
  },

  /**
   * Regenerar los códigos de recuperación (invalida los anteriores).
   * POST /api/auth/2fa/recovery-codes/
   */
  async regenerateRecoveryCodes(totp_code: string): Promise<{ message: string; recovery_codes: string[] }> {
    const { data } = await apiClient.post<{ message: string; recovery_codes: string[] }>(
      '/auth/2fa/recovery-codes/',
      { totp_code },
    )
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

  /**
   * Solicitar recuperación de contraseña.
   * POST /api/auth/password-reset/
   * Siempre responde 200 aunque el email no exista (anti-enumeración).
   */
  async requestPasswordReset(email: string): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>('/auth/password-reset/', { email })
    return data
  },

  /**
   * Confirmar nueva contraseña con el token del email.
   * POST /api/auth/password-reset/confirm/
   */
  async confirmPasswordReset(
    uid: string,
    token: string,
    new_password: string,
    new_password_confirm: string,
  ): Promise<{ message: string }> {
    const { data } = await apiClient.post<{ message: string }>('/auth/password-reset/confirm/', {
      uid,
      token,
      new_password,
      new_password_confirm,
    })
    return data
  },

  /**
   * Eliminar la cuenta de usuario de forma permanente.
   * DELETE /api/auth/delete-account/
   */
  async deleteAccount(password: string): Promise<void> {
    await apiClient.delete('/auth/delete-account/', { data: { password } })
  },
}
