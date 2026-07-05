/**
 * components/analysis/PredictionMonitoringPanel.tsx — Monitorización de drift.
 *
 * Compara lo que el modelo PROMETÍA (precisión out-of-sample registrada) con lo
 * que de verdad ha LOGRADO en vivo, y dibuja la precisión realizada en el tiempo
 * para detectar degradación (concept drift). Una brecha negativa sostenida es la
 * señal canónica para reentrenar/reoptimizar; aquí se traduce en una insignia
 * accionable (estable / vigilancia / drift) y una serie temporal.
 */

import { useEffect, useState } from 'react'
import {
  Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import { analysisService, type PredictionMonitoring } from '@/services/analysisService'

const STATUS_STYLE: Record<PredictionMonitoring['status'], { chip: string; label: string }> = {
  ok: { chip: 'bg-green-500/15 text-green-300 border-green-500/30', label: '● Estable' },
  watch: { chip: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30', label: '● Vigilancia' },
  drift: { chip: 'bg-red-500/15 text-red-300 border-red-500/30', label: '● Drift detectado' },
  insufficient: { chip: 'bg-slate-700/40 text-slate-400 border-slate-600/40', label: '○ Sin muestra' },
}

export default function PredictionMonitoringPanel() {
  const [mon, setMon] = useState<PredictionMonitoring | null>(null)
  useEffect(() => {
    analysisService.getPredictionMonitoring().then(setMon).catch(() => { /* sin datos */ })
  }, [])

  // Sin nada resuelto todavía: no abrumamos con un panel vacío.
  if (!mon || mon.n_resolved === 0) return null

  const s = STATUS_STYLE[mon.status]
  const expected = mon.expected_accuracy != null ? mon.expected_accuracy * 100 : null
  const realized = mon.realized_accuracy != null ? mon.realized_accuracy * 100 : null
  const gapPct = mon.gap != null ? mon.gap * 100 : null
  const chart = mon.series.map((b, i) => ({ idx: i + 1, accuracy: +(b.accuracy * 100).toFixed(1), n: b.n }))

  return (
    <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-3">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <h4 className="text-xs font-semibold text-slate-300">Monitorización del modelo (drift)</h4>
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${s.chip}`}>{s.label}</span>
      </div>

      <div className="grid grid-cols-3 gap-2 mb-2">
        <div className="bg-slate-800/50 rounded-md p-2">
          <p className="text-[10px] text-slate-500 uppercase">Prometida (OOS)</p>
          <p className="text-sm font-bold font-mono text-slate-300">{expected != null ? `${expected.toFixed(1)}%` : '—'}</p>
        </div>
        <div className="bg-slate-800/50 rounded-md p-2">
          <p className="text-[10px] text-slate-500 uppercase">Realizada (vivo)</p>
          <p className="text-sm font-bold font-mono text-white">{realized != null ? `${realized.toFixed(1)}%` : '—'}</p>
        </div>
        <div className="bg-slate-800/50 rounded-md p-2">
          <p className="text-[10px] text-slate-500 uppercase">Brecha</p>
          <p className={`text-sm font-bold font-mono ${(gapPct ?? 0) >= -8 ? 'text-green-400' : (gapPct ?? 0) >= -15 ? 'text-yellow-400' : 'text-red-400'}`}>
            {gapPct != null ? `${gapPct >= 0 ? '+' : ''}${gapPct.toFixed(1)}%` : '—'}
          </p>
        </div>
      </div>

      {chart.length >= 2 && (
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={chart} margin={{ top: 5, right: 8, left: -20, bottom: 0 }}>
            <XAxis dataKey="idx" tick={{ fill: '#64748b', fontSize: 9 }} axisLine={{ stroke: '#334155' }} tickLine={false} />
            <YAxis domain={[0, 100]} tick={{ fill: '#64748b', fontSize: 9 }} axisLine={false} tickLine={false} />
            {expected != null && (
              <ReferenceLine y={expected} stroke="#38bdf8" strokeDasharray="4 4" strokeWidth={1} />
            )}
            <ReferenceLine y={50} stroke="#475569" strokeDasharray="2 2" strokeWidth={1} />
            <Tooltip
              contentStyle={{ background: 'rgb(var(--c-slate-900))', border: '1px solid rgb(var(--c-slate-700))', borderRadius: 8, fontSize: 11 }}
              labelFormatter={(l) => `Ventana ${l}`}
              formatter={(v, _n, item) => [`${typeof v === 'number' ? v.toFixed(1) : v}% (${item?.payload?.n} pred.)`, 'precisión']}
            />
            <Line type="monotone" dataKey="accuracy" stroke="#22c55e" strokeWidth={2} dot={{ r: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      )}

      <p className="text-[11px] text-slate-400 mt-1">{mon.message}</p>

      {Object.keys(mon.by_asset).length > 1 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {Object.entries(mon.by_asset).slice(0, 6).map(([sym, a]) => (
            <span key={sym} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
              {sym}: {(a.accuracy * 100).toFixed(0)}% <span className="text-slate-500">({a.n})</span>
            </span>
          ))}
        </div>
      )}
      <p className="text-[10px] text-slate-600 mt-2">
        Línea azul = precisión prometida fuera de muestra; verde = precisión real por ventanas de resolución.
        Si la real cae sostenidamente bajo la prometida, conviene reoptimizar.
      </p>
    </div>
  )
}
