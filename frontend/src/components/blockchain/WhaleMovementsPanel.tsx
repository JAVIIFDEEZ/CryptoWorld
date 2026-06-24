/**
 * components/blockchain/WhaleMovementsPanel.tsx — Mayores movimientos on-chain.
 *
 * Tabla estilo Whale Alert / Arkham: las mayores transferencias recientes de una
 * red (moneda nativa + tokens ERC-20) ordenadas por valor en USD, con etiquetas
 * de entidad (exchange, contrato, ENS) cuando se conocen. Datos reales vía
 * Blockscout. Selector de red y de umbral mínimo ($).
 */

import { useEffect, useState } from 'react'
import {
  blockchainService,
  type MovementParty,
  type WalletChain,
  type WhaleMovement,
  type WhaleMovementsResponse,
} from '@/services/blockchainService'

const THRESHOLDS = [10_000, 100_000, 1_000_000, 10_000_000]

function fmtUsd(n: number | null): string {
  if (n == null) return '—'
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(1)}K`
  return `$${n.toFixed(0)}`
}

function fmtAmount(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: n >= 1 ? 2 : 6 })
}

function whaleIcon(usd: number | null): string {
  if (usd == null) return ''
  if (usd >= 10_000_000) return '🐋'
  if (usd >= 1_000_000) return '🐳'
  return '🦈'
}

function ago(ts: string | null): string {
  if (!ts) return ''
  const d = (Date.now() - new Date(ts).getTime()) / 1000
  if (d < 60) return `${Math.floor(d)}s`
  if (d < 3600) return `${Math.floor(d / 60)}m`
  if (d < 86400) return `${Math.floor(d / 3600)}h`
  return `${Math.floor(d / 86400)}d`
}

function Party({ p }: Readonly<{ p: MovementParty }>) {
  const short = p.address ? `${p.address.slice(0, 6)}…${p.address.slice(-4)}` : '—'
  if (p.label) {
    return <span className="text-cyan-300 font-medium" title={p.address ?? ''}>{p.label}</span>
  }
  return <span className="text-slate-400 font-mono" title={p.address ?? ''}>{short}{p.is_contract ? ' ⚙' : ''}</span>
}

export default function WhaleMovementsPanel() {
  const [chains, setChains] = useState<WalletChain[]>([])
  const [chain, setChain] = useState('ethereum')
  const [minUsd, setMinUsd] = useState(100_000)
  const [data, setData] = useState<WhaleMovementsResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    blockchainService.getWalletChains().then(setChains).catch(() => { /* sin redes */ })
  }, [])

  useEffect(() => {
    setLoading(true)
    blockchainService.getWhaleMovements(chain, minUsd)
      .then((d) => setData(d.error ? null : d))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [chain, minUsd])

  return (
    <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 mb-6">
      <div className="flex items-center flex-wrap gap-2 mb-1">
        <span className="text-sky-400">🐋</span>
        <h2 className="text-lg font-bold text-white">Mayores movimientos</h2>
        <div className="ml-auto flex gap-2">
          <select value={minUsd} onChange={(e) => setMinUsd(Number(e.target.value))}
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500">
            {THRESHOLDS.map((t) => <option key={t} value={t}>≥ {fmtUsd(t)}</option>)}
          </select>
          <select value={chain} onChange={(e) => setChain(e.target.value)}
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-sky-500">
            {(chains.length ? chains : [{ slug: 'ethereum', name: 'Ethereum' } as WalletChain]).map((c) => (
              <option key={c.slug} value={c.slug}>{c.name}</option>
            ))}
          </select>
        </div>
      </div>
      <p className="text-slate-400 text-xs mb-4">
        Las mayores transferencias recientes por valor en USD · nativas y tokens · vía Blockscout
      </p>

      {loading && <p className="text-slate-500 text-sm">Cargando…</p>}

      {!loading && data && data.movements.length === 0 && (
        <p className="text-slate-500 text-sm">No hay movimientos por encima de {fmtUsd(minUsd)} entre las transacciones recientes.</p>
      )}

      {!loading && data && data.movements.length > 0 && (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-[10px] uppercase text-slate-500 border-b border-slate-700/60">
                  <th className="py-1.5 pr-3">Activo</th>
                  <th className="py-1.5 pr-3 text-right">Cantidad</th>
                  <th className="py-1.5 pr-3 text-right">Valor</th>
                  <th className="py-1.5 pr-3">De</th>
                  <th className="py-1.5 pr-3">A</th>
                  <th className="py-1.5 text-right">Hace</th>
                </tr>
              </thead>
              <tbody>
                {data.movements.map((m: WhaleMovement, i) => (
                  <tr key={`${m.hash}-${i}`} className="border-b border-slate-800 last:border-0 hover:bg-slate-900/40">
                    <td className="py-2 pr-3 whitespace-nowrap">
                      <span className="mr-1">{whaleIcon(m.value_usd)}</span>
                      <span className="text-slate-200 font-semibold">{m.symbol}</span>
                      <span className={`ml-1 text-[9px] px-1 rounded border ${m.kind === 'native' ? 'border-amber-500/30 text-amber-300' : 'border-slate-600 text-slate-500'}`}>
                        {m.kind === 'native' ? 'nativo' : 'token'}
                      </span>
                    </td>
                    <td className="py-2 pr-3 text-right font-mono text-slate-300">{fmtAmount(m.amount)}</td>
                    <td className="py-2 pr-3 text-right font-mono text-emerald-300 font-bold">{fmtUsd(m.value_usd)}</td>
                    <td className="py-2 pr-3 whitespace-nowrap"><Party p={m.from} /></td>
                    <td className="py-2 pr-3 whitespace-nowrap"><Party p={m.to} /></td>
                    <td className="py-2 text-right text-slate-500 whitespace-nowrap">
                      {m.explorer_url
                        ? <a href={m.explorer_url} target="_blank" rel="noreferrer" className="hover:text-sky-300">{ago(m.timestamp)} ↗</a>
                        : ago(m.timestamp)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[10px] text-slate-600 mt-3">
            {data.count} movimientos · {data.scanned} transacciones recientes analizadas. {data.note}
          </p>
        </>
      )}
    </div>
  )
}
