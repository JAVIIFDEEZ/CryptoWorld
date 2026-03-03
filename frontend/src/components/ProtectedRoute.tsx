/**
 * components/ProtectedRoute.tsx — Guard de rutas autenticadas.
 *
 * Responsabilidad: comprobar si el usuario está autenticado antes
 * de renderizar la ruta hija. Si no lo está, redirige a /login.
 *
 * Usa el patrón de "layout route" de React Router v6:
 * envuelve rutas hijas con <Outlet /> en lugar de recibir un
 * componente como prop. Esto permite anidar múltiples rutas
 * protegidas de forma limpia.
 *
 * El parámetro `replace` en Navigate evita que /login quede en
 * el historial del navegador cuando se redirige automáticamente.
 */

import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  // Mostrar pantalla de carga mientras se restaura la sesión de localStorage
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="text-slate-400 text-sm animate-pulse">Cargando...</div>
      </div>
    )
  }

  if (!isAuthenticated) {
    /*
     * Guardar la ruta intentada en `state` para redirigir allí
     * después del login (UX mejorada).
     */
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // Usuario autenticado: renderizar la ruta hija
  return <Outlet />
}

export default ProtectedRoute
