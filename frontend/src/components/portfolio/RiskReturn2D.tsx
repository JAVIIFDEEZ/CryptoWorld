/**
 * components/portfolio/RiskReturn2D.tsx — Riesgo / retorno 2D (recharts).
 *
 * Dispersión X=volatilidad, Y=retorno, tamaño=peso. Fallback sin WebGL.
 */

import {
  ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer, Cell,
} from 'recharts'
import type { RiskReturnPoint } from './portfolioViz'

export default function RiskReturn2D({ points }: Readonly<{ points: RiskReturnPoint[] }>) {
  if (!points.length) {
    return <div className="text-slate-500 text-sm text-center py-16">Sin posiciones con histórico suficiente.</div>
  }
  const data = points.map((p) => ({ x: p.vol, y: p.ret, z: p.weight * 100, symbol: p.symbol }))
  return (
    <div className="rounded-xl border border-slate-700/70 bg-slate-900/40 p-3" style={{ height: 420 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 12, right: 18, left: 0, bottom: 16 }}>
          <CartesianGrid stroke="#1e293b" />
          <XAxis type="number" dataKey="x" name="Volatilidad" unit="%" tick={{ fill: '#64748b', fontSize: 10 }}
            label={{ value: 'Volatilidad 7d (%)', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 11 }} />
          <YAxis type="number" dataKey="y" name="Retorno" unit="%" tick={{ fill: '#64748b', fontSize: 10 }}
            label={{ value: 'Retorno 7d (%)', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }} />
          <ZAxis type="number" dataKey="z" range={[60, 500]} name="Peso" unit="%" />
          <ReferenceLine y={0} stroke="#475569" strokeDasharray="3 3" />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            contentStyle={{ background: 'rgb(var(--c-slate-900))', border: '1px solid rgb(var(--c-slate-700))', borderRadius: 8, fontSize: 11 }}
            formatter={(v) => (typeof v === 'number' ? v.toFixed(1) : String(v))}
          />
          <Scatter data={data}>
            {data.map((d) => <Cell key={d.symbol} fill={d.y >= 0 ? '#34d399' : '#f87171'} />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}
