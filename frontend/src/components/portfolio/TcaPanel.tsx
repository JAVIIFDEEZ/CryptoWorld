/**
 * TcaPanel.tsx — Analítica de coste de ejecución (TCA).
 *
 * Calidad de la ejecución real: slippage medio (bps, con signo de coste),
 * coste total, fill rate y desglose por símbolo, sobre la auditoría de órdenes
 * reales. No pinta nada si aún no hay ejecuciones.
 */

import { useEffect, useState } from 'react'
import { tradingService, type ExecutionTca } from '@/services/tradingService'

function usd(n: number | undefined | null): string {
  if (n == null) return '—'
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`
}

// Coste positivo = peor ejecución → rojo; negativo (mejor) → verde.
function slipClass(bps: number | undefined | null): string {
  if (bps == null) return 'text-slate-300'
  if (bps > 2) return 'text-red-300'
  if (bps < 0) return 'text-emerald-300'
  return 'text-amber-300'
}

export default function TcaPanel() {
  const [data, setData] = useState<ExecutionTca | null>(null)

  useEffect(() => {
    let cancelled = false
    tradingService.getTca()
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { /* best-effort */ })
    return () => { cancelled = true }
  }, [])

  if (!data || data.status !== 'OK') return null

  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-1">Coste de ejecución (TCA)</h3>
      <p className="text-[11px] text-slate-500 mb-3">
        Calidad de la ejecución real frente al precio de la señal — slippage con
        signo de coste ponderado por nocional.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center mb-4">
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Slippage medio</p>
          <p className={`text-lg font-bold font-mono ${slipClass(data.avg_slippage_bps)}`}>
            {data.avg_slippage_bps?.toFixed(2)} bps
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Coste total</p>
          <p className="text-lg font-bold font-mono text-white">{usd(data.total_cost_usd)}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Fill rate</p>
          <p className="text-lg font-bold font-mono text-white">
            {data.fill_rate_pct != null ? `${data.fill_rate_pct.toFixed(0)}%` : '—'}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Ejecuciones</p>
          <p className="text-lg font-bold font-mono text-white">{data.fills}</p>
        </div>
      </div>

      {(data.by_symbol?.length ?? 0) > 0 && (
        <div className="space-y-1">
          {data.by_symbol!.slice(0, 6).map((b) => (
            <div key={b.symbol} className="flex items-center justify-between text-xs">
              <span className="font-mono text-slate-300">{b.symbol}</span>
              <span className="text-slate-500">{b.fills} fills · {usd(b.notional_usd)}</span>
              <span className={`font-mono ${slipClass(b.avg_slippage_bps)}`}>
                {b.avg_slippage_bps.toFixed(1)} bps
              </span>
            </div>
          ))}
        </div>
      )}

      {data.note && <p className="text-[10px] text-slate-600 mt-3">{data.note}</p>}
    </div>
  )
}
