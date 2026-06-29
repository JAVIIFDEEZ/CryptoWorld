/**
 * components/AppShell.tsx — Layout principal autenticado.
 */

import { useEffect, useRef, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth, type AuthUser } from '@/hooks/useAuth'
import TickerBar from '@/components/market/TickerBar'
import CommandPalette from '@/components/layout/CommandPalette'
import NotificationBell from '@/components/layout/NotificationBell'
import { useTheme, type Theme } from '@/hooks/useTheme'
import { useTranslation } from 'react-i18next'
import { SUPPORTED_LANGUAGES } from '@/i18n'

/** Iniciales del usuario para el avatar (ej. "Javier" → "JA"). */
function userInitials(user: AuthUser | null): string {
  const source = user?.username || user?.email || '?'
  return source.slice(0, 2).toUpperCase()
}

/**
 * Menú de cuenta del sidebar: avatar con iniciales que despliega
 * accesos a Ajustes, Seguridad 2FA, Panel Admin y Cerrar sesión.
 * Se cierra al hacer click fuera o al pulsar Escape.
 */
/**
 * Selector de idioma (ES/EN) dentro del menú de cuenta. Cambia la traducción en
 * caliente y persiste la elección (localStorage vía i18next-languagedetector).
 */
function LanguageSwitcher() {
  const { t, i18n } = useTranslation()
  return (
    <div className="px-2 py-1.5">
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 px-1">{t('nav.language')}</p>
      <div className="flex gap-0.5 bg-slate-900 rounded-lg p-0.5">
        {SUPPORTED_LANGUAGES.map((l) => (
          <button
            key={l.code}
            onClick={() => i18n.changeLanguage(l.code)}
            className={`flex-1 py-1 rounded-md text-[11px] font-medium transition-colors ${
              i18n.resolvedLanguage === l.code ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            {l.label}
          </button>
        ))}
      </div>
    </div>
  )
}

/**
 * Selector de tema (claro / oscuro / sistema) dentro del menú de cuenta.
 */
function ThemeSwitcher() {
  const { theme, setTheme } = useTheme()
  const { t } = useTranslation()
  const options: { value: Theme; label: string; icon: string }[] = [
    { value: 'light', label: t('nav.themeLight'), icon: '☀' },
    { value: 'dark', label: t('nav.themeDark'), icon: '☾' },
    { value: 'system', label: t('nav.themeSystem'), icon: '⛶' },
  ]
  return (
    <div className="px-2 py-1.5">
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5 px-1">{t('nav.theme')}</p>
      <div className="flex gap-0.5 bg-slate-900 rounded-lg p-0.5">
        {options.map((o) => (
          <button
            key={o.value}
            onClick={() => setTheme(o.value)}
            className={`flex-1 flex items-center justify-center gap-1 py-1 rounded-md text-[11px] font-medium transition-colors ${
              theme === o.value ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            <span>{o.icon}</span>{o.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function AccountMenu({ onLogout }: { onLogout: () => void }) {
  const { t } = useTranslation()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function handleEscape(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [open])

  function go(path: string) {
    setOpen(false)
    navigate(path)
  }

  const itemClasses =
    'w-full flex items-center gap-2.5 px-3 py-2 text-sm text-slate-300 hover:bg-white/[0.08] hover:text-white rounded-lg transition-colors text-left'

  return (
    <div ref={containerRef} className="relative">
      {open && (
        <div
          role="menu"
          className="absolute bottom-full left-0 right-0 mb-2 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl p-1.5 space-y-0.5"
        >
          <button role="menuitem" onClick={() => go('/settings')} className={itemClasses}>
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            {t('nav.accountSettings')}
          </button>
          <button role="menuitem" onClick={() => go('/security/2fa')} className={itemClasses}>
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            {t('nav.security2fa')}
          </button>
          {user?.isAdmin && (
            <button role="menuitem" onClick={() => go('/admin')} className={itemClasses}>
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0 .656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              {t('nav.adminPanel')}
            </button>
          )}
          <hr className="border-slate-700 my-1" />
          <ThemeSwitcher />
          <LanguageSwitcher />
          <hr className="border-slate-700 my-1" />
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false)
              onLogout()
            }}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 rounded-lg transition-colors text-left"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
            </svg>
            {t('nav.logout')}
          </button>
        </div>
      )}

      <button
        onClick={() => setOpen(!open)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="w-full flex items-center gap-3 rounded-xl px-2 py-2 hover:bg-white/[0.06] transition-colors"
      >
        <div className="w-9 h-9 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-xs font-bold text-white shrink-0">
          {userInitials(user)}
        </div>
        <div className="min-w-0 flex-1 text-left">
          <p className="text-sm text-slate-200 font-medium truncate">{user?.username}</p>
          <p className="text-[11px] text-slate-500 truncate">{user?.email}</p>
        </div>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className={`h-4 w-4 text-slate-500 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" />
        </svg>
      </button>
    </div>
  )
}

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
const IconGenerator = () => (
  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714a2.25 2.25 0 00.659 1.591L19 14.5M14.25 3.104c.251.023.501.05.75.082M19 14.5l-3.5 3.5m0 0l-3.5-3.5M15.5 18H8.5" />
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

// Las etiquetas son CLAVES i18n: se traducen en render con t() (ES/EN).
const navSections: NavSection[] = [
  {
    label: 'nav.sections.principal',
    items: [
      { path: '/dashboard', label: 'nav.dashboard', shortLabel: 'Dash', icon: <IconDashboard />, exact: true },
    ],
  },
  {
    label: 'nav.sections.markets',
    items: [
      { path: '/market', label: 'nav.market', shortLabel: 'Market', icon: <IconMarket /> },
      { path: '/analysis', label: 'nav.technicalAnalysis', shortLabel: 'TA', icon: <IconAnalysis /> },
      { path: '/blockchain', label: 'nav.blockchain', shortLabel: 'Chain', icon: <IconBlockchain /> },
    ],
  },
  {
    label: 'nav.sections.strategies',
    items: [
      { path: '/strategies', label: 'nav.generator', shortLabel: 'Gen', icon: <IconGenerator /> },
    ],
  },
  {
    label: 'nav.sections.management',
    items: [
      { path: '/portfolio', label: 'nav.portfolio', shortLabel: 'Port', icon: <IconPortfolio /> },
      { path: '/alerts', label: 'nav.alerts', shortLabel: 'Alerts', icon: <IconAlerts /> },
    ],
  },
  {
    label: 'nav.sections.information',
    items: [
      { path: '/news', label: 'nav.news', shortLabel: 'News', icon: <IconNews /> },
    ],
  },
]

// Flat list for mobile bottom bar
const navItemsFlat = navSections.flatMap(s => s.items)

function AppShell() {
  const { user, logout } = useAuth()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="app-shell-height overflow-hidden bg-slate-900 text-slate-100 flex flex-col">
      {/* Ticker bar — cotizaciones en tiempo real */}
      <TickerBar />

      {/* Paleta de comandos global (⌘K / Ctrl+K) */}
      <CommandPalette />

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
          <div className="h-16 px-5 flex items-center justify-between border-b border-white/10">
            <button
              className="text-lg font-bold tracking-tight"
              onClick={() => navigate('/dashboard')}
            >
              <span className="text-blue-400">Crypto</span>World
            </button>
            <NotificationBell />
          </div>

          {/* Buscador global — abre la paleta de comandos (⌘K) */}
          <div className="px-3 pt-3">
            <button
              onClick={() => window.dispatchEvent(new Event('open-command-palette'))}
              className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-slate-400 hover:text-white hover:border-white/20 transition-colors"
            >
              <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <span className="text-xs">{t('nav.search')}</span>
              <kbd className="ml-auto text-[10px] border border-white/15 rounded px-1.5 py-0.5">⌘K</kbd>
            </button>
          </div>

          {/* Navegación por secciones */}
          <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-5">
            {navSections.map(section => (
              <div key={section.label}>
                <p className="px-3 mb-1.5 text-[10px] font-semibold tracking-widest text-slate-500 uppercase select-none">
                  {t(section.label)}
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
                            : 'text-slate-400 hover:bg-white/[0.08] hover:text-slate-100',
                        ].join(' ')
                      }
                    >
                      {item.icon}
                      <span>{t(item.label)}</span>
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

          <div className="mt-auto p-3 border-t border-white/10">
            <AccountMenu onLogout={handleLogout} />
          </div>
        </aside>

        <div className="flex-1 min-w-0 flex flex-col">
          {/* Cabecera móvil: hamburguesa + marca */}
          <div className="lg:hidden h-12 shrink-0 border-b border-slate-700/70 bg-slate-800/80 backdrop-blur px-3 flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(true)}
              aria-label="Abrir menú de navegación"
              className="rounded-lg p-2 text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            <button
              className="text-base font-bold tracking-tight"
              onClick={() => navigate('/dashboard')}
            >
              <span className="text-blue-400">Crypto</span>World
            </button>
            <NotificationBell className="ml-auto" />
          </div>

          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            <Outlet />
          </main>

          {/* Barra de navegación inferior (móvil): siempre visible gracias a
              la altura fija del shell; respeta la safe-area de iOS */}
          <nav className="lg:hidden shrink-0 border-t border-slate-700 bg-slate-800 px-1 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] flex justify-between">
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
