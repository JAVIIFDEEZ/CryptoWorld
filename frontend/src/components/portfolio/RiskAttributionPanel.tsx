/**
 * RiskAttributionPanel.tsx — Atribución del riesgo del libro.
 *
 * Muestra (1) el reparto del riesgo de cola (CVaR 95%) por posición mediante
 * descomposición de Euler — las contribuciones suman el total — y (2) la
 * separación sistemática (beta al mercado, BTC) vs idiosincrásica. Se monta
 * dentro del panel de riesgo; no pinta nada si no hay histórico suficiente.
 */

import { useEffect, useState } from 'react'
import { portfolioService, type RiskAttribution } from '../../services/portfolioService'

function usd(n: number | undefined | null): string {
  if (n == null) return '—'
  return `$${Math.abs(n).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
}

export default function RiskAttributionPanel() {
  const [data, setData] = useState<RiskAttribution | null>(null)

  useEffect(() => {
    let cancelled = false
    portfolioService.getRiskAttribution()
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { /* best-effort */ })
    return () => { cancelled = true }
  }, [])

  if (!data || data.status !== 'OK') return null
  const comps = data.components?.components ?? []
  const factor = data.factor
  const maxComp = Math.max(...comps.map((c) => Math.abs(c.component_usd)), 1)

  return (
    <div className="mt-6 pt-5 border-t border-slate-700/60">
      <h3 className="text-sm font-semibold text-slate-300 mb-1">Atribución del riesgo</h3>
      <p className="text-[11px] text-slate-500 mb-3">
        Reparto del riesgo de cola (CVaR 95%) por posición — las contribuciones
        suman el total, así que se ve <em>quién aporta</em> el riesgo, no solo quién es grande.
      </p>

      {/* Componentes */}
      <div className="space-y-1.5">
        {comps.slice(0, 8).map((c) => (
          <div key={c.symbol} className="flex items-center gap-2">
            <span className="font-mono text-xs text-slate-300 w-14 shrink-0">{c.symbol}</span>
            <div className="flex-1 h-4 bg-slate-800 rounded overflow-hidden">
              <div
                className={`h-full ${c.component_usd >= 0 ? 'bg-red-500/60' : 'bg-emerald-500/50'}`}
                style={{ width: `${(Math.abs(c.component_usd) / maxComp) * 100}%` }}
              />
            </div>
            <span className="font-mono text-[11px] text-slate-400 w-24 text-right shrink-0">
              {usd(c.component_usd)} · {c.pct.toFixed(0)}%
            </span>
          </div>
        ))}
      </div>

      {/* Factor de mercado */}
      {factor?.status === 'OK' && (
        <div className="mt-4">
          <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
            <span>Sistemática (mercado) vs idiosincrásica</span>
            <span className="font-mono">β {factor.beta_usd?.toLocaleString('en-US', { maximumFractionDigits: 0 })} · R² {factor.r_squared}</span>
          </div>
          <div className="flex h-5 rounded overflow-hidden text-[10px] font-medium">
            <div
              className="bg-blue-600/70 flex items-center justify-center text-blue-50"
              style={{ width: `${factor.systematic_pct ?? 0}%` }}
            >
              {(factor.systematic_pct ?? 0) >= 12 ? `${(factor.systematic_pct ?? 0).toFixed(0)}%` : ''}
            </div>
            <div
              className="bg-slate-600/70 flex items-center justify-center text-slate-100"
              style={{ width: `${factor.idiosyncratic_pct ?? 0}%` }}
            >
              {(factor.idiosyncratic_pct ?? 0) >= 12 ? `${(factor.idiosyncratic_pct ?? 0).toFixed(0)}%` : ''}
            </div>
          </div>
          <div className="flex items-center gap-3 mt-1 text-[10px] text-slate-500">
            <span><span className="inline-block w-2 h-2 rounded-sm bg-blue-600/70 mr-1" />sistemática</span>
            <span><span className="inline-block w-2 h-2 rounded-sm bg-slate-600/70 mr-1" />idiosincrásica</span>
          </div>
        </div>
      )}
    </div>
  )
}
