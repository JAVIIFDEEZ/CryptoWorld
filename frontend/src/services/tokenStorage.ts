/**
 * services/tokenStorage.ts — Único propietario de la sesión en el cliente.
 *
 * Las claves de `localStorage` estaban declaradas por separado en
 * `api.ts`, `useAuth.ts` y `authService.ts`. Tres copias de la misma
 * constante es una invitación a que una se quede atrás: basta con que un
 * flujo escriba el token nuevo y otro siga leyendo el viejo para dejar
 * al usuario en un estado a medias entre sesión iniciada y cerrada.
 *
 * Nota de seguridad — por qué `localStorage`:
 * guardar el JWT aquí lo expone a cualquier XSS que llegue a ejecutarse
 * en la página. La alternativa robusta son cookies `HttpOnly`, que el
 * JavaScript no puede leer. Mientras el esquema siga siendo Bearer, las
 * mitigaciones que sostienen esta decisión son:
 *   - CSP estricta servida por nginx (sin `unsafe-inline` en scripts).
 *   - Access tokens de vida corta (15 min) con rotación de refresh.
 *   - Revocación global por `credentials_changed_at` en el servidor.
 * Está anotado como riesgo aceptado en `SECURITY.md`.
 */

const ACCESS_TOKEN_KEY = 'cw_access_token'
const REFRESH_TOKEN_KEY = 'cw_refresh_token'
const USER_KEY = 'cw_user'

export const tokenStorage = {
  getAccessToken(): string | null {
    return localStorage.getItem(ACCESS_TOKEN_KEY)
  },

  getRefreshToken(): string | null {
    return localStorage.getItem(REFRESH_TOKEN_KEY)
  },

  setAccessToken(token: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, token)
  },

  /** Persistir el par completo tras un login o una rotación de sesión. */
  setTokens(accessToken: string, refreshToken: string): void {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  },

  getUser<T>(): T | null {
    const raw = localStorage.getItem(USER_KEY)
    if (!raw) return null
    try {
      return JSON.parse(raw) as T
    } catch {
      // Contenido corrupto: se descarta en vez de romper el arranque.
      localStorage.removeItem(USER_KEY)
      return null
    }
  },

  setUser(user: unknown): void {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  },

  /** Borrar toda la sesión local. */
  clear(): void {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  },
}
