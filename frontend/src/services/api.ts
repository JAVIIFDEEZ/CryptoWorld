/**
 * services/api.ts — Instancia centralizada de Axios.
 *
 * Responsabilidad: configurar el cliente HTTP base con:
 *   - URL base apuntando a la API Django
 *   - Interceptor de petición: inyecta el token JWT en cada request
 *   - Interceptor de respuesta: maneja errores 401 globalmente
 *
 * NINGÚN otro servicio crea su propia instancia de axios.
 * Todos importan esta instancia para garantizar consistencia.
 *
 * La URL base se lee de la variable de entorno VITE_API_URL,
 * con fallback al proxy de Vite en desarrollo.
 */

import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

const TOKEN_KEY = 'cw_access_token'
const REFRESH_KEY = 'cw_refresh_token'
const USER_KEY = 'cw_user'

/**
 * Instancia de Axios configurada para el backend CryptoWorld.
 * Exportada para uso en todos los servicios de la aplicación.
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api',
  timeout: 10_000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
})

/**
 * Interceptor de petición:
 * Añade el token JWT Bearer al header Authorization en cada petición.
 * Si no hay token (usuario no autenticado), la petición sale sin él
 * y el backend devolverá 401 si el endpoint lo requiere.
 */
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem(TOKEN_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

/**
 * Renovación del access token con el refresh token almacenado.
 *
 * Se usa axios "crudo" (no apiClient) para no pasar por los interceptores
 * y evitar bucles. SimpleJWT rota el refresh token (ROTATE_REFRESH_TOKENS),
 * así que si la respuesta incluye uno nuevo también se persiste.
 */
let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = localStorage.getItem(REFRESH_KEY)
  if (!refreshToken) return null
  try {
    const { data } = await axios.post<{ access: string; refresh?: string }>(
      `${apiClient.defaults.baseURL}/auth/token/refresh/`,
      { refresh: refreshToken },
      { timeout: 10_000 },
    )
    localStorage.setItem(TOKEN_KEY, data.access)
    if (data.refresh) {
      localStorage.setItem(REFRESH_KEY, data.refresh)
    }
    return data.access
  } catch {
    return null
  }
}

function clearSessionAndRedirect(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
  localStorage.removeItem(USER_KEY)
  if (window.location.pathname !== '/login') {
    window.location.href = '/login'
  }
}

/**
 * Interceptor de respuesta:
 * Ante un 401, intenta renovar el access token con el refresh token y
 * reintenta la petición original una vez (single-flight: si hay varias
 * peticiones en vuelo comparten la misma renovación). Solo si el refresh
 * también falla se considera la sesión caducada y se redirige al login.
 */
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
    const status = error.response?.status
    // Los propios endpoints de login/refresh no deben disparar renovaciones
    const isAuthEndpoint =
      !!original?.url && (original.url.includes('/auth/login') || original.url.includes('/auth/token/refresh'))

    if (status === 401 && original && !original._retry && !isAuthEndpoint) {
      original._retry = true

      refreshPromise = refreshPromise ?? refreshAccessToken()
      const newToken = await refreshPromise
      refreshPromise = null

      if (newToken) {
        original.headers.Authorization = `Bearer ${newToken}`
        return apiClient(original)
      }
      clearSessionAndRedirect()
    }
    return Promise.reject(error)
  },
)

export default apiClient
