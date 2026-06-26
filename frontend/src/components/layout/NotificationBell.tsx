/**
 * components/layout/NotificationBell.tsx — Campana del centro de notificaciones.
 *
 * Muestra el nº de no leídas y, al abrir, un panel con el feed unificado
 * (señales, ballenas, predicciones resueltas, alertas de precio). Abrir marca
 * todas como leídas (limpia el contador) conservando el resaltado de esta vista.
 * Sondea el contador en segundo plano cada 60 s.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  notificationsService,
  type NotificationItem,
  type NotificationKind,
  type NotificationsFeed,
} from '@/services/notificationsService'

const KIND_ICON: Record<NotificationKind, string> = {
  signal: '📈', whale: '🐋', prediction: '🔮', price: '🔔',
}

function ago(ts: string): string {
  const d = (Date.now() - new Date(ts).getTime()) / 1000
  if (d < 60) return 'ahora'
  if (d < 3600) return `${Math.floor(d / 60)}m`
  if (d < 86400) return `${Math.floor(d / 3600)}h`
  return `${Math.floor(d / 86400)}d`
}

export default function NotificationBell({ className = '' }: Readonly<{ className?: string }>) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [feed, setFeed] = useState<NotificationsFeed | null>(null)
  const [unread, setUnread] = useState(0)
  const pollRef = useRef<number>(0)

  const refresh = useCallback(async () => {
    try {
      const f = await notificationsService.getNotifications()
      setFeed(f)
      if (!open) setUnread(f.unread)
    } catch { /* sin notificaciones */ }
  }, [open])

  useEffect(() => {
    refresh()
    pollRef.current = window.setInterval(refresh, 60_000)
    return () => window.clearInterval(pollRef.current)
  }, [refresh])

  async function togglePanel() {
    const next = !open
    setOpen(next)
    if (next) {
      try {
        const f = await notificationsService.getNotifications()
        setFeed(f)
        if (f.unread > 0) await notificationsService.markSeen()
      } catch { /* ignora */ }
      setUnread(0)
    }
  }

  function openItem(it: NotificationItem) {
    setOpen(false)
    navigate(it.link)
  }

  return (
    <>
      <button
        onClick={togglePanel}
        aria-label="Notificaciones"
        className={`relative rounded-lg p-2 text-slate-300 hover:bg-white/10 hover:text-white transition-colors ${className}`}
      >
        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-red-500 text-white text-[9px] font-bold">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {open && (
        <>
          <button className="fixed inset-0 z-[90]" aria-label="Cerrar" onClick={() => setOpen(false)} />
          <div className="fixed z-[95] top-14 right-3 sm:right-5 w-[22rem] max-w-[calc(100vw-1.5rem)] bg-slate-800 border border-slate-700 rounded-xl shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700">
              <h3 className="text-sm font-semibold text-white">Notificaciones</h3>
              <span className="text-[10px] text-slate-500">{feed?.count ?? 0} recientes</span>
            </div>
            <div className="max-h-96 overflow-y-auto">
              {(!feed || feed.items.length === 0) && (
                <p className="px-4 py-8 text-center text-sm text-slate-500">No tienes notificaciones todavía.</p>
              )}
              {feed?.items.map((it) => (
                <button
                  key={it.id}
                  onClick={() => openItem(it)}
                  className={`w-full flex items-start gap-3 px-4 py-2.5 text-left border-b border-slate-800/60 last:border-0 hover:bg-slate-700/40 transition-colors ${it.unread ? 'bg-blue-600/10' : ''}`}
                >
                  <span className="text-base shrink-0 mt-0.5">{KIND_ICON[it.kind]}</span>
                  <span className="flex-1 min-w-0">
                    <span className="flex items-center gap-2">
                      <span className="text-xs font-medium text-slate-200 truncate">{it.title}</span>
                      {it.unread && <span className="w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />}
                    </span>
                    {it.body && <span className="block text-[11px] text-slate-400 truncate">{it.body}</span>}
                  </span>
                  <span className="text-[10px] text-slate-600 shrink-0">{ago(it.created_at)}</span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  )
}
