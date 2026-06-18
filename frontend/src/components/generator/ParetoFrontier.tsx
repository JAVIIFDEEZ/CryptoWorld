/**
 * components/generator/ParetoFrontier.tsx — Frontera de Pareto (NSGA-II).
 *
 * Dispersión del compromiso retorno/riesgo: cada estrategia no dominada es un
 * punto (X = drawdown máximo, Y = Sharpe OOS); el color codifica el sobreajuste
 * (verde = bajo). El usuario ve el trade-off y elige su punto preferido.
 */

import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import type { ParetoPoint } from '@/services/strategyGeneratorService'

function gapColor(gap: number): string {
  // sobreajuste bajo (0) → verde; alto (≥1.5) → rojo
  const t = Math.max(0, Math.min(1, gap / 1.5))
  const r = Math.round(52 + t * 200)
  const g = Math.round(211 - t * 130)
  return `rgb(${r}, ${g}, 110)`
}

export default function ParetoFrontier({ points }: Readonly<{ points: ParetoPoint[] }>) {
  if (!points.length) return null
  const data = points.map((p) => ({
    x: p.max_drawdown_pct,
    y: p.oos_sharpe,
    z: p.overfit_gap,
    desc: p.description,
  }))

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-base">⚖️</span>
        <h3 className="text-sm font-semibold text-white">Frontera de Pareto</h3>
        <span className="text-[11px] text-slate-500">{points.length} estrategias no dominadas · compromiso retorno/riesgo</span>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 12, right: 20, left: 0, bottom: 16 }}>
          <CartesianGrid stroke="#1e293b" />
          <XAxis type="number" dataKey="x" name="Max drawdown" unit="%" tick={{ fill: '#64748b', fontSize: 10 }}
            label={{ value: 'Max drawdown (%) — menos es mejor →', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 11 }} />
          <YAxis type="number" dataKey="y" name="Sharpe OOS" tick={{ fill: '#64748b', fontSize: 10 }}
            label={{ value: 'Sharpe OOS ↑', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }} />
          <ZAxis type="number" dataKey="z" range={[80, 320]} name="Sobreajuste" />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
            formatter={(v, n) => [typeof v === 'number' ? v.toFixed(2) : String(v), n]}
          />
          <Scatter data={data}>
            {data.map((d, i) => <Cell key={i} fill={gapColor(d.z)} />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <p className="text-[10px] text-slate-500 text-center">Color = sobreajuste (verde bajo · rojo alto) · tamaño proporcional al sobreajuste</p>
    </div>
  )
}
