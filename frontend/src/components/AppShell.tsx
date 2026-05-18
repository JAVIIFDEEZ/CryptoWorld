/**
 * components/AppShell.tsx — Layout principal autenticado.
 */

import { useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import TickerBar from '@/components/TickerBar'

// -- Iconos SVG inline --

const IconDashboard = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
  </svg>
)
const IconMarket = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
  </svg>
)
const IconAnalysis = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
  </svg>
)
const IconBlockchain = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
  </svg>
)
const IconPortfolio = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M21 13.255A23.931 23.931 0 0112 15c-3.183 0-6.22-.62-9-1.745M16 6V4a2 2 0 00-2-2h-4a2 2 0 00-2 2v2m4 6h.01M5 20h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
  </svg>
)
const IconAlerts = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
  </svg>
)
const IconNews = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
  </svg>
)

type NavSection = {
  label: string
  items: { path: string; label: string; shortLabel: string; icon: JSX.Element; exact?: boolean }[]
}

const navSections: NavSection[] = [
  {
    label: 'PRINCIPAL',
    items: [
      { path: '/dashboard', label: 'Dashboard', shortLabel: 'Dash', icon: <IconDashboard />, exact: true },
    ],
  },
  {
    label: 'MERCADOS',
    items: [
      { path: '/market', label: 'Mercado', shortLabel: 'Market', icon: <IconMarket /> },
      { path: '/analysis', label: 'Análisis Técnico', shortLabel: 'TA', icon: <IconAnalysis /> },
      { path: '/blockchain', label: 'Blockchain', shortLabel: 'Chain', icon: <IconBlockchain /> },
    ],
  },
  {
    label: 'GESTIÓN',
    items: [
      { path: '/portfolio', label: 'Portfolio', shortLabel: 'Port', icon: <IconPortfolio /> },
      { path: '/alerts', label: 'Alertas', shortLabel: 'Alerts', icon: <IconAlerts /> },
    ],
  },
  {
    label: 'INFORMACIÓN',
    items: [
      { path: '/news', label: 'Noticias', shortLabel: 'News', icon: <IconNews /> },
    ],
  },
]

// Flat list for mobile bottom bar
const navItemsFlat = navSections.flatMap(s => s.items)

function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="min-h-screen lg:h-screen lg:overflow-hidden bg-slate-900 text-slate-100 flex flex-col">
      {/* Ticker bar — cotizaciones en tiempo real */}
      <TickerBar />

      {mobileMenuOpen && (
        <button
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-label="Cerrar menu"
        />
      )}

      <div className="flex flex-1 min-h-0">
        <aside
          className={`
            fixed lg:relative z-40 inset-y-0 left-0 w-64 flex flex-col
            transform transition-transform duration-200
            ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
            bg-gradient-to-b from-[#0b1120] to-[#0f1f3d] border-r border-white/10
          `}
        >
          <div className="h-16 px-5 flex items-center border-b border-white/10">
            <button
              className="text-lg font-bold tracking-tight"
              onClick={() => navigate('/dashboard')}
            >
              <span className="text-blue-400">Crypto</span>World
            </button>
          </div>

          {/* Navegación por secciones */}
          <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-5">
            {navSections.map(section => (
              <div key={section.label}>
                <p className="px-3 mb-1.5 text-[10px] font-semibold tracking-widest text-slate-500 uppercase select-none">
                  {section.label}
                </p>
                <div className="space-y-0.5">
                  {section.items.map(item => (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      onClick={() => setMobileMenuOpen(false)}
                      end={item.exact}
                      className={({ isActive }) =>
                        [
                          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                          isActive
                            ? 'bg-blue-600 text-white'
                            : 'text-slate-400 hover:bg-white/8 hover:text-slate-100',
                        ].join(' ')
                      }
                    >
                      {item.icon}
                      <span>{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            ))}

            {/* Enlace Admin — solo visible para administradores */}
            {user?.isAdmin && (
              <div>
                <p className="px-3 mb-1.5 text-[10px] font-semibold tracking-widest text-slate-500 uppercase select-none">
                  SISTEMA
                </p>
                <NavLink
                  to="/admin"
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    [
                      'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors border border-blue-500/20',
                      isActive
                        ? 'bg-blue-600 text-white'
                        : 'text-blue-400 hover:bg-blue-500/10 hover:text-blue-300',
                    ].join(' ')
                  }
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                  </svg>
                  <span>Panel Admin</span>
                </NavLink>
              </div>
            )}
          </nav>

          <div className="mt-auto p-3 border-t border-white/10 flex flex-col gap-2">
            <p className="text-xs text-slate-400 truncate px-1">{user?.username ?? user?.email}</p>
            
            <div className="flex gap-2">
              <button
                onClick={() => navigate('/settings')}
                title="Ajustes de cuenta"
                className="flex items-center justify-center rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white p-2 transition-colors border border-slate-700"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </button>
              
              <button
                onClick={handleLogout}
                className="flex-1 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-100 text-sm py-2 transition-colors"
              >
                Cerrar sesion
              </button>
            </div>
          </div>
        </aside>

        <div className="flex-1 min-w-0 flex flex-col">
          {/* Botón menú móvil */}
          <div className="lg:hidden h-12 border-b border-slate-700/70 bg-slate-800/80 backdrop-blur px-4 flex items-center">
            <button
              className="rounded-md px-2 py-1 bg-slate-700 text-slate-100 text-sm"
              onClick={() => setMobileMenuOpen(true)}
            >
              Menú
            </button>
          </div>

          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            <Outlet />
          </main>

          <nav className="lg:hidden border-t border-slate-700 bg-slate-800 px-1 py-2 flex justify-between">
            {navItemsFlat.slice(0, 5).map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.exact}
                className={({ isActive }) =>
                  [
                    'flex flex-col items-center gap-0.5 px-2 py-1 rounded-md text-[10px]',
                    isActive ? 'text-blue-400' : 'text-slate-400',
                  ].join(' ')
                }
              >
                {item.icon}
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
