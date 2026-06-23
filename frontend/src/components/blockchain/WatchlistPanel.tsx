/**
 * components/blockchain/WatchlistPanel.tsx — Vigilancia de direcciones on-chain.
 *
 * El usuario añade direcciones de interés (ballenas, tesorerías, contratos) con
 * un umbral de variación; una tarea periódica revisa su saldo vía Blockscout y
 * registra alertas cuando se mueve por encima del umbral. Aquí se gestionan las
 * direcciones vigiladas y se muestran las alertas recientes (whale tracking).
 */

import { useEffect, useState } from 'react'
import {
  blockchainService,
  type AddressAlert,
  type WalletChain,
  type WatchedAddress,
} from '@/services/blockchainService'

function shorten(addr: string): string {
  return addr.length > 14 ? `${addr.slice(0, 8)}…${addr.slice(-6)}` : addr
}

export default function WatchlistPanel() {
  const [chains, setChains] = useState<WalletChain[]>([])
  const [items, setItems] = useState<WatchedAddress[]>([])
  const [alerts, setAlerts] = useState<AddressAlert[]>([])
  const [chain, setChain] = useState('ethereum')
  const [address, setAddress] = useState('')
  const [label, setLabel] = useState('')
  const [threshold, setThreshold] = useState(5)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function reload() {
    blockchainService.getWatchlist()
      .then((r) => { setItems(r.results); setAlerts(r.alerts) })
      .catch(() => { /* sin watchlist */ })
  }

  useEffect(() => {
    blockchainService.getWalletChains().then(setChains).catch(() => { /* sin redes */ })
    reload()
  }, [])

  async function add() {
    const addr = address.trim()
    if (!addr) return
    setBusy(true); setError(null)
    try {
      const r = await blockchainService.addWatchedAddress(chain, addr, label.trim() || undefined, threshold)
      if (r.error) { setError(r.error); return }
      setAddress(''); setLabel('')
      reload()
    } catch (e: unknown) {
      const resp = (e as { response?: { data?: { error?: string } } })?.response
      setError(resp?.data?.error ?? 'No se pudo añadir la dirección.')
    } finally {
      setBusy(false)
    }
  }

  async function remove(id: number) {
    try { await blockchainService.removeWatchedAddress(id); reload() } catch { /* ignora */ }
  }

  return (
    <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 mb-6">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-fuchsia-400">👁</span>
        <h2 className="text-lg font-bold text-white">Vigilancia de direcciones</h2>
      </div>
      <p className="text-slate-400 text-xs mb-4">
        Sigue wallets de interés y recibe alertas cuando su saldo se mueve · whale tracking vía Blockscout
      </p>

      {/* Alta */}
      <div className="flex flex-col lg:flex-row gap-2 mb-4">
        <select value={chain} onChange={(e) => setChain(e.target.value)}
          className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fuchsia-500">
          {(chains.length ? chains : [{ slug: 'ethereum', name: 'Ethereum' } as WalletChain]).map((c) => (
            <option key={c.slug} value={c.slug}>{c.name}</option>
          ))}
        </select>
        <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="0x… dirección"
          spellCheck={false}
          className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-fuchsia-500" />
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Alias (opcional)"
          className="sm:w-40 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-fuchsia-500" />
        <div className="flex items-center gap-1 bg-slate-900 border border-slate-700 rounded-lg px-2">
          <span className="text-[10px] text-slate-500">umbral</span>
          <input type="number" min={0.1} max={100} step={0.5} value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            className="w-14 bg-transparent text-sm text-slate-200 py-2 focus:outline-none" />
          <span className="text-[10px] text-slate-500">%</span>
        </div>
        <button onClick={add} disabled={busy || !address.trim()}
          className="px-5 py-2 rounded-lg text-sm font-bold bg-fuchsia-600 text-white hover:bg-fuchsia-500 transition-colors disabled:opacity-50">
          {busy ? '…' : 'Vigilar'}
        </button>
      </div>

      {error && <div className="text-red-400 text-sm bg-red-900/20 border border-red-700/40 rounded-lg px-3 py-2 mb-3">{error}</div>}

      {/* Direcciones vigiladas */}
      {items.length === 0 ? (
        <p className="text-slate-500 text-sm">Aún no vigilas ninguna dirección.</p>
      ) : (
        <div className="space-y-1.5 mb-4">
          {items.map((w) => (
            <div key={w.id} className="flex items-center gap-2 text-xs bg-slate-900/50 rounded-lg border border-slate-700/60 px-3 py-2">
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-400 uppercase">{w.chain}</span>
              <span className="text-slate-200 font-medium">{w.label || shorten(w.address)}</span>
              <span className="text-slate-300 font-mono ml-auto">
                {w.last_balance != null ? `${w.last_balance.toLocaleString(undefined, { maximumFractionDigits: 4 })} ${w.native_symbol ?? ''}` : '—'}
              </span>
              {w.last_value_usd != null && <span className="text-slate-500 font-mono">${w.last_value_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>}
              <span className="text-[10px] text-slate-600">±{w.alert_threshold_pct}%</span>
              <button onClick={() => remove(w.id)} title="Dejar de vigilar"
                className="text-slate-500 hover:text-red-400 transition-colors">✕</button>
            </div>
          ))}
        </div>
      )}

      {/* Alertas recientes */}
      {alerts.length > 0 && (
        <div>
          <p className="text-[10px] uppercase text-slate-500 mb-2">Movimientos detectados</p>
          <div className="space-y-1">
            {alerts.map((a) => (
              <div key={a.id} className="flex items-center gap-2 text-[11px] py-1 border-b border-slate-800/60 last:border-0">
                <span className={`font-bold px-1.5 py-0.5 rounded border text-[9px] ${
                  a.direction === 'increase' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                    : 'bg-red-500/15 text-red-300 border-red-500/30'}`}>
                  {a.direction === 'increase' ? '↑ ENTRADA' : '↓ SALIDA'}
                </span>
                <span className="text-slate-300">{a.label || shorten(a.address)}</span>
                <span className={`font-mono ml-auto ${a.delta_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {a.delta_pct >= 0 ? '+' : ''}{a.delta_pct.toFixed(1)}%
                </span>
                {a.value_usd != null && <span className="text-slate-500 font-mono">${a.value_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>}
                <span className="text-slate-600">{new Date(a.created_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-[10px] text-slate-600 mt-3">
        La revisión es periódica (cada ~30 min); las alertas aparecen cuando el saldo varía por encima del umbral. No es asesoramiento financiero.
      </p>
    </div>
  )
}
