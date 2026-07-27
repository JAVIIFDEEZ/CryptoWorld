/**
 * components/analysis/tabs/PatternsTab.tsx — Detección de patrones de velas.
 */

import type { PatternsResult } from '@/services/analysisService'
import {
  EmptyState, reliabilityBadge, reliabilityStars, signalBg, signalColor, signalDot, signalLabel,
} from '@/components/analysis/analysisShared'

export default function PatternsTab({ data }: { data: PatternsResult | null }) {
  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        }
        title="Detección de patrones de velas"
        description="Identifica formaciones chartistas clásicas (Doji, Hammer, Engulfing, etc.) en las últimas velas. Cada patrón incluye señal alcista/bajista y fiabilidad histórica."
      />
    )
  }

  if (data.patterns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3 text-center">
        <svg className="w-8 h-8 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-slate-400 text-sm">No se detectaron patrones en las últimas velas.</p>
        <p className="text-[11px] text-slate-500 max-w-xs">
          Los patrones requieren condiciones específicas de precio y volumen. Prueba con otro intervalo temporal.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-400">
        {data.patterns.length} patrón(es) detectado(s) — {data.total_candles} velas analizadas
      </p>
      {data.patterns.map((p, i) => (
        <div key={i} className={`rounded-lg border p-3 ${signalBg(p.signal)}`}>
          <div className="flex items-start justify-between">
            <div className="flex-1 mr-3">
              <p className="text-sm font-semibold text-white">{p.name}</p>
              <p className="text-xs text-slate-300 mt-0.5">{p.description}</p>
            </div>
            <div className="flex flex-col items-end gap-1.5 shrink-0">
              <span className="inline-flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full shrink-0 ${signalDot(p.signal)}`} />
                <span className={`text-xs font-bold ${signalColor(p.signal)}`}>{signalLabel(p.signal)}</span>
              </span>
              <span className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full ${reliabilityBadge(p.reliability)}`}>
                <span>{reliabilityStars(p.reliability)}</span>
                <span>{p.reliability}</span>
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
