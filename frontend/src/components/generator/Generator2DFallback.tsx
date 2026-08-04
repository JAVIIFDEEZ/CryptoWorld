/**
 * components/generator/Generator2DFallback.tsx — Fallback 2D sin WebGL.
 *
 * Equivalentes en recharts (ya en el bundle) de las tres vistas 3D, para
 * navegadores sin WebGL. Mantienen la misma información: dispersión de robustez,
 * evolución del fitness y composición de la estrategia ganadora.
 */

import {
  ScatterChart, Scatter, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ZAxis, Cell,
} from 'recharts'
import { conditionLabel } from '@/services/strategyGeneratorService'
import type { Candidate, GenerationHistoryPoint, StrategySpec, SpecCondition } from '@/services/strategyGeneratorService'

const FRAME = 'rounded-xl border border-slate-700/70 bg-slate-900/50 p-3'

export function Universe2D({ candidates }: Readonly<{ candidates: Candidate[] }>) {
  const data = candidates.map((c) => ({
    x: c.wf_efficiency ?? 0,
    y: c.oos_sharpe ?? 0,
    z: 1 - (c.pbo ?? 1),
    passed: c.passed_gating,
    desc: c.description,
  }))
  return (
    <div className={FRAME}>
      <ResponsiveContainer width="100%" height={380}>
        <ScatterChart margin={{ top: 10, right: 16, left: 0, bottom: 16 }}>
          <CartesianGrid stroke="#1e293b" />
          <XAxis type="number" dataKey="x" name="Eficiencia WF" tick={{ fill: '#64748b', fontSize: 10 }}
            label={{ value: 'Eficiencia WF', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 11 }} />
          <YAxis type="number" dataKey="y" name="Sharpe OOS" tick={{ fill: '#64748b', fontSize: 10 }}
            label={{ value: 'Sharpe OOS', angle: -90, position: 'insideLeft', fill: '#64748b', fontSize: 11 }} />
          <ZAxis type="number" dataKey="z" range={[40, 360]} name="Robustez" />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            contentStyle={{ background: 'rgb(var(--c-slate-900))', border: '1px solid rgb(var(--c-slate-700))', borderRadius: 8, fontSize: 11 }}
            formatter={(v) => (typeof v === 'number' ? v.toFixed(2) : String(v))}
          />
          <Scatter data={data}>
            {data.map((d, i) => <Cell key={i} fill={d.passed ? '#34d399' : '#475569'} />)}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <p className="text-[10px] text-slate-500 text-center">Tamaño = robustez (1−PBO) · verde = supera el gating</p>
    </div>
  )
}

export function Landscape2D({ history }: Readonly<{ history: GenerationHistoryPoint[] }>) {
  return (
    <div className={FRAME}>
      <ResponsiveContainer width="100%" height={380}>
        <LineChart data={history} margin={{ top: 10, right: 16, left: 0, bottom: 16 }}>
          <CartesianGrid stroke="#1e293b" />
          <XAxis dataKey="generation" tick={{ fill: '#64748b', fontSize: 10 }}
            label={{ value: 'Generación', position: 'insideBottom', offset: -8, fill: '#64748b', fontSize: 11 }} />
          <YAxis tick={{ fill: '#64748b', fontSize: 10 }} />
          <Tooltip contentStyle={{ background: 'rgb(var(--c-slate-900))', border: '1px solid rgb(var(--c-slate-700))', borderRadius: 8, fontSize: 11 }} />
          <Line type="monotone" dataKey="best" stroke="#34d399" strokeWidth={2} dot={false} name="Mejor" />
          <Line type="monotone" dataKey="mean" stroke="#60a5fa" strokeWidth={1.5} strokeDasharray="4 3" dot={false} name="Medio" />
        </LineChart>
      </ResponsiveContainer>
      <p className="text-[10px] text-slate-500 text-center">Fitness mejor (verde) y medio (azul) por generación</p>
    </div>
  )
}

// La etiqueta vive en el servicio porque la comparten esta vista y la hélice
// 3D: duplicarla fue lo que dejó fuera las condiciones de estado, pendiente y
// patrón, que aquí salían como «undefined ↗ undefined».
const condLabel = conditionLabel

export function Dna2D({ spec }: Readonly<{ spec: StrategySpec | null }>) {
  if (!spec) return <div className="text-slate-500 text-sm text-center py-16">Sin estrategia ganadora.</div>
  const block = (title: string, color: string, conds: SpecCondition[], combine: string) => (
    <div className={FRAME}>
      <p className="text-xs font-semibold mb-2" style={{ color }}>{title}</p>
      <div className="space-y-1.5">
        {conds.map((c, i) => (
          <div key={i} className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full" style={{ background: color }} />
            <span className="text-xs text-slate-200 font-mono">{condLabel(c)}</span>
            {i < conds.length - 1 && <span className="text-[10px] text-slate-500 ml-auto">{combine}</span>}
          </div>
        ))}
      </div>
    </div>
  )
  return (
    <div className="grid sm:grid-cols-2 gap-3">
      {block('Entrada', '#60a5fa', spec.entry.conditions, spec.entry.combine)}
      {block('Salida', '#fbbf24', spec.exit.conditions, spec.exit.combine)}
    </div>
  )
}
