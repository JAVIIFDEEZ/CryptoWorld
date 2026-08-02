/**
 * useAuth.ts — Hook de autenticación + Context Provider.
 *
 * Centraliza todo el estado de autenticación en un único lugar.
 * Cualquier componente puede acceder a { user, token, login, logout }
 * mediante el hook useAuth() sin necesidad de prop drilling.
 *
 * El token JWT se persiste en localStorage para sobrevivir recargas.
 * En producción considerar httpOnly cookies por razones de seguridad.
 *
 * Patrón: React Context + Custom Hook (alternativa ligera a Redux).
 */

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  type ReactNode,
} from 'react'
import { authService } from '@/services/authService'
import { tokenStorage } from '@/services/tokenStorage'

// ── Tipos ──────────────────────────────────────────────────────────

/** Datos del usuario autenticado disponibles en toda la app */
export interface AuthUser {
  id: number
  email: string
  username: string
  isAdmin: boolean
}

interface AuthContextType {
  user: AuthUser | null
  token: string | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string) => Promise<{ requires2FA: boolean; preAuthToken?: string }>
  verify2FALogin: (
    preAuthToken: string,
    factor: { totpCode?: string; recoveryCode?: string },
  ) => Promise<void>
  /** Actualiza datos del usuario en memoria y localStorage (ej. tras editar el perfil). */
  updateUser: (partial: Partial<AuthUser>) => void
  logout: () => void
}

// ── Context ────────────────────────────────────────────────────────

// Valor inicial undefined indica "fuera del Provider" (error en desarrollo)
const AuthContext = createContext<AuthContextType | undefined>(undefined)

// ── Provider ───────────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(() => {
    // Restaurar usuario desde el almacenamiento local al iniciar
    return tokenStorage.getUser<AuthUser>()
  })

  const [token, setToken] = useState<string | null>(() => {
    return tokenStorage.getAccessToken()
  })

  const [isLoading, setIsLoading] = useState(false)

  function applyAuthenticatedSession(accessToken: string, refreshToken: string, authUser: AuthUser) {
    setToken(accessToken)
    setUser(authUser)
    // El refresh token permite renovar la sesión sin volver a pedir credenciales
    tokenStorage.setTokens(accessToken, refreshToken)
    tokenStorage.setUser(authUser)
  }

  /**
   * login — Autenticar con la API y almacenar los tokens.
   *
   * Delega la llamada HTTP en authService para mantener
   * este hook libre de lógica de transporte.
   */
  const login = useCallback(async (email: string, password: string) => {
    setIsLoading(true)
    try {
      const response = await authService.login({ email, password })

      // Paso 1 del flujo 2FA: credenciales correctas, pendiente TOTP.
      if (response.requires_2fa) {
        return { requires2FA: true, preAuthToken: response.pre_auth_token }
      }

      const authUser: AuthUser = {
        id: response.user_id,
        email: response.email,
        username: response.username,
        isAdmin: !!response.is_admin,
      }
      applyAuthenticatedSession(response.access_token, response.refresh_token, authUser)
      return { requires2FA: false }
    } finally {
      setIsLoading(false)
    }
  }, [])

  const verify2FALogin = useCallback(async (
    preAuthToken: string,
    factor: { totpCode?: string; recoveryCode?: string },
  ) => {
    setIsLoading(true)
    try {
      const response = await authService.verify2FALogin(preAuthToken, {
        totp_code: factor.totpCode,
        recovery_code: factor.recoveryCode,
      })
      const authUser: AuthUser = {
        id: response.user_id,
        email: response.email,
        username: response.username,
        isAdmin: !!response.is_admin,
      }
      applyAuthenticatedSession(response.access_token, response.refresh_token, authUser)
    } finally {
      setIsLoading(false)
    }
  }, [])

  /**
   * updateUser — Sincronizar el usuario en memoria tras editar el perfil
   * (username, email...) sin obligar a recargar ni a re-loguear.
   */
  const updateUser = useCallback((partial: Partial<AuthUser>) => {
    setUser((prev) => {
      if (!prev) return prev
      const next = { ...prev, ...partial }
      tokenStorage.setUser(next)
      return next
    })
  }, [])

  /**
   * logout — Invalidar el refresh token en el backend (blacklist) y
   * limpiar el estado local. La llamada al backend es fire-and-forget:
   * el logout local no debe bloquearse si la red falla.
   */
  const logout = useCallback(() => {
    const refreshToken = tokenStorage.getRefreshToken()
    if (refreshToken) {
      authService.logout(refreshToken).catch(() => {
        // El token expirará solo; el logout local ya se ha completado
      })
    }
    setUser(null)
    setToken(null)
    tokenStorage.clear()
  }, [])

  return React.createElement(
    AuthContext.Provider,
    {
      value: {
        user,
        token,
        isAuthenticated: !!token && !!user,
        isLoading,
        login,
        verify2FALogin,
        updateUser,
        logout,
      },
    },
    children,
  )
}

// ── Hook ───────────────────────────────────────────────────────────

/**
 * useAuth — Acceder al contexto de autenticación desde cualquier componente.
 *
 * Lanza un error claro si se usa fuera del AuthProvider.
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth debe usarse dentro de un AuthProvider')
  }
  return context
}
