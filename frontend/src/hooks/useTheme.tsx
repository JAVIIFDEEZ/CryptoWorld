/**
 * hooks/useTheme.tsx — Tema claro / oscuro / sistema.
 *
 * Aplica el tema añadiendo la clase `theme-light` al <html> (el oscuro es el
 * valor por defecto, sin clase → cero regresión). Persiste la preferencia y, en
 * modo «sistema», sigue la preferencia del SO en vivo. El cambio de paleta es
 * automático en toda la app gracias a las variables CSS de index.css.
 */

import {
  createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode,
} from 'react'

export type Theme = 'light' | 'dark' | 'system'
type Resolved = 'light' | 'dark'

const STORAGE_KEY = 'cw.theme'

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined'
    && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function loadTheme(): Theme {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'light' || v === 'dark' || v === 'system') return v
  } catch { /* sin almacenamiento */ }
  return 'dark'
}

export function applyTheme(resolved: Resolved): void {
  if (typeof document !== 'undefined') {
    document.documentElement.classList.toggle('theme-light', resolved === 'light')
  }
}

interface ThemeCtx {
  theme: Theme
  resolved: Resolved
  setTheme: (t: Theme) => void
}

const ThemeContext = createContext<ThemeCtx | null>(null)

export function ThemeProvider({ children }: Readonly<{ children: ReactNode }>) {
  const [theme, setThemeState] = useState<Theme>(loadTheme)
  const [systemDark, setSystemDark] = useState<boolean>(systemPrefersDark)

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setSystemDark(mq.matches)
    mq.addEventListener?.('change', onChange)
    return () => mq.removeEventListener?.('change', onChange)
  }, [])

  const resolved: Resolved = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme

  useEffect(() => { applyTheme(resolved) }, [resolved])

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t)
    try { localStorage.setItem(STORAGE_KEY, t) } catch { /* sin almacenamiento */ }
  }, [])

  const value = useMemo(() => ({ theme, resolved, setTheme }), [theme, resolved, setTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeCtx {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme debe usarse dentro de ThemeProvider')
  return ctx
}
