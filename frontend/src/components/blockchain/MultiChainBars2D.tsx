/**
 * components/blockchain/MultiChainBars2D.tsx — Comparador multi-cadena 2D.
 *
 * Barras agrupadas (recharts): una cadena por grupo, una barra por métrica
 * normalizada. Fallback sin WebGL del comparador 3D.
 */

import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { METRIC_PALETTE, type CompareData } from './blockchainViz'

export default function MultiChainBars2D({ data }: Readonly<{ data: CompareData }>) {
  if (data.chains.length < 2 || data.metrics.length === 0) {
    return <div className="text-slate-500 text-sm text-center py-16">Datos insuficientes para comparar cadenas.</div>
  }
  const rows = data.chains.map((chain, i) => {
    const row: Record<string, number | string> = { chain }
    data.metrics.forEach((m, j) => { row[m.key] = Number(((data.norm[i][j] ?? 0) * 100).toFixed(1)) })
    return row
  })
  return (
    <div className="rounded-xl border border-slate-700/70 bg-slate-900/40 p-3" style={{ height: 440 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 10, right: 16, left: 0, bottom: 4 }}>
          <CartesianGrid stroke="#1e293b" />
          <XAxis dataKey="chain" tick={{ fill: '#94a3b8', fontSize: 11 }} />
          <YAxis tick={{ fill: '#64748b', fontSize: 10 }} unit="%" domain={[0, 100]} />
          <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {data.metrics.map((m, j) => (
            <Bar key={m.key} dataKey={m.key} name={m.label} fill={METRIC_PALETTE[j % METRIC_PALETTE.length]} radius={[2, 2, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
      <p className="text-[10px] text-slate-500 text-center mt-1">Valores normalizados por métrica (0–100% del máximo entre cadenas)</p>
    </div>
  )
}
