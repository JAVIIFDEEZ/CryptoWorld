/**
 * components/Navbar.tsx — Barra de navegación principal.
 *
 * Responsabilidad: mostrar la navegación global de la app
 * y el botón de cierre de sesión para usuarios autenticados.
 *
 * Se renderiza solo dentro de rutas protegidas (ver routes.tsx),
 * por lo que podemos asumir que el usuario siempre está autenticado aquí.
 */

import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <header className="bg-slate-800 border-b border-slate-700 sticky top-0 z-50">
      <nav className="container mx-auto px-4 h-16 flex items-center justify-between">
        {/* Logo / Brand */}
        <Link
          to="/dashboard"
          className="text-xl font-bold text-white tracking-tight hover:text-blue-400 transition-colors"
        >
          <span className="text-blue-400">Crypto</span>World
        </Link>

        {/* Links de navegación */}
        <div className="flex items-center gap-6">
          <Link
            to="/dashboard"
            className="text-slate-300 hover:text-white text-sm transition-colors"
          >
            Dashboard
          </Link>
        </div>

        {/* Usuario + logout */}
        <div className="flex items-center gap-4">
          {user && (
            <span className="text-slate-400 text-sm hidden sm:block">
              {user.username}
            </span>
          )}
          <button
            onClick={handleLogout}
            className="bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm px-3 py-1.5 rounded-md transition-colors"
          >
            Cerrar sesión
          </button>
        </div>
      </nav>
    </header>
  )
}

export default Navbar
