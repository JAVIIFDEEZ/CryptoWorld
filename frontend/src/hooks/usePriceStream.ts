/**
 * hooks/usePriceStream.ts — Precios en tiempo real por WebSocket.
 *
 * Se conecta al stream de precios del backend (Channels) y mantiene un mapa
 * symbol → { price, change } que se actualiza por push, sustituyendo el polling.
 * Reconexión automática con backoff. Degrada con elegancia: si no hay WS, el
 * mapa simplemente queda vacío y la UI sigue con sus datos por HTTP.
 */

import { useEffect, useRef, useState } from 'react'

export interface LivePrice {
  price: number | null
  change: number | null
}

/** Deriva la URL de un stream WebSocket a partir de la base de la API. */
export function wsStreamUrl(path: string): string {
  const api = import.meta.env.VITE_API_URL as string | undefined
  if (api && /^https?:\/\//i.test(api)) {
    // Base absoluta (p. ej. https://api.host/api) → wss://api.host<path>
    const u = new URL(api)
    const proto = u.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${u.host}${path}`
  }
  // Base relativa (/api): mismo host que la página (Vite proxya /ws en dev).
  if (typeof window !== 'undefined') {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}${path}`
  }
  return ''
}

/** URL del stream de precios. */
export function priceStreamUrl(): string {
  return wsStreamUrl('/ws/prices/')
}

export function usePriceStream(): { prices: Record<string, LivePrice>; connected: boolean } {
  const [prices, setPrices] = useState<Record<string, LivePrice>>({})
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const retryRef = useRef(0)
  const closedRef = useRef(false)

  useEffect(() => {
    closedRef.current = false
    let reconnectTimer: number | undefined

    function connect() {
      const url = priceStreamUrl()
      if (!url || typeof WebSocket === 'undefined') return
      let ws: WebSocket
      try { ws = new WebSocket(url) } catch { return }
      wsRef.current = ws

      ws.onopen = () => { retryRef.current = 0; setConnected(true) }

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg?.type !== 'price_update' || !Array.isArray(msg.data)) return
          setPrices((prev) => {
            const next = { ...prev }
            for (const it of msg.data) {
              if (it?.symbol) next[it.symbol] = { price: it.price ?? null, change: it.change ?? null }
            }
            return next
          })
        } catch { /* mensaje no JSON */ }
      }

      ws.onclose = () => {
        setConnected(false)
        wsRef.current = null
        if (closedRef.current) return
        // Reconexión con backoff exponencial (máx. 30 s).
        const delay = Math.min(1000 * 2 ** retryRef.current, 30_000)
        retryRef.current += 1
        reconnectTimer = window.setTimeout(connect, delay)
      }

      ws.onerror = () => { ws.close() }
    }

    connect()
    return () => {
      closedRef.current = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      wsRef.current?.close()
    }
  }, [])

  return { prices, connected }
}
