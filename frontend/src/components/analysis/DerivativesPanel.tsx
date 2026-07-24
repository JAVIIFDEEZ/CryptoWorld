/**
 * DerivativesPanel.tsx — Microestructura de perpetuos (funding / basis / OI).
 *
 * Muestra el funding anualizado con veredicto de sobrecalentamiento, el basis
 * (contango/backwardation) y el interés abierto (contratos + nocional) del
 * perpetuo USDⓈ-M del activo. Se monta junto a la terminal cuantitativa.
 */

import { useEffect, useState } from 'react'
import { analysisService, type DerivativesSnapshot } from '@/services/analysisService'

function pct(n: number | null | undefined): string {
  if (n == null) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
}

function compactUsd(n: number | null | undefined): string {
  if (n == null) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(1)}K`
  return `$${n.toFixed(0)}`
}

function verdictClass(v: string | undefined): string {
  if (!v) return 'text-slate-400'
  if (v.includes('SOBRECALENTAD')) return 'text-red-300'
  if (v.includes('alcista') || v === 'contango' || v === 'contango fuerte') return 'text-emerald-300'
  if (v.includes('bajista') || v.includes('backwardation')) return 'text-amber-300'
  return 'text-slate-400'
}

export default function DerivativesPanel({ symbol }: Readonly<{ symbol: string }>) {
  const [snap, setSnap] = useState<DerivativesSnapshot | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    analysisService.getDerivatives(symbol)
      .then((d) => { if (!cancelled) setSnap(d) })
      .catch(() => { if (!cancelled) setSnap({ available: false }) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol])

  if (loading) {
    return <div className="text-xs text-slate-500 py-3">Cargando derivados…</div>
  }
  if (!snap || !snap.available) {
    return (
      <div className="text-xs text-slate-500 py-3">
        {symbol} no tiene perpetuo USDⓈ-M o la fuente no responde.
      </div>
    )
  }

  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-3">
        Derivados · <span className="font-mono text-slate-400">{snap.perp_symbol}</span>
      </h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Funding anual.</p>
          <p className={`text-lg font-bold font-mono ${verdictClass(snap.funding_verdict)}`}>
            {pct(snap.funding_annualized_pct)}
          </p>
          <p className={`text-[10px] ${verdictClass(snap.funding_verdict)}`}>{snap.funding_verdict}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Basis</p>
          <p className={`text-lg font-bold font-mono ${verdictClass(snap.basis_verdict)}`}>
            {pct(snap.basis_pct)}
          </p>
          <p className={`text-[10px] ${verdictClass(snap.basis_verdict)}`}>{snap.basis_verdict}</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Interés abierto</p>
          <p className="text-lg font-bold font-mono text-white">{compactUsd(snap.open_interest_usd)}</p>
          <p className="text-[10px] text-slate-500">nocional</p>
        </div>
        <div>
          <p className="text-[10px] text-slate-500 uppercase">Mark / Index</p>
          <p className="text-sm font-bold font-mono text-white">
            {snap.mark_price?.toLocaleString('en-US', { maximumFractionDigits: 2 })}
          </p>
          <p className="text-[10px] text-slate-500 font-mono">
            {snap.index_price?.toLocaleString('en-US', { maximumFractionDigits: 2 }) ?? '—'}
          </p>
        </div>
      </div>
    </div>
  )
}
