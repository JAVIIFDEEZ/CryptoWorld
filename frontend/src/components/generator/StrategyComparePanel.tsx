/**
 * components/generator/StrategyComparePanel.tsx — Comparador cara a cara.
 *
 * Pone 2-4 estrategias guardadas lado a lado: equity fresca superpuesta
 * (crecimiento de 1€, comparable entre activos), tabla de métricas con el mejor
 * de cada fila resaltado, correlación entre estrategias y veredictos por
 * dimensión. La pregunta que responde: ¿a cuál le asigno capital?
 */

import { useEffect, useState } from 'react'
import {
  strategyGeneratorService,
  type StrategyComparison,
  type CompareItem,
} from '@/services/strategyGeneratorService'

// Paleta categórica validada (CVD/contraste) — orden fijo, nunca ciclada.
export const SERIES_COLORS = ['#3b82f6', '#d97706', '#8b5cf6', '#ec4899']

// ── Gráfica de equity superpuesta ───────────────────────────────────

const W = 640, H = 200, PAD = { top: 10, right: 78, bottom: 18, left: 42 }

function OverlaidEquity({ items }: Readonly<{ items: CompareItem[] }>) {
  const withEquity = items.filter((it) => it.fresh.available && (it.fresh.equity?.length ?? 0) > 1)
  if (withEquity.length === 0) {
    return <p className="text-xs text-slate-500 py-6 text-center">Sin datos frescos para superponer curvas.</p>
  }
  const all = withEquity.flatMap((it) => it.fresh.equity!)
  const lo = Math.min(...all), hi = Math.max(...all)
  const span = hi - lo || 1
  const maxLen = Math.max(...withEquity.map((it) => it.fresh.equity!.length))
  const x = (i: number, len: number) =>
    PAD.left + ((i / (len - 1)) * (W - PAD.left - PAD.right))
  const y = (v: number) => H - PAD.bottom - ((v - lo) / span) * (H - PAD.top - PAD.bottom)

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Equity comparada (crecimiento de 1€)">
        {/* Línea base 1.0 y rejilla mín/máx recesiva */}
        <line x1={PAD.left} x2={W - PAD.right} y1={y(1)} y2={y(1)} stroke="#475569" strokeWidth={0.8} strokeDasharray="3 3" />
        {[lo, hi].map((v, i) => (
          <text key={i} x={PAD.left - 6} y={y(v) + 3} textAnchor="end" fontSize={9} className="fill-slate-500 font-mono">
            {v.toFixed(2)}
          </text>
        ))}
        {withEquity.map((it, k) => {
          const eq = it.fresh.equity!
          const pts = eq.map((v, i) => `${x(i, eq.length).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
          const color = SERIES_COLORS[k % SERIES_COLORS.length]
          return (
            <g key={it.strategy_id}>
              <polyline points={pts} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
              {/* Etiqueta directa al final de cada serie */}
              <text x={x(eq.length - 1, eq.length) + 6} y={y(eq[eq.length - 1]) + 3}
                    fontSize={9} fill={color} className="font-medium">
                {it.asset_symbol} {eq[eq.length - 1] >= 1 ? '+' : ''}{((eq[eq.length - 1] - 1) * 100).toFixed(0)}%
              </text>
            </g>
          )
        })}
        <text x={PAD.left} y={H - 4} fontSize={9} className="fill-slate-600">ventana reciente · crecimiento de 1€ · {maxLen} puntos</text>
      </svg>
      {/* Leyenda */}
      <div className="flex flex-wrap items-center gap-4 mt-1 text-[10px] text-slate-400">
        {withEquity.map((it, k) => (
          <span key={it.strategy_id} className="flex items-center gap-1.5">
            <span className="inline-block w-4 h-0.5 rounded" style={{ background: SERIES_COLORS[k % SERIES_COLORS.length] }} />
            {it.label}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Tabla de métricas con el mejor de cada fila resaltado ───────────

type MetricRow = {
  label: string
  get: (it: CompareItem) => number | null | undefined
  fmt: (v: number) => string
  higherBetter: boolean
}

const ROWS: MetricRow[] = [
  { label: 'Fitness', get: (i) => i.stored.fitness, fmt: (v) => v.toFixed(3), higherBetter: true },
  { label: 'Sharpe OOS (original)', get: (i) => i.stored.mean_oos_sharpe, fmt: (v) => v.toFixed(2), higherBetter: true },
  { label: 'PBO', get: (i) => i.stored.pbo, fmt: (v) => `${Math.round(v * 100)}%`, higherBetter: false },
  { label: 'Eficiencia WF', get: (i) => i.stored.wf_efficiency, fmt: (v) => v.toFixed(2), higherBetter: true },
  { label: 'Holdout', get: (i) => i.stored.holdout_return_pct, fmt: (v) => `${v >= 0 ? '+' : ''}${v}%`, higherBetter: true },
  { label: 'Multi-activo', get: (i) => i.stored.cross_consistency, fmt: (v) => `${Math.round(v * 100)}%`, higherBetter: true },
  { label: 'Retorno fresco', get: (i) => i.fresh.available ? i.fresh.window_return_pct : null, fmt: (v) => `${v >= 0 ? '+' : ''}${v}%`, higherBetter: true },
  { label: 'Sharpe OOS fresco', get: (i) => i.fresh.available ? i.fresh.oos_sharpe : null, fmt: (v) => v.toFixed(2), higherBetter: true },
]

function MetricsTable({ items }: Readonly<{ items: CompareItem[] }>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="text-[9px] uppercase text-slate-500 border-b border-slate-700">
            <th className="text-left py-1.5 pr-2">Métrica</th>
            {items.map((it, k) => (
              <th key={it.strategy_id} className="text-right py-1.5 px-2 whitespace-nowrap">
                <span className="inline-block w-2 h-2 rounded-full mr-1.5 align-middle"
                      style={{ background: SERIES_COLORS[k % SERIES_COLORS.length] }} />
                {it.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => {
            const values = items.map((it) => row.get(it))
            const defined = values.filter((v): v is number => v != null)
            const best = defined.length > 1
              ? (row.higherBetter ? Math.max(...defined) : Math.min(...defined))
              : null
            return (
              <tr key={row.label} className="border-b border-slate-700/40">
                <td className="py-1.5 pr-2 text-slate-400">{row.label}</td>
                {values.map((v, k) => (
                  <td key={k} className={`py-1.5 px-2 text-right font-mono ${
                    v != null && v === best ? 'text-emerald-300 font-bold' : 'text-slate-300'
                  }`}>
                    {v != null ? row.fmt(v) : '—'}
                    {v != null && v === best && ' ★'}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Panel principal ─────────────────────────────────────────────────

export default function StrategyComparePanel({ ids, onClose }: Readonly<{
  ids: number[]
  onClose: () => void
}>) {
  const [data, setData] = useState<StrategyComparison | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError('')
    strategyGeneratorService.compare(ids)
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setError('No se pudo cargar la comparación.') })
    return () => { cancelled = true }
  }, [ids])

  const v = data?.verdicts

  return (
    <div className="bg-slate-800 rounded-xl border border-blue-500/30 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">
          ⚖ Comparador cara a cara
          <span className="ml-2 text-[10px] font-normal text-slate-500">¿a cuál le asigno capital?</span>
        </h3>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-200 text-sm" aria-label="Cerrar comparador">✕</button>
      </div>

      {error && <p className="text-xs text-red-400 py-4">{error}</p>}
      {!error && !data && <p className="text-xs text-slate-500 py-4">Re-ejecutando estrategias sobre datos actuales…</p>}

      {data && (
        <>
          {/* Veredictos por dimensión */}
          {v && (
            <div className="flex flex-wrap gap-2 text-[10px]">
              {v.best_fitness && <Chip label="Mejor fitness" value={v.best_fitness} cls="text-blue-300 border-blue-500/30 bg-blue-500/10" />}
              {v.best_holdout && <Chip label="Mejor holdout" value={v.best_holdout} cls="text-emerald-300 border-emerald-500/30 bg-emerald-500/10" />}
              {v.best_fresh && <Chip label="Mejor en fresco" value={v.best_fresh} cls="text-cyan-300 border-cyan-500/30 bg-cyan-500/10" />}
              {v.best_generalization && <Chip label="Mejor generalización" value={v.best_generalization} cls="text-purple-300 border-purple-500/30 bg-purple-500/10" />}
              {v.most_diversifying_pair && (
                <Chip label="Pareja más diversificadora"
                      value={`${v.most_diversifying_pair.a} + ${v.most_diversifying_pair.b} (ρ ${v.most_diversifying_pair.corr})`}
                      cls="text-amber-300 border-amber-500/30 bg-amber-500/10" />
              )}
            </div>
          )}

          <OverlaidEquity items={data.items} />
          <MetricsTable items={data.items} />

          {/* Correlación entre estrategias */}
          {data.correlation && (
            <div className="text-[10px] text-slate-400">
              <span className="uppercase text-slate-500">Correlación entre estrategias</span>
              <span className="text-slate-600"> · {data.correlation.common_days} días comunes · </span>
              {data.correlation.labels.map((la, i) =>
                data.correlation!.labels.slice(i + 1).map((lb, jOff) => {
                  const c = data.correlation!.matrix[i][i + 1 + jOff]
                  return (
                    <span key={`${la}-${lb}`} className="mr-3 font-mono">
                      {la}↔{lb}: <span className={c != null && Math.abs(c) < 0.4 ? 'text-emerald-400' : 'text-amber-300'}>
                        {c != null ? c.toFixed(2) : '—'}
                      </span>
                    </span>
                  )
                }))}
            </div>
          )}
          <p className="text-[9px] text-slate-600">{data.note}</p>
        </>
      )}
    </div>
  )
}

function Chip({ label, value, cls }: Readonly<{ label: string; value: string; cls: string }>) {
  return (
    <span className={`px-2 py-0.5 rounded-full border ${cls}`}>
      {label}: <span className="font-semibold">{value}</span>
    </span>
  )
}
