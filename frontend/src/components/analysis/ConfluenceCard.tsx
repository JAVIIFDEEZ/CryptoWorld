/**
 * components/ConfluenceCard.tsx — Ficha de confluencia técnica de un activo.
 *
 * Renderiza dentro de la SPA el resultado del endpoint
 * GET /api/assets/<symbol>/confluence/: veredicto con confianza, tendencia,
 * narrativa, resumen de indicadores, soportes/resistencias y Fibonacci.
 * Enlaza también a la landing pública SEO (servida por el backend).
 */

import { useEffect, useState } from 'react'
import {
  confluenceService,
  publicLandingUrl,
  type ConfluenceCard as ConfluenceCardData,
} from '@/services/confluenceService'
import { useCurrency } from '@/hooks/useCurrency'
import Skeleton from '@/components/ui/Skeleton'

const VERDICT_LABEL: Record<string, string> = {
  COMPRA_FUERTE: 'Compra fuerte',
  COMPRA: 'Compra',
  NEUTRAL: 'Neutral',
  VENTA: 'Venta',
  VENTA_FUERTE: 'Venta fuerte',
}

/** Tono de color por señal (compra=verde, venta=rojo, neutral=gris). */
function toneOf(value: string): string {
  if (value === 'COMPRA' || value === 'COMPRA_FUERTE' || value === 'ALCISTA') return 'text-emerald-400'
  if (value === 'VENTA' || value === 'VENTA_FUERTE' || value === 'BAJISTA') return 'text-red-400'
  return 'text-slate-300'
}

function bgToneOf(value: string): string {
  if (value === 'COMPRA' || value === 'COMPRA_FUERTE' || value === 'ALCISTA') return 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
  if (value === 'VENTA' || value === 'VENTA_FUERTE' || value === 'BAJISTA') return 'bg-red-500/15 text-red-400 border-red-500/30'
  return 'bg-slate-700/40 text-slate-300 border-slate-600'
}

