/**
 * components/TickerBar.tsx — Barra de cotizaciones animada.
 *
 * Muestra los activos principales con su precio y variación 24h
 * desplazándose horizontalmente de forma continua (estilo Bloomberg/CNBC).
 * Consume GET /api/assets/ y se refresca cada 60s.
 */

import { useEffect, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import { analysisService, type CryptoAsset } from '@/services/analysisService'

/* eslint-disable @typescript-eslint/no-explicit-any */

// Velocidad de desplazamiento en px/frame (~60fps)
const SCROLL_SPEED = 0.6

export default function TickerBar() {
  const [assets, setAssets] = useState<CryptoAsset[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)
  const innerRef  = useRef<HTMLDivElement>(null)
  const offsetRef = useRef(0)
  const rafRef    = useRef<number>(0)
  const pausedRef = useRef(false)

  // ── Cargar datos ──────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const data = await analysisService.getAssets()
        if (!cancelled) setAssets(data)
      } catch {
        // silencioso — si falla, ticker queda vacío
      }
    }

    load()
    const timer = window.setInterval(load, 60_000) // refresco cada 60s
    return () => { cancelled = true; clearInterval(timer) }
  }, [])

  // ── Animación continua ────────────────────────────────────────
  useEffect(() => {
    if (assets.length === 0) return

    function animate() {
      if (!pausedRef.current && innerRef.current) {
        offsetRef.current -= SCROLL_SPEED
        // Cuando el primer "set" entero sale por la izquierda, resetear offset
        const halfWidth = innerRef.current.scrollWidth / 2
        if (Math.abs(offsetRef.current) >= halfWidth) {
          offsetRef.current = 0
        }
        innerRef.current.style.transform = `translateX(${offsetRef.current}px)`
      }
      rafRef.current = requestAnimationFrame(animate)
    }

    rafRef.current = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(rafRef.current)
  }, [assets])

  if (assets.length === 0) return null

  // Duplicamos la lista para crear efecto infinito
  const items = [...assets, ...assets]

  return (
    <div
      ref={scrollRef}
      className="w-full bg-slate-950 border-b border-slate-800 overflow-hidden h-8 flex items-center"
      onMouseEnter={() => { pausedRef.current = true }}
      onMouseLeave={() => { pausedRef.current = false }}
    >
      <div
        ref={innerRef}
        className="flex items-center whitespace-nowrap will-change-transform"
        style={{ gap: '2rem' }}
      >
        {items.map((a, idx) => {
          const change = parseFloat(a.price_change_24h ?? '0')
          const isUp   = change >= 0
          const price  = parseFloat(a.current_price)
          const fmt    = price >= 1
            ? price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            : price.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 6 })

          return (
            <Link
              key={`${a.symbol}-${idx}`}
              to={`/assets/${a.symbol}`}
              className="flex items-center gap-1.5 text-xs hover:bg-slate-800/60 px-2 py-1 rounded transition-colors shrink-0"
            >
              {a.logo_url && (
                <img src={a.logo_url} alt="" className="w-4 h-4 rounded-full" />
              )}
              <span className="text-slate-400 font-medium">{a.symbol}</span>
              <span className="text-slate-200 font-mono">${fmt}</span>
              <span className={`font-mono font-medium ${isUp ? 'text-green-400' : 'text-red-400'}`}>
                {isUp ? '▲' : '▼'}{Math.abs(change).toFixed(2)}%
              </span>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
