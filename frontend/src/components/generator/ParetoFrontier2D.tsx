/**
 * components/generator/ParetoFrontier2D.tsx — Frontera de Pareto (dispersión 2D).
 *
 * Solo el gráfico (sin tarjeta): lo envuelve Viz3DSwitch. X = drawdown máximo,
 * Y = Sharpe OOS, color/tamaño = sobreajuste.
 */

import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import type { ParetoPoint } from '@/services/strategyGeneratorService'

export function gapColor(gap: number): string {
  const t = Math.max(0, Math.min(1, gap / 1.5))
  const r = Math.round(52 + t * 200)
  const g = Math.round(211 - t * 130)
  return `rgb(${r}, ${g}, 110)`
}

export default function ParetoFrontier2D({ points }: Readonly<{ points: ParetoPoint[] }>) {
  if (!points.length) return <div className="text-slate-500 text-sm text-center py-16">Sin frontera que mostrar.</div>
  const data = points.map((p) => ({ x: p.max_drawdown_pct, y: p.oos_sharpe, z: p.overfit_gap, desc: p.description }))
  return (
    <div className="rounded-xl border border-slate-700/70 bg-slate-900/40 p-3" style={{ height: 360 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 12, right: 20, left: 0, bottom: 16 }}>
          <CartesianGrid stroke="#1e293b" />
          <XAxis type="number" dataKey="x" name="Max drawdown" unit="%" tick={{ fill: '#64748b', fontSize: 10 }}
            label={{ value: 'Max drawdown (%) — menos es mejor →', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 11 }} />
          <YAxis type="number" dataKey="y" name="Sharpe OOS" tick={{ fill: '#64748b', fontSize: 10 }}
            label={{ value: 'Sharpe OOS ↑', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }} />
          <ZAxis type="number" dataKey="z" range={[80, 320]} name="Sobreajuste" />
          <Tooltip cursor={{ strokeDasharray: '3 3' }}
            contentStyle={{ background: 'rgb(var(--c-slate-900))', border: '1px solid rgb(var(--c-slate-700))', borderRadius: 8, fontSize: 11 }}
            formatter={(v, n) => [typeof v === 'number' ? v.toFixed(2) : String(v), n]} />
          <Scatter data={data}>
            {data.map((d, i) => <Cell key={i} fill={gapColor(d.z)} />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <p className="text-[10px] text-slate-500 text-center">Color/tamaño = sobreajuste (verde bajo · rojo alto)</p>
    </div>
  )
}
