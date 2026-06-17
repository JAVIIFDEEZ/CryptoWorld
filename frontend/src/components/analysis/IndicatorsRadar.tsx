/**
 * components/analysis/IndicatorsRadar.tsx — Radar de consenso de indicadores.
 *
 * Cada indicador es un eje; el valor es su "alcismo" (0 = venta fuerte, 50 =
 * neutral, 100 = compra fuerte). La forma comunica el consenso de un vistazo:
 * un polígono amplio y regular = acuerdo alcista; pequeño = bajista; irregular =
 * señales mixtas. Más legible que la lista para captar el sentimiento global.
 */

import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip,
} from 'recharts'
import type { SignalIndicator } from '@/services/analysisService'

const BULLISHNESS: Record<string, number> = {
  COMPRA_FUERTE: 100,
  COMPRA: 72,
  NEUTRAL: 50,
  VENTA: 28,
  VENTA_FUERTE: 0,
}

export default function IndicatorsRadar({ indicators }: Readonly<{ indicators: SignalIndicator[] }>) {
  if (indicators.length < 3) return null
  const data = indicators.map((ind) => ({
    indicator: ind.name,
    value: BULLISHNESS[ind.signal] ?? 50,
    signal: ind.signal,
  }))
  const mean = data.reduce((s, d) => s + d.value, 0) / data.length
  const tone = mean >= 60 ? '#22c55e' : mean <= 40 ? '#ef4444' : '#eab308'

  return (
    <div className="bg-slate-900/40 rounded-xl border border-slate-700/60 p-3">
      <h4 className="text-xs font-semibold text-slate-300 mb-1 px-1">Consenso de indicadores</h4>
      <ResponsiveContainer width="100%" height={240}>
        <RadarChart data={data} outerRadius="72%">
          <PolarGrid stroke="#334155" />
          <PolarAngleAxis dataKey="indicator" tick={{ fill: '#94a3b8', fontSize: 10 }} />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar dataKey="value" stroke={tone} fill={tone} fillOpacity={0.35} />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
            formatter={(v) => [`${typeof v === 'number' ? v.toFixed(0) : v}/100`, 'alcismo']}
          />
        </RadarChart>
      </ResponsiveContainer>
      <p className="text-[10px] text-slate-500 text-center">0 = venta fuerte · 50 = neutral · 100 = compra fuerte</p>
    </div>
  )
}
