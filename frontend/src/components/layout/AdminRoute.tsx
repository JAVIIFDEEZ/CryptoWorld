import { Navigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

export function AdminRoute({ children }: { children: JSX.Element }) {
  const { user, isAuthenticated } = useAuth()

  // Si no estÃ¡ autenticado o no es admin, redirigir
  if (!isAuthenticated || !user?.isAdmin) {
    return <Navigate to="/dashboard" replace />
  }

  return children
}
