/**
 * components/ui/StatCard.tsx — Tarjeta de métrica del dashboard.
 *
 * Estructura: etiqueta atenuada → valor grande (mono, tabular) →
 * fila opcional con chip de variación y/o sub-texto. Acepta `children`
 * para alojar un minigráfico (Sparkline) o un medidor (Gauge).
 */

import type { ReactNode } from 'react'
import DeltaChip from './DeltaChip'

interface StatCardProps {
  label: string
  value: string
  sub?: string
  /** Variación porcentual; si se pasa, se muestra como chip. */
  delta?: number | string | null
  /** Color del valor principal. */
  tone?: 'default' | 'positive' | 'negative' | 'brand'
  children?: ReactNode
}

export default function StatCard({ label, value, sub, delta, tone = 'default', children }: StatCardProps) {
  const valueColor =
    tone === 'positive'
      ? 'text-positive'
      : tone === 'negative'
        ? 'text-negative'
        : tone === 'brand'
          ? 'text-blue-400'
          : 'text-white'

  const accent =
    tone === 'positive'
      ? 'border-l-2 border-l-positive'
      : tone === 'negative'
        ? 'border-l-2 border-l-negative'
        : tone === 'brand'
          ? 'border-l-2 border-l-blue-500'
          : ''

  return (
    <div className={`bg-slate-800/60 rounded-xl border border-slate-700 px-5 py-4 hover:border-slate-600 hover:bg-slate-800/80 transition-all ${accent}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-slate-500 text-xs font-medium uppercase tracking-wide">{label}</p>
        {delta !== undefined && delta !== null && <DeltaChip value={delta} size="sm" />}
      </div>
      <p className={`text-2xl font-bold font-mono tabular-nums mt-1.5 tracking-tight ${valueColor}`}>{value}</p>
      {sub && <p className="text-slate-500 text-xs mt-1">{sub}</p>}
      {children && <div className="mt-3">{children}</div>}
    </div>
  )
}
