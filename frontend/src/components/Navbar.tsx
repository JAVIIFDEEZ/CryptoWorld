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
import { useState, useRef, useEffect } from 'react'

function Navbar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  // Cerrar menú si se hace click fuera
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

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
          {user?.isAdmin && (
            <Link
              to="/admin"
              className="text-fuchsia-400 hover:text-fuchsia-300 text-sm font-medium transition-colors flex items-center gap-1"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              Admin
            </Link>
          )}
        </div>

        {/* Usuario + menú de ajustes */}
        <div className="flex items-center gap-4 relative" ref={menuRef}>
          {user && (
            <span className="text-slate-400 text-sm hidden sm:block">
              {user.username}
            </span>
          )}
          
          <button
            onClick={() => setIsMenuOpen(!isMenuOpen)}
            className="p-2 text-slate-300 hover:text-white hover:bg-slate-700 rounded-full transition-colors flex items-center justify-center"
            title="Ajustes de cuenta"
          >
            {/* Ícono de engranaje SVG */}
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>

          {/* Menú desplegable */}
          {isMenuOpen && (
            <div className="absolute right-0 top-12 w-48 bg-slate-800 border border-slate-700 rounded-md shadow-lg py-1 z-50">
              <Link
                to="/settings"
                onClick={() => setIsMenuOpen(false)}
                className="block px-4 py-2 text-sm text-slate-300 hover:bg-slate-700 hover:text-white"
              >
                Ajustes
              </Link>
              <button
                onClick={() => {
                  setIsMenuOpen(false);
                  handleLogout();
                }}
                className="block w-full text-left px-4 py-2 text-sm text-red-400 hover:bg-slate-700 hover:text-red-300"
              >
                Cerrar sesión
              </button>
            </div>
          )}
        </div>
      </nav>
    </header>
  )
}

export default Navbar
