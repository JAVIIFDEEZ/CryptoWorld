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

function Party({ p, watched, busy, onWatch }: Readonly<{
  p: MovementParty; watched?: boolean; busy?: boolean; onWatch?: (addr: string | null) => void
}>) {
  const short = p.address ? `${p.address.slice(0, 6)}…${p.address.slice(-4)}` : '—'
  const label = p.label
    ? <span className="text-cyan-300 font-medium" title={p.address ?? ''}>{p.label}</span>
    : <span className="text-slate-400 font-mono" title={p.address ?? ''}>{short}{p.is_contract ? ' ⚙' : ''}</span>
  return (
    <span className="inline-flex items-center gap-1">
      {label}
      {p.address && onWatch && (
        <button
          onClick={() => onWatch(p.address)}
          disabled={busy}
          title={watched ? 'Ya en tu watchlist' : 'Vigilar esta dirección'}
          className={`text-[10px] transition-colors disabled:opacity-50 ${watched ? 'text-fuchsia-400' : 'text-slate-600 hover:text-fuchsia-300'}`}
        >
          {watched ? '✓👁' : '👁'}
        </button>
      )}
    </span>
  )
}

export default function WhaleMovementsPanel() {
  const [chains, setChains] = useState<WalletChain[]>([])
  const [chain, setChain] = useState('ethereum')
  const [minUsd, setMinUsd] = useState(100_000)
  const [data, setData] = useState<WhaleMovementsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [watched, setWatched] = useState<Set<string>>(new Set())
  const [busyAddr, setBusyAddr] = useState<string | null>(null)

  // Vigilar (añadir a la watchlist) una dirección que aparece en un movimiento,
  // sin salir del feed. Conecta el whale watch con la watchlist.
  async function watchAddress(addr: string | null) {
    if (!addr || !data) return
    const key = addr.toLowerCase()
    if (watched.has(key)) return
    setBusyAddr(addr)
    try {
      await blockchainService.addWatchedAddress(data.chain, addr)
      setWatched((s) => new Set(s).add(key))   // marca también si ya estaba vigilada
    } catch { /* ignora */ }
    finally { setBusyAddr(null) }
  }

  useEffect(() => {
    blockchainService.getWalletChains().then(setChains).catch(() => { /* sin redes */ })
  }, [])

  function load() {
    setLoading(true); setError(null)
    blockchainService.getWhaleMovements(chain, minUsd)
      .then((d) => {
        if (d.error) { setData(null); setError(d.error) }
        else setData(d)
      })
      .catch((e: unknown) => {
        setData(null)
        const resp = (e as { response?: { data?: { error?: string } } })?.response
        setError(resp?.data?.error ?? 'No se pudieron cargar los movimientos (¿red de Blockscout accesible?).')
      })
      .finally(() => setLoading(false))
  }

  useEffect(load, [chain, minUsd])

  return (
    <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 mb-6">
      <div className="flex items-center flex-wrap gap-2 mb-1">
        <span className="text-sky-400">🐋</span>
        <h2 className="text-lg font-bold text-white">Mayores movimientos</h2>
        <div className="ml-auto flex gap-2">
          <button onClick={load} disabled={loading} title="Actualizar"
            className="px-2 py-1.5 rounded-lg text-sm bg-slate-900 border border-slate-700 text-slate-300 hover:text-white transition-colors disabled:opacity-50">
            ⟳
          </button>
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

      {loading && <p className="text-slate-500 text-sm">Cargando movimientos…</p>}

      {!loading && error && (
        <div className="text-amber-300/90 text-sm bg-amber-900/15 border border-amber-700/40 rounded-lg px-3 py-2">
          {error} <button onClick={load} className="underline hover:text-amber-200 ml-1">Reintentar</button>
        </div>
      )}

      {!loading && !error && data && data.movements.length === 0 && (
        <p className="text-slate-500 text-sm">
          No hay movimientos por encima de {fmtUsd(minUsd)} entre las {data.scanned} transacciones recientes analizadas.
          Prueba a bajar el umbral.
        </p>
      )}

      {!loading && !error && data && data.movements.length > 0 && (
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
                    <td className="py-2 pr-3 whitespace-nowrap">
                      <Party p={m.from} watched={watched.has((m.from.address ?? '').toLowerCase())} busy={busyAddr === m.from.address} onWatch={watchAddress} />
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap">
                      <Party p={m.to} watched={watched.has((m.to.address ?? '').toLowerCase())} busy={busyAddr === m.to.address} onWatch={watchAddress} />
                    </td>
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
