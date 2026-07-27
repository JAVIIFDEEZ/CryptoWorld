/**
 * LeadLagPanel.tsx — Señales lead-lag (quién adelanta a quién).
 *
 * Ranking de liderazgo de la cesta y las relaciones lead-lag más fuertes
 * (líder → seguidor, con el desfase en barras). No pinta nada sin datos.
 */

import { useEffect, useState } from 'react'
import { regimeService, type LeadLag } from '../../services/regimeService'

export default function LeadLagPanel() {
  const [data, setData] = useState<LeadLag | null>(null)

  useEffect(() => {
    let cancelled = false
    regimeService.leadLag()
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { /* best-effort */ })
    return () => { cancelled = true }
  }, [])

  if (!data || data.status !== 'OK' || !(data.pairs?.length)) return null
  const leaders = (data.leaders ?? []).filter((l) => l.leads > 0).slice(0, 5)

  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-1">Señales lead-lag</h3>
      <p className="text-[11px] text-slate-500 mb-3">
        Qué activos anticipan a cuáles — un desfase positivo del líder significa
        que sus retornos adelantan los del seguidor en esas barras.
      </p>

      {leaders.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {leaders.map((l) => (
            <span key={l.symbol} className="text-[11px] px-2 py-0.5 rounded-full bg-blue-500/15 border border-blue-500/30 text-blue-300">
              {l.symbol} lidera {l.leads}
            </span>
          ))}
        </div>
      )}

      <div className="space-y-1">
        {data.pairs!.slice(0, 8).map((p) => (
          <div key={`${p.leader}-${p.follower}`} className="flex items-center justify-between text-xs">
            <span className="font-mono text-slate-300">
              <span className="text-emerald-300">{p.leader}</span>
              {' → '}
              <span className="text-slate-400">{p.follower}</span>
            </span>
            <span className="text-slate-500">
              +{p.lag} barra{p.lag === 1 ? '' : 's'} · r={p.corr.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
