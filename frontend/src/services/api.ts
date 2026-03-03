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
 * Interceptor de respuesta:
 * Centraliza el manejo de errores de autenticación.
 * Si el backend devuelve 401, limpia la sesión y recarga la app.
 *
 * Esto evita tener que manejar el 401 en cada servicio/componente.
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expirado o inválido — limpiar sesión
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem('cw_user')
      // Redirigir al login sin usar react-router (no tenemos acceso al navigate aquí)
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export default apiClient
