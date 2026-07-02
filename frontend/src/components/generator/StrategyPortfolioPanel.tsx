/**
 * components/generator/StrategyPortfolioPanel.tsx — Cartera de estrategias.
 *
 * Analiza cómo DIVERSIFICAN las campeonas juntas: matriz de correlación entre
 * sus retornos diarios (verde = descorrelacionadas, rojo = redundantes), equity
 * conjunta equiponderada y métricas de la cartera. La lección profesional:
 * combinar estrategias poco correlacionadas reduce el drawdown conjunto.
 */

import { useEffect, useState } from 'react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  strategyGeneratorService,
  type StrategyPortfolio,
} from '@/services/strategyGeneratorService'

function corrColor(v: number | null): string {
  if (v === null) return '#334155'
  // −1 (verde: diversifica) → 0 (gris) → +1 (rojo: redundante)
  if (v >= 0) {
    const t = Math.min(v, 1)
    return `rgba(239, 68, 68, ${0.15 + 0.6 * t})`
  }
  const t = Math.min(-v, 1)
  return `rgba(34, 197, 94, ${0.15 + 0.6 * t})`
}

export default function StrategyPortfolioPanel({ refreshKey = 0 }: Readonly<{ refreshKey?: number }>) {
  const [data, setData] = useState<StrategyPortfolio | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    strategyGeneratorService.getStrategyPortfolio()
      .then((d) => {
        if (d.error) { setData(null); setMessage(d.error) }
        else { setData(d); setMessage(null) }
      })
      .catch(() => { setData(null); setMessage('No se pudo calcular la cartera.') })
      .finally(() => setLoading(false))
  }, [refreshKey])

  if (loading) return null
  if (!data) {
    return message ? (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 text-sm text-slate-500">
        <span className="text-slate-300 font-medium">Cartera de estrategias:</span> {message}
      </div>
    ) : null
  }

  const avg = data.avg_correlation
  const avgTone = avg === null ? 'text-slate-400' : avg < 0.3 ? 'text-green-400' : avg < 0.6 ? 'text-yellow-400' : 'text-red-400'
  const port = data.portfolio
  const equityUp = port.total_return_pct >= 0

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4 mb-6">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-purple-400">◈</span>
        <h3 className="text-sm font-semibold text-white">Cartera de estrategias (diversificación)</h3>
        <span className="ml-auto text-[10px] text-slate-500">{data.common_days} días comunes</span>
      </div>
      <p className="text-[11px] text-slate-500 mb-4">
        Correlación entre los retornos diarios de las campeonas y equity conjunta equiponderada.
        Verde = diversifican; rojo = redundantes.
      </p>

      <div className="grid lg:grid-cols-2 gap-4">
        {/* Matriz de correlación */}
        <div>
          <div className="flex items-baseline justify-between mb-2">
            <p className="text-[10px] text-slate-500 uppercase">Matriz de correlación</p>
            <p className="text-[11px]">
              <span className="text-slate-500">media </span>
              <span className={`font-mono font-bold ${avgTone}`}>{avg !== null ? avg.toFixed(2) : '—'}</span>
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="text-[10px]">
              <thead>
                <tr>
                  <th></th>
                  {data.labels.map((l) => (
                    <th key={l} className="px-1 pb-1 text-slate-400 font-medium whitespace-nowrap">{l}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.labels.map((row, i) => (
                  <tr key={row}>
                    <td className="pr-2 py-0.5 text-slate-400 whitespace-nowrap">{row}</td>
                    {data.labels.map((col, j) => {
                      const v = data.correlation_matrix[i][j]
                      return (
                        <td key={col} className="p-0.5">
                          <div
                            className="w-12 h-8 rounded flex items-center justify-center font-mono text-slate-100"
                            style={{ backgroundColor: corrColor(v) }}
                            title={`${row} × ${col}`}
                          >
                            {v !== null ? v.toFixed(2) : '—'}
                          </div>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Equity conjunta + métricas */}
        <div>
          <div className="grid grid-cols-3 gap-2 mb-2">
            <div className="bg-slate-900/40 rounded-lg p-2">
              <p className="text-[9px] text-slate-500 uppercase">Retorno</p>
              <p className={`text-sm font-bold font-mono ${equityUp ? 'text-green-400' : 'text-red-400'}`}>
                {port.total_return_pct >= 0 ? '+' : ''}{port.total_return_pct.toFixed(2)}%
              </p>
            </div>
            <div className="bg-slate-900/40 rounded-lg p-2">
              <p className="text-[9px] text-slate-500 uppercase">Max DD</p>
              <p className="text-sm font-bold font-mono text-amber-300">−{port.max_drawdown_pct.toFixed(2)}%</p>
            </div>
            <div className="bg-slate-900/40 rounded-lg p-2">
              <p className="text-[9px] text-slate-500 uppercase">Sharpe</p>
              <p className="text-sm font-bold font-mono text-slate-200">{port.sharpe.toFixed(2)}</p>
            </div>
          </div>
          {port.equity.length >= 2 && (
            <ResponsiveContainer width="100%" height={140}>
              <AreaChart data={port.equity} margin={{ top: 4, right: 4, left: -16, bottom: 0 }}>
                <defs>
                  <linearGradient id="portfill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={equityUp ? '#22c55e' : '#ef4444'} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={equityUp ? '#22c55e' : '#ef4444'} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} axisLine={{ stroke: '#334155' }} tickLine={false} minTickGap={30} />
                <YAxis domain={['dataMin', 'dataMax']} tick={{ fill: '#64748b', fontSize: 9 }} axisLine={false} tickLine={false} width={44} />
                <Tooltip
                  contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
                  formatter={(v) => [typeof v === 'number' ? v.toFixed(2) : v, 'equity (base 100)']}
                />
                <Area type="monotone" dataKey="value" stroke={equityUp ? '#22c55e' : '#ef4444'} strokeWidth={1.5} fill="url(#portfill)" />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Miembros */}
      <div className="flex flex-wrap gap-1.5 mt-3">
        {data.members.map((m) => (
          <span key={m.strategy_id} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-900 border border-slate-700 text-slate-300" title={m.name}>
            {m.label}
            {m.window_return_pct != null && (
              <span className={`ml-1 font-mono ${m.window_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {m.window_return_pct >= 0 ? '+' : ''}{m.window_return_pct.toFixed(1)}%
              </span>
            )}
          </span>
        ))}
      </div>
      <p className="text-[10px] text-slate-600 mt-2">{data.note}</p>
    </div>
  )
}
