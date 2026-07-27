/**
 * components/layout/CommandPalette.tsx — Paleta de comandos global (⌘K / Ctrl+K).
 *
 * Búsqueda y navegación rápida por toda la app: secciones (Dashboard, Mercado,
 * Blockchain…) y activos (BTC, ETH…). Se abre con ⌘K/Ctrl+K o disparando el
 * evento 'open-command-palette'. Navegación por teclado (↑/↓/Enter, Esc cierra).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { analysisService, type CryptoAsset } from '@/services/analysisService'

interface Item {
  id: string
  label: string
  sublabel?: string
  path: string
  group: 'Secciones' | 'Activos'
  badge?: string
}

const NAV_ITEMS: Item[] = [
  { id: 'nav-dashboard', label: 'Dashboard', path: '/dashboard', group: 'Secciones' },
  { id: 'nav-market', label: 'Mercado', path: '/market', group: 'Secciones' },
  { id: 'nav-analysis', label: 'Análisis Técnico', path: '/analysis', group: 'Secciones' },
  { id: 'nav-blockchain', label: 'Blockchain', path: '/blockchain', group: 'Secciones' },
  { id: 'nav-strategies', label: 'Generador de estrategias', path: '/strategies', group: 'Secciones' },
  { id: 'nav-portfolio', label: 'Portfolio', path: '/portfolio', group: 'Secciones' },
  { id: 'nav-alerts', label: 'Alertas', path: '/alerts', group: 'Secciones' },
  { id: 'nav-news', label: 'Noticias', path: '/news', group: 'Secciones' },
  { id: 'nav-learn', label: 'Academia', path: '/learn', group: 'Secciones' },
  { id: 'nav-settings', label: 'Ajustes de cuenta', path: '/settings', group: 'Secciones' },
  { id: 'nav-2fa', label: 'Seguridad 2FA', path: '/security/2fa', group: 'Secciones' },
]

export default function CommandPalette() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [assets, setAssets] = useState<Item[]>([])
  const [assetsLoaded, setAssetsLoaded] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const close = useCallback(() => { setOpen(false); setQuery(''); setActive(0) }, [])

  // Carga perezosa del catálogo de activos la primera vez que se abre.
  useEffect(() => {
    if (!open || assetsLoaded) return
    setAssetsLoaded(true)
    analysisService.getAssets()
      .then((list: CryptoAsset[]) => setAssets(list.map((a) => ({
        id: `asset-${a.symbol}`,
        label: a.symbol,
        sublabel: a.name,
        path: `/assets/${a.symbol}`,
        group: 'Activos' as const,
        badge: a.is_bullish_24h ? '▲' : '▼',
      }))))
      .catch(() => { /* sin catálogo */ })
  }, [open, assetsLoaded])

  // Atajo global ⌘K / Ctrl+K + evento personalizado para abrir desde un botón.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((v) => !v)
      } else if (e.key === 'Escape') {
        close()
      }
    }
    function onOpen() { setOpen(true) }
    window.addEventListener('keydown', onKey)
    window.addEventListener('open-command-palette', onOpen)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('open-command-palette', onOpen)
    }
  }, [close])

  useEffect(() => { if (open) inputRef.current?.focus() }, [open])

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    const all = [...NAV_ITEMS, ...assets]
    if (!q) return all.slice(0, 20)
    return all
      .filter((it) => it.label.toLowerCase().includes(q) || (it.sublabel?.toLowerCase().includes(q)))
      .slice(0, 30)
  }, [query, assets])

  useEffect(() => { setActive(0) }, [query])

  function choose(it: Item | undefined) {
    if (!it) return
    close()
    navigate(it.path)
  }

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)) }
    else if (e.key === 'Enter') { e.preventDefault(); choose(results[active]) }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[12vh] px-4" role="dialog" aria-modal="true">
      <button className="absolute inset-0 bg-black/60 backdrop-blur-sm" aria-label="Cerrar" onClick={close} />
      <div className="relative w-full max-w-xl bg-slate-800 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 border-b border-slate-700">
          <svg className="w-4 h-4 text-slate-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKey}
            placeholder="Buscar secciones o activos…"
            className="flex-1 bg-transparent py-3 text-sm text-slate-100 placeholder-slate-500 focus:outline-none"
          />
          <kbd className="text-[10px] text-slate-500 border border-slate-600 rounded px-1.5 py-0.5">Esc</kbd>
        </div>

        <div className="max-h-80 overflow-y-auto py-2">
          {results.length === 0 && (
            <p className="px-4 py-6 text-center text-sm text-slate-500">Sin resultados para «{query}».</p>
          )}
          {results.map((it, i) => (
            <button
              key={it.id}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(it)}
              className={`w-full flex items-center gap-3 px-4 py-2 text-left transition-colors ${
                i === active ? 'bg-blue-600/20' : 'hover:bg-slate-700/40'
              }`}
            >
              <span className={`text-[9px] uppercase tracking-wide w-14 shrink-0 ${it.group === 'Activos' ? 'text-amber-400/70' : 'text-slate-500'}`}>
                {it.group === 'Activos' ? 'Activo' : 'Ir a'}
              </span>
              <span className="text-sm text-slate-200 font-medium">{it.label}</span>
              {it.sublabel && <span className="text-xs text-slate-500 truncate">{it.sublabel}</span>}
              {it.badge && <span className={`ml-auto text-xs ${it.badge === '▲' ? 'text-green-400' : 'text-red-400'}`}>{it.badge}</span>}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3 px-4 py-2 border-t border-slate-700 text-[10px] text-slate-500">
          <span><kbd className="border border-slate-600 rounded px-1">↑</kbd> <kbd className="border border-slate-600 rounded px-1">↓</kbd> navegar</span>
          <span><kbd className="border border-slate-600 rounded px-1">↵</kbd> abrir</span>
          <span className="ml-auto">⌘K / Ctrl+K</span>
        </div>
      </div>
    </div>
  )
}
