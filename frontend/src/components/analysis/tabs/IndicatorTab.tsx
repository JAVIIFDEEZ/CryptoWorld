/**
 * components/analysis/tabs/IndicatorTab.tsx — Cálculo individual de indicador.
 */

import type { AnalysisResult, AnalysisType } from '@/services/analysisService'
import {
  EmptyState, signalBg, signalColor, signalDot, signalLabel,
} from '@/components/analysis/analysisShared'

// ── Gauge RSI ─────────────────────────────────────────────────────
function RsiGauge({ value }: { value: number }) {
  const pct = Math.min(Math.max(value, 0), 100)
  const color = pct >= 70 ? 'text-red-400' : pct <= 30 ? 'text-green-400' : 'text-yellow-400'
  const label = pct >= 70 ? 'Sobrecompra ≥ 70' : pct <= 30 ? 'Sobreventa ≤ 30' : 'Zona neutral'
  return (
    <div className="space-y-2">
      <div className="relative h-5 rounded-full overflow-hidden flex">
        <div className="w-[30%] bg-green-900/50 border-r border-slate-700" />
        <div className="w-[40%] bg-slate-700/30 border-r border-slate-700" />
        <div className="w-[30%] bg-red-900/50" />
        <div
          className="absolute top-1 bottom-1 w-2 bg-white rounded-full shadow transition-all"
          style={{ left: `calc(${pct}% - 4px)` }}
        />
      </div>
      <div className="flex justify-between text-[9px] text-slate-500">
        <span className="text-green-500">0 — Sobreventa</span>
        <span>30 &nbsp;&nbsp;&nbsp; 70</span>
        <span className="text-red-500">Sobrecompra — 100</span>
      </div>
      <div className="flex items-baseline gap-2 mt-1">
        <span className={`text-3xl font-bold font-mono ${color}`}>{pct.toFixed(2)}</span>
        <span className="text-xs text-slate-400">{label}</span>
      </div>
    </div>
  )
}

export default function IndicatorTab({ data, indType }: { data: AnalysisResult | null; indType: AnalysisType }) {
  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
          </svg>
        }
        title="Cálculo individual de indicador"
        description="Selecciona RSI, MACD, SMA, EMA o Bollinger y obtén el valor actual con interpretación detallada sobre datos reales de mercado."
      />
    )
  }

  const r = data.result as Record<string, unknown> | null
  if (!r || data.status === 'failed') {
    return <div className="text-red-400 text-sm">{(r as Record<string, string>)?.error ?? 'Error en el análisis.'}</div>
  }

  const signal = (r.signal as string) ?? 'NEUTRAL'
  const interp = (r.interpretation as string) ?? ''
  const numValue = typeof r.value === 'number' ? r.value : null

  return (
    <div className="space-y-4">
      {/* Señal principal */}
      <div className={`rounded-xl border p-4 ${signalBg(signal)}`}>
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-slate-400 uppercase font-medium">{r.indicator as string}</p>
          <span className="inline-flex items-center gap-1.5">
            <span className={`w-2.5 h-2.5 rounded-full ${signalDot(signal)}`} />
            <span className={`text-lg font-bold ${signalColor(signal)}`}>{signalLabel(signal)}</span>
          </span>
        </div>

        {/* RSI: gauge visual */}
        {indType === 'RSI' && numValue !== null ? (
          <RsiGauge value={numValue} />
        ) : (
          <p className={`text-2xl font-bold font-mono ${signalColor(signal)}`}>
            {numValue !== null ? numValue.toFixed(4) : String(r.value ?? '—')}
          </p>
        )}

        {interp && (
          <p className="text-xs text-slate-300 mt-3 pt-3 border-t border-slate-700/50">{interp}</p>
        )}
      </div>

      {/* Datos extra */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Object.entries(r).map(([key, val]) => {
          if (['indicator', 'signal', 'interpretation', 'series', 'params'].includes(key)) return null
          if (key.startsWith('series_')) return null
          if (val === null || val === undefined) return null
          if (key === 'value' && indType === 'RSI') return null  // ya mostrado en gauge
          return (
            <div key={key} className="bg-slate-900/50 rounded-lg p-3">
              <p className="text-[10px] text-slate-500 uppercase">{key.replace(/_/g, ' ')}</p>
              <p className="text-sm font-mono text-slate-200">
                {typeof val === 'number' ? val.toFixed(4) : String(val)}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
