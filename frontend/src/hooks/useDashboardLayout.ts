/**
 * hooks/useDashboardLayout.ts — Personalización del dashboard por usuario.
 *
 * Guarda en localStorage qué widgets se muestran y en qué orden, para que cada
 * usuario adapte su panel de inicio. Es tolerante a cambios del catálogo de
 * widgets: respeta el orden guardado, añade los nuevos al final y descarta los
 * que ya no existen.
 */

import { useCallback, useEffect, useState } from 'react'

export interface DashboardWidget {
  id: string
  visible: boolean
}

export const WIDGET_LABELS: Record<string, string> = {
  market: 'Mercado global',
  catalog: 'Catálogo',
  watchlist: 'Mi seguimiento',
  movers: 'Movimiento del mercado',
}

const DEFAULT_LAYOUT: DashboardWidget[] = [
  { id: 'market', visible: true },
  { id: 'catalog', visible: true },
  { id: 'watchlist', visible: true },
  { id: 'movers', visible: true },
]

const STORAGE_KEY = 'cw.dashboard.layout.v1'

function reconcile(stored: DashboardWidget[]): DashboardWidget[] {
  const known = new Set(DEFAULT_LAYOUT.map((w) => w.id))
  const kept = stored.filter((w) => known.has(w.id))
  const seen = new Set(kept.map((w) => w.id))
  const appended = DEFAULT_LAYOUT.filter((w) => !seen.has(w.id))
  return [...kept, ...appended]
}

function load(): DashboardWidget[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_LAYOUT
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return DEFAULT_LAYOUT
    return reconcile(parsed.filter((w) => w && typeof w.id === 'string'))
  } catch {
    return DEFAULT_LAYOUT
  }
}

export function useDashboardLayout() {
  const [layout, setLayout] = useState<DashboardWidget[]>(load)

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(layout)) } catch { /* sin persistencia */ }
  }, [layout])

  const toggle = useCallback((id: string) => {
    setLayout((l) => l.map((w) => (w.id === id ? { ...w, visible: !w.visible } : w)))
  }, [])

  const move = useCallback((id: string, dir: -1 | 1) => {
    setLayout((l) => {
      const i = l.findIndex((w) => w.id === id)
      const j = i + dir
      if (i < 0 || j < 0 || j >= l.length) return l
      const next = [...l]
      ;[next[i], next[j]] = [next[j], next[i]]
      return next
    })
  }, [])

  const reset = useCallback(() => setLayout(DEFAULT_LAYOUT), [])

  return { layout, toggle, move, reset }
}
