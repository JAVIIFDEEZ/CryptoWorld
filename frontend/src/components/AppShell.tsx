/**
 * components/AppShell.tsx — Layout principal autenticado.
 *
 * Inspirado en el prototipo de Figma: sidebar + cabecera + contenido.
 * Se mantiene simple para integrarlo por fases sin añadir dependencias extra.
 */

import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

type NavItem = {
  path: string
  label: string
  shortLabel: string
  exact?: boolean
}

const navItems: NavItem[] = [
  { path: '/dashboard', label: 'Dashboard', shortLabel: 'Dash', exact: true },
  { path: '/market', label: 'Mercado', shortLabel: 'Market' },
  { path: '/analysis', label: 'Analisis Tecnico', shortLabel: 'TA' },
  { path: '/blockchain', label: 'Blockchain', shortLabel: 'Chain' },
  { path: '/portfolio', label: 'Portfolio', shortLabel: 'Port' },
  { path: '/news', label: 'Noticias', shortLabel: 'News' },
  { path: '/alerts', label: 'Alertas', shortLabel: 'Alerts' },
  { path: '/security/2fa', label: 'Seguridad 2FA', shortLabel: '2FA' },
]

function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen lg:h-screen lg:overflow-hidden bg-slate-900 text-slate-100">
      {mobileMenuOpen && (
        <button
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-label="Cerrar menu"
        />
      )}

      <div className="flex h-full">
        <aside
          className={`
            fixed lg:relative z-40 inset-y-0 left-0 w-64
            transform transition-transform duration-200
            ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
            bg-gradient-to-b from-[#0b1120] to-[#0f1f3d] border-r border-white/10
          `}
        >
          <div className="h-16 px-4 flex items-center border-b border-white/10">
            <button
              className="text-lg font-bold tracking-tight"
              onClick={() => navigate('/dashboard')}
            >
              <span className="text-blue-400">Crypto</span>World
            </button>
          </div>

          <nav className="p-3 space-y-1">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setMobileMenuOpen(false)}
                end={item.exact}
                className={({ isActive }) =>
                  [
                    'block rounded-lg px-3 py-2 text-sm transition-colors',
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:bg-white/10 hover:text-white',
                  ].join(' ')
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto p-3 border-t border-white/10">
            <p className="text-xs text-slate-400 truncate mb-2">{user?.username ?? user?.email}</p>
            <button
              onClick={handleLogout}
              className="w-full rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-100 text-sm py-2 transition-colors"
            >
              Cerrar sesion
            </button>
          </div>
        </aside>

        <div className="flex-1 min-w-0 flex flex-col">
          <header className="h-16 border-b border-slate-700/70 bg-slate-800/80 backdrop-blur px-4 flex items-center gap-3">
            <button
              className="lg:hidden rounded-md px-2 py-1 bg-slate-700 text-slate-100"
              onClick={() => setMobileMenuOpen(true)}
            >
              Menu
            </button>
            <p className="text-sm text-slate-300">Panel de analisis</p>
          </header>

          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            <Outlet />
          </main>

          <nav className="lg:hidden border-t border-slate-700 bg-slate-800 px-1 py-2 flex justify-between">
            {navItems.slice(0, 5).map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.exact}
                className={({ isActive }) =>
                  [
                    'text-[11px] px-2 py-1 rounded-md',
                    isActive ? 'text-blue-400' : 'text-slate-400',
                  ].join(' ')
                }
              >
                {item.shortLabel}
              </NavLink>
            ))}
          </nav>
        </div>
      </div>
    </div>
  )
}

export default AppShell
