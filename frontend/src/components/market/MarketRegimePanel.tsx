/**
 * MarketRegimePanel.tsx — Correlaciones cross-asset y régimen de mercado.
 *
 * Mapa de calor de correlación de la cesta (top por capitalización) + etiqueta
 * de régimen (risk-on / risk-off / rotación / neutral) con la correlación
 * media, la tendencia de BTC y la amplitud. No pinta nada sin datos.
 */

import { useEffect, useState } from 'react'
import { regimeService, type MarketRegime } from '../../services/regimeService'

const REGIME_STYLE: Record<string, string> = {
  RISK_ON: 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300',
  RISK_OFF: 'bg-red-500/15 border-red-500/40 text-red-300',
  ROTACION: 'bg-blue-500/15 border-blue-500/40 text-blue-300',
  NEUTRAL: 'bg-slate-600/20 border-slate-500/40 text-slate-300',
  UNKNOWN: 'bg-slate-700/30 border-slate-600 text-slate-400',
}

// Correlación → color diverging: +1 azul, 0 gris, -1 ámbar.
function cellColor(c: number): string {
  if (c >= 0) {
    const a = Math.min(1, c)
    return `rgba(59, 130, 246, ${0.15 + a * 0.6})`
  }
  const a = Math.min(1, -c)
  return `rgba(245, 158, 11, ${0.15 + a * 0.6})`
}

export default function MarketRegimePanel() {
  const [data, setData] = useState<MarketRegime | null>(null)

  useEffect(() => {
    let cancelled = false
    regimeService.get()
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { /* best-effort */ })
    return () => { cancelled = true }
  }, [])

  if (!data || data.status !== 'OK' || !data.correlations) return null
  const { correlations: cor, regime } = data
  const syms = cor.symbols

  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h3 className="text-sm font-semibold text-white">Régimen de mercado y correlaciones</h3>
        {regime && (
          <span className={`text-xs px-2.5 py-1 rounded-full border font-medium ${REGIME_STYLE[regime.regime] ?? REGIME_STYLE.UNKNOWN}`}>
            {regime.label}
          </span>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4 text-center">
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Correlación media</p>
          <p className="text-lg font-bold font-mono text-white">{cor.avg_correlation?.toFixed(2)}</p>
          <p className="text-[10px] text-slate-500">{regime?.correlation_state}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Tendencia BTC</p>
          <p className={`text-lg font-bold font-mono ${(data.btc_trend_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {(data.btc_trend_pct ?? 0) >= 0 ? '+' : ''}{(data.btc_trend_pct ?? 0).toFixed(1)}%
          </p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Amplitud</p>
          <p className="text-lg font-bold font-mono text-white">{(data.breadth_pct ?? 0).toFixed(0)}%</p>
          <p className="text-[10px] text-slate-500">sobre su media</p>
        </div>
      </div>

      {/* Mapa de calor */}
      <div className="overflow-x-auto">
        <table className="border-collapse text-[10px]">
          <thead>
            <tr>
              <th className="p-1"></th>
              {syms.map((s) => (
                <th key={s} className="p-1 font-mono text-slate-400 font-normal">{s}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {syms.map((s, i) => (
              <tr key={s}>
                <td className="p-1 font-mono text-slate-400 text-right pr-2">{s}</td>
                {cor.matrix[i].map((c, j) => (
                  <td
                    key={j}
                    className="w-8 h-8 text-center font-mono text-slate-100"
                    style={{ backgroundColor: i === j ? 'rgba(100,116,139,0.25)' : cellColor(c) }}
                    title={`${syms[i]}–${syms[j]}: ${c.toFixed(2)}`}
                  >
                    {c.toFixed(1)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.note && <p className="text-[10px] text-slate-600 mt-3">{data.note}</p>}
    </div>
  )
}
