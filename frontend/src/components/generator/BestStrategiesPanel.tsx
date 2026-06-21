/**
 * components/generator/BestStrategiesPanel.tsx — Campeona por activo.
 *
 * Muestra la mejor estrategia validada de cada activo (por fitness) con su
 * rendimiento en el holdout y, si el usuario la sigue en paper trading, su
 * rentabilidad REAL en vivo. Es el "salón de la fama" que la reoptimización
 * semanal mantiene fresco frente al drift de mercado.
 */

import { useEffect, useState } from 'react'
import { strategyGeneratorService, type BestStrategy } from '@/services/strategyGeneratorService'

function tone(v: number | null | undefined): string {
  if (v == null) return 'text-slate-400'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300'
}

export default function BestStrategiesPanel({ refreshKey = 0 }: Readonly<{ refreshKey?: number }>) {
  const [items, setItems] = useState<BestStrategy[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    strategyGeneratorService.getBestStrategies()
      .then(setItems)
      .catch(() => { /* sin estrategias */ })
      .finally(() => setLoading(false))
  }, [refreshKey])

  if (loading || items.length === 0) return null

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-amber-400">★</span>
        <h3 className="text-sm font-semibold text-white">Mejor estrategia por activo</h3>
        <span className="text-[11px] text-slate-500">campeona actual · reoptimizada semanalmente</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="text-[10px] uppercase text-slate-500 border-b border-slate-700/60">
              <th className="py-1.5 pr-3">Activo</th>
              <th className="py-1.5 pr-3">Estrategia</th>
              <th className="py-1.5 pr-3 text-right">Fitness</th>
              <th className="py-1.5 pr-3 text-right">Holdout</th>
              <th className="py-1.5 pr-3 text-right">Sharpe</th>
              <th className="py-1.5 text-right">En vivo (real)</th>
            </tr>
          </thead>
          <tbody>
            {items.map((s) => (
              <tr key={s.strategy_id} className="border-b border-slate-800 last:border-0">
                <td className="py-2 pr-3">
                  <span className="text-emerald-300 font-semibold">{s.asset_symbol}</span>
                  <span className="text-slate-600 ml-1">{s.interval}</span>
                </td>
                <td className="py-2 pr-3 max-w-[14rem]">
                  <span className="text-slate-300 font-mono line-clamp-1" title={s.name}>{s.name}</span>
                </td>
                <td className="py-2 pr-3 text-right font-mono text-blue-300">{s.fitness?.toFixed(2) ?? '—'}</td>
                <td className={`py-2 pr-3 text-right font-mono ${tone(s.holdout_return_pct)}`}>
                  {s.holdout_return_pct != null ? `${s.holdout_return_pct >= 0 ? '+' : ''}${s.holdout_return_pct.toFixed(1)}%` : '—'}
                </td>
                <td className="py-2 pr-3 text-right font-mono text-slate-300">{s.holdout_sharpe?.toFixed(2) ?? '—'}</td>
                <td className="py-2 text-right">
                  {s.live ? (
                    <span className={`font-mono ${tone(s.live.total_return_pct)}`}>
                      {s.live.total_return_pct >= 0 ? '+' : ''}{s.live.total_return_pct.toFixed(2)}%
                      <span className="text-slate-600 ml-1">({s.live.trades_count} ops)</span>
                    </span>
                  ) : (
                    <span className="text-slate-600">sin seguir</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[10px] text-slate-600 mt-2">
        Fitness y holdout son del backtest; «en vivo» es la rentabilidad real de tu paper trading.
        La reoptimización programada regenera estas estrategias con datos frescos cuando el régimen cambia.
      </p>
    </div>
  )
}
