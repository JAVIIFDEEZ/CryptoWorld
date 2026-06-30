/**
 * components/analysis/tabs/MtfTab.tsx — Confluencia multi-marco temporal.
 *
 * Muestra el veredicto de cada marco (15m/1h/4h/1d), la barra de alineación
 * ponderada (los marcos altos pesan más) y el % de acuerdo. La idea profesional:
 * una señal vale más cuando el intradía va A FAVOR de la tendencia de fondo.
 */

import type { MtfConfluence, MtfFrame } from '@/services/analysisService'
import { EmptyState } from '@/components/analysis/analysisShared'

const VERDICT_STYLE: Record<string, { chip: string; label: string }> = {
  ALINEADO_ALCISTA: { chip: 'bg-green-500/15 text-green-300 border-green-500/30', label: '▲ Marcos alineados — alcista' },
  ALINEADO_BAJISTA: { chip: 'bg-red-500/15 text-red-300 border-red-500/30', label: '▼ Marcos alineados — bajista' },
  MIXTO: { chip: 'bg-amber-500/15 text-amber-300 border-amber-500/30', label: '⚠ Marcos en conflicto' },
  NEUTRAL: { chip: 'bg-slate-700/40 text-slate-300 border-slate-600/40', label: '— Sin dirección clara' },
}

function frameTone(normalized?: number): string {
  if (normalized == null) return 'text-slate-500'
  if (normalized > 0.1) return 'text-green-400'
  if (normalized < -0.1) return 'text-red-400'
  return 'text-yellow-400'
}

function AlignmentBar({ value }: { value: number }) {
  // value ∈ [-1, +1] → posición del marcador en la barra bajista↔alcista
  const pct = ((value + 1) / 2) * 100
  return (
    <div className="space-y-1">
      <div className="relative h-3 rounded-full overflow-hidden flex">
        <div className="w-1/2 bg-gradient-to-r from-red-500/60 to-slate-600/40" />
        <div className="w-1/2 bg-gradient-to-r from-slate-600/40 to-green-500/60" />
        <div
          className="absolute top-0 bottom-0 w-1.5 bg-white rounded-full shadow transition-all"
          style={{ left: `calc(${Math.min(Math.max(pct, 1), 99)}% - 3px)` }}
        />
      </div>
      <div className="flex justify-between text-[9px] text-slate-500">
        <span className="text-red-400">−1 bajista</span>
        <span>0</span>
        <span className="text-green-400">+1 alcista</span>
      </div>
    </div>
  )
}

function FrameCard({ f }: { f: MtfFrame }) {
  if (f.error) {
    return (
      <div className="bg-slate-900/40 rounded-lg border border-slate-700/50 p-3 opacity-60">
        <p className="text-xs font-bold text-slate-400">{f.interval}</p>
        <p className="text-[10px] text-slate-600 mt-1">sin datos</p>
      </div>
    )
  }
  const n = f.normalized ?? 0
  return (
    <div className="bg-slate-900/40 rounded-lg border border-slate-700/50 p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-bold text-slate-200">{f.interval}</p>
        <span className="text-[9px] text-slate-600" title="Peso en la alineación (los marcos altos pesan más)">×{f.weight}</span>
      </div>
      <p className={`text-lg font-bold font-mono mt-1 ${frameTone(n)}`}>
        {n > 0 ? '+' : ''}{(n * 100).toFixed(0)}%
      </p>
      <div className="flex gap-1 mt-1.5 text-[9px]">
        <span className="text-green-400">▲{f.buy_count ?? 0}</span>
        <span className="text-yellow-400">—{f.neutral_count ?? 0}</span>
        <span className="text-red-400">▼{f.sell_count ?? 0}</span>
      </div>
    </div>
  )
}

export default function MtfTab({ data }: { data: MtfConfluence | null }) {
  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
          </svg>
        }
        title="Confluencia multi-marco temporal"
        description="Calcula las señales multi-indicador en 15m, 1h, 4h y 1d a la vez y mide si los marcos están alineados. Una señal intradía vale más cuando va a favor de la tendencia de fondo; operar contra los marcos superiores es la situación de mayor riesgo."
      />
    )
  }

  const v = VERDICT_STYLE[data.verdict] ?? VERDICT_STYLE.NEUTRAL

  return (
    <div className="space-y-4">
      {/* Veredicto de confluencia */}
      <div className={`rounded-xl border p-4 ${v.chip}`}>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <p className="text-sm font-bold uppercase tracking-wide">{v.label}</p>
          <span className="text-[11px] opacity-80">
            acuerdo {data.agreement_pct.toFixed(0)}% · {data.frames_analyzed} marcos
          </span>
        </div>
        {data.verdict_text && <p className="text-[11px] mt-1.5 text-slate-300">{data.verdict_text}</p>}
      </div>

      {/* Barra de alineación ponderada */}
      <div className="bg-slate-900/30 rounded-lg p-3">
        <div className="flex items-baseline justify-between mb-2">
          <p className="text-[10px] text-slate-500 uppercase">Alineación ponderada</p>
          <p className={`text-xl font-bold font-mono ${frameTone(data.alignment_score)}`}>
            {data.alignment_score > 0 ? '+' : ''}{data.alignment_score.toFixed(2)}
          </p>
        </div>
        <AlignmentBar value={data.alignment_score} />
        <p className="text-[10px] text-slate-600 mt-2">
          Media de los marcos ponderada por su peso (1d ×4 · 4h ×3 · 1h ×2 · 15m ×1): la tendencia de fondo manda sobre el ruido intradía.
        </p>
      </div>

      {/* Tarjetas por marco */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {data.frames.map((f) => <FrameCard key={f.interval} f={f} />)}
      </div>

      {data.disclaimer && <p className="text-[10px] text-slate-600">{data.disclaimer}</p>}
    </div>
  )
}