export default function ConfluenceCard({ symbol }: Readonly<{ symbol: string }>) {
  const { formatPrice } = useCurrency()
  const [card, setCard] = useState<ConfluenceCardData | null>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')

  useEffect(() => {
    let cancelled = false
    setStatus('loading')
    confluenceService
      .getConfluence(symbol)
      .then((data) => {
        if (!cancelled) {
          setCard(data)
          setStatus('ready')
        }
      })
      .catch(() => {
        if (!cancelled) setStatus('error')
      })
    return () => {
      cancelled = true
    }
  }, [symbol])

  if (status === 'loading') {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-6">
        <Skeleton className="h-5 w-56 mb-4" />
        <div className="flex gap-2 mb-4">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-8 w-32" />
        </div>
        <Skeleton className="h-24 w-full" />
      </div>
    )
  }

  if (status === 'error' || !card) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-6">
        <h2 className="text-lg font-semibold text-white mb-1">Ficha de confluencia</h2>
        <p className="text-slate-400 text-sm">
          No hay datos suficientes para generar la ficha técnica de {symbol} en este momento.
        </p>
      </div>
    )
  }

  const { verdict, trend, signals, support_resistance: sr, fibonacci: fibo } = card

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-6">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Ficha de confluencia técnica</h2>
          <p className="text-xs text-slate-500">
            Resumen automático · <span className="text-slate-400 font-medium">marco diario (1D)</span> · fuente: {card.data_source}
          </p>
        </div>
        <a
          href={publicLandingUrl(card.slug)}
          target="_blank"
          rel="noopener"
          className="text-xs text-blue-400 hover:text-blue-300 transition-colors shrink-0"
        >
          Ver ficha pública ↗
        </a>
      </div>

      {/* Chips de veredicto, confianza y tendencia */}
      <div className="flex flex-wrap gap-2 mb-5">
        <span className={`px-3 py-1.5 rounded-lg text-sm font-semibold border ${bgToneOf(verdict.verdict)}`}>
          {VERDICT_LABEL[verdict.verdict] ?? verdict.verdict}
        </span>
        <span className="px-3 py-1.5 rounded-lg text-sm font-medium border border-slate-600 bg-slate-700/40 text-slate-300">
          Confianza: {verdict.confidence_pct}% ({verdict.confidence_level})
        </span>
        <span className={`px-3 py-1.5 rounded-lg text-sm font-medium border ${bgToneOf(trend.trend)}`}>
          Tendencia: {trend.trend.charAt(0) + trend.trend.slice(1).toLowerCase()}
        </span>
      </div>

      {/* Narrativa (análisis derivado de los datos) */}
      <p className="text-sm text-slate-300 leading-relaxed mb-6">{card.narrative}</p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Soportes y resistencias */}
        <div className="bg-slate-900/40 rounded-lg border border-slate-700 p-4">
          <h3 className="text-sm font-semibold text-white mb-3">Soportes y resistencias</h3>
          <div className="space-y-1.5 text-sm">
            {sr.resistances.slice().reverse().map((r) => (
              <div key={`r-${r.level}`} className="flex justify-between">
                <span className="text-red-400">Resistencia</span>
                <span className="font-mono tabular-nums text-slate-200">{formatPrice(r.level)}</span>
                <span className="text-slate-500 text-xs w-14 text-right">{r.distance_pct}%</span>
              </div>
            ))}
            {sr.supports.map((s) => (
              <div key={`s-${s.level}`} className="flex justify-between">
                <span className="text-emerald-400">Soporte</span>
                <span className="font-mono tabular-nums text-slate-200">{formatPrice(s.level)}</span>
                <span className="text-slate-500 text-xs w-14 text-right">{s.distance_pct}%</span>
              </div>
            ))}
            {sr.supports.length === 0 && sr.resistances.length === 0 && (
              <p className="text-slate-500 text-xs">Sin niveles de pivote relevantes en el periodo.</p>
            )}
          </div>
        </div>

        {/* Fibonacci */}
        <div className="bg-slate-900/40 rounded-lg border border-slate-700 p-4">
          <h3 className="text-sm font-semibold text-white mb-3">
            Retrocesos de Fibonacci <span className="text-slate-500 font-normal">({trend.trend === 'ALCISTA' || fibo.direction === 'ALCISTA' ? 'impulso alcista' : 'impulso bajista'})</span>
          </h3>
          <div className="space-y-1.5 text-sm">
            {fibo.levels.map((l) => {
              const isNearest = fibo.nearest_level && l.price === fibo.nearest_level.price
              return (
                <div key={l.ratio} className={`flex justify-between ${isNearest ? 'text-blue-300 font-medium' : 'text-slate-300'}`}>
                  <span>{l.label}{isNearest ? ' · más cercano' : ''}</span>
                  <span className="font-mono tabular-nums">{formatPrice(l.price)}</span>
                </div>
              )
            })}
            {fibo.levels.length === 0 && (
              <p className="text-slate-500 text-xs">Rango insuficiente para trazar Fibonacci.</p>
            )}
          </div>
        </div>
      </div>

      {/* Resumen de indicadores */}
      <div className="mt-5">
        <div className="flex items-center gap-3 mb-3 text-xs">
          <span className="text-emerald-400">{signals.summary.buy_count} compra</span>
          <span className="text-red-400">{signals.summary.sell_count} venta</span>
          <span className="text-slate-400">{signals.summary.neutral_count} neutral</span>
          <span className="text-slate-500">· {signals.summary.total} indicadores</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
          {signals.indicators.map((ind) => (
            <div key={ind.name} className="flex items-center justify-between bg-slate-900/40 rounded-md px-3 py-2 border border-slate-700/60">
              <span className="text-xs text-slate-400 truncate">{ind.name}</span>
              <span className={`text-xs font-semibold ${toneOf(ind.signal)}`}>{ind.signal}</span>
            </div>
          ))}
        </div>
      </div>

      <p className="text-[11px] text-slate-500 mt-5">
        Indicadores calculados sobre velas diarias. Para explorar otros marcos temporales,
        predicción ML, patrones o backtesting, usa el panel de análisis interactivo más abajo ↓
      </p>
      <p className="text-[11px] text-slate-600 mt-1">
        Análisis generado automáticamente con fines informativos. No constituye asesoramiento financiero.
      </p>
    </div>
  )
}
