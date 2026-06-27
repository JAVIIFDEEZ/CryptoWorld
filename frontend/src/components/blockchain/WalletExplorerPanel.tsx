/**
 * components/blockchain/WalletExplorerPanel.tsx — Explorador on-chain de wallets.
 *
 * Pega una dirección y elige una red (Ethereum, Base, Optimism, Arbitrum,
 * Gnosis): muestra su saldo nativo valorado en USD, la cartera de tokens ERC-20
 * ordenada por valor y las transacciones recientes. Datos 100% reales vía la API
 * REST v2 de Blockscout. Convierte el módulo de "estadísticas de red" en una
 * herramienta de analítica on-chain a nivel de dirección.
 */

import { useEffect, useState } from 'react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  blockchainService,
  type BalancePoint,
  type WalletChain,
  type WalletOverview,
} from '@/services/blockchainService'
import { useWallet } from '@/hooks/useWallet'

function fmtUsd(n: number | null | undefined): string {
  if (n == null) return '—'
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
}

function shorten(addr: string | null): string {
  if (!addr) return '—'
  return addr.length > 14 ? `${addr.slice(0, 8)}…${addr.slice(-6)}` : addr
}

export default function WalletExplorerPanel() {
  const wallet = useWallet()
  const [chains, setChains] = useState<WalletChain[]>([])
  const [chain, setChain] = useState('ethereum')
  const [address, setAddress] = useState('')
  const [data, setData] = useState<WalletOverview | null>(null)
  const [history, setHistory] = useState<BalancePoint[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    blockchainService.getWalletChains().then(setChains).catch(() => { /* sin redes */ })
  }, [])

  async function search(addrArg?: string, chainArg?: string) {
    const addr = (addrArg ?? address).trim()
    const ch = chainArg ?? chain
    if (!addr) return
    setLoading(true); setError(null); setData(null); setHistory([])
    try {
      const r = await blockchainService.getWalletOverview(ch, addr)
      if (r.error) { setError(r.error); return }
      setData(r)
      // Curva de patrimonio (best-effort: no bloquea la vista si falla).
      blockchainService.getWalletBalanceHistory(ch, addr)
        .then((h) => { if (!h.error) setHistory(h.history) })
        .catch(() => { /* sin historial */ })
    } catch (e: unknown) {
      const resp = (e as { response?: { data?: { error?: string } } })?.response
      setError(resp?.data?.error ?? 'No se pudo consultar la dirección.')
    } finally {
      setLoading(false)
    }
  }

  // Al conectar la wallet, carga automáticamente la cartera del usuario.
  useEffect(() => {
    if (!wallet.address) return
    const ch = wallet.chainSlug ?? 'ethereum'
    setAddress(wallet.address)
    setChain(ch)
    search(wallet.address, ch)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wallet.address, wallet.chainSlug])

  return (
    <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 mb-6">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-indigo-400">🔍</span>
        <h2 className="text-lg font-bold text-white">Explorador de wallets on-chain</h2>
        {wallet.available && (
          wallet.address ? (
            <button
              onClick={wallet.disconnect}
              title="Desconectar wallet"
              className="ml-auto text-[11px] px-2.5 py-1 rounded-lg bg-emerald-600/15 text-emerald-300 border border-emerald-500/30 hover:bg-emerald-600/25 transition-colors font-mono"
            >
              ● {wallet.address.slice(0, 6)}…{wallet.address.slice(-4)}
            </button>
          ) : (
            <button
              onClick={wallet.connect}
              disabled={wallet.connecting}
              className="ml-auto text-[11px] px-2.5 py-1 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 transition-colors disabled:opacity-50"
            >
              {wallet.connecting ? 'Conectando…' : '🦊 Conectar wallet'}
            </button>
          )
        )}
      </div>
      <p className="text-slate-400 text-xs mb-4">
        Saldo, tokens y transacciones reales de cualquier dirección · multi-cadena vía Blockscout
        {wallet.available && !wallet.address && ' · o conecta tu wallet para ver la tuya'}
      </p>
      {wallet.error && <p className="text-amber-300/80 text-[11px] mb-2">{wallet.error}</p>}

      {/* Controles */}
      <div className="flex flex-col sm:flex-row gap-2 mb-4">
        <select
          value={chain}
          onChange={(e) => setChain(e.target.value)}
          className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
        >
          {(chains.length ? chains : [{ slug: 'ethereum', name: 'Ethereum' } as WalletChain]).map((c) => (
            <option key={c.slug} value={c.slug}>{c.name}</option>
          ))}
        </select>
        <input
          value={address}
          onChange={(e) => setAddress(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') search() }}
          placeholder="0x… dirección o contrato"
          spellCheck={false}
          className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 font-mono focus:outline-none focus:border-indigo-500"
        />
        <button
          onClick={() => search()}
          disabled={loading || !address.trim()}
          className="px-5 py-2 rounded-lg text-sm font-bold bg-indigo-600 text-white hover:bg-indigo-500 transition-colors disabled:opacity-50"
        >
          {loading ? 'Buscando…' : 'Explorar'}
        </button>
      </div>

      {error && <div className="text-red-400 text-sm bg-red-900/20 border border-red-700/40 rounded-lg px-3 py-2">{error}</div>}

      {data && <WalletResult data={data} history={history} fmtUsd={fmtUsd} />}
    </div>
  )
}

function BalanceCurve({ history, symbol }: Readonly<{ history: BalancePoint[]; symbol: string }>) {
  if (history.length < 2) return null
  const data = history.map((p) => ({ date: p.date, balance: p.balance }))
  const last = data[data.length - 1].balance
  const first = data[0].balance
  const stroke = last >= first ? '#22c55e' : '#ef4444'
  return (
    <div>
      <p className="text-xs text-slate-400 uppercase mb-2">Saldo nativo en el tiempo ({symbol})</p>
      <ResponsiveContainer width="100%" height={120}>
        <AreaChart data={data} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
          <defs>
            <linearGradient id="balfill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} axisLine={{ stroke: '#334155' }} tickLine={false} minTickGap={28} />
          <YAxis tick={{ fill: '#64748b', fontSize: 9 }} axisLine={false} tickLine={false} width={48} />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
            formatter={(v) => [`${typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 6 }) : v} ${symbol}`, 'saldo']}
          />
          <Area type="monotone" dataKey="balance" stroke={stroke} strokeWidth={1.5} fill="url(#balfill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function WalletResult({ data, history, fmtUsd }: Readonly<{ data: WalletOverview; history: BalancePoint[]; fmtUsd: (n: number | null | undefined) => string }>) {
  return (
    <div className="space-y-4">
      {/* Resumen */}
      <div className="bg-slate-900/50 rounded-lg border border-slate-700/60 p-4">
        <div className="flex items-center flex-wrap gap-2 mb-2">
          <a href={data.explorer_url} target="_blank" rel="noreferrer"
            className="text-indigo-300 font-mono text-sm hover:underline">{shorten(data.address)}</a>
          {data.ens_name && <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">{data.ens_name}</span>}
          {data.is_contract && <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30">contrato{data.is_verified ? ' ✓' : ''}</span>}
          <span className="text-[10px] text-slate-500 ml-auto">{data.chain_name}</span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <Metric label={`Saldo ${data.native_symbol}`} value={`${data.native_balance.toLocaleString(undefined, { maximumFractionDigits: 6 })}`}
            sub={data.native_value_usd != null ? fmtUsd(data.native_value_usd) : undefined} />
          <Metric label="Tokens" value={String(data.token_count)} sub={data.tokens_value_usd != null ? fmtUsd(data.tokens_value_usd) : undefined} />
          <Metric label="Valor cartera" value={fmtUsd(data.portfolio_value_usd)} accent />
        </div>
      </div>

      {/* Curva de patrimonio on-chain */}
      {history.length >= 2 && <BalanceCurve history={history} symbol={data.native_symbol} />}

      {/* Tokens */}
      {data.tokens.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 uppercase mb-2">Cartera de tokens (ERC-20)</p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-[10px] uppercase text-slate-500 border-b border-slate-700/60">
                  <th className="py-1.5 pr-3">Token</th>
                  <th className="py-1.5 pr-3 text-right">Saldo</th>
                  <th className="py-1.5 pr-3 text-right">Precio</th>
                  <th className="py-1.5 text-right">Valor</th>
                </tr>
              </thead>
              <tbody>
                {data.tokens.map((t) => (
                  <tr key={t.address ?? t.symbol} className="border-b border-slate-800 last:border-0">
                    <td className="py-1.5 pr-3">
                      <span className="text-slate-200 font-semibold">{t.symbol}</span>
                      <span className="text-slate-600 ml-1 truncate">{t.name}</span>
                    </td>
                    <td className="py-1.5 pr-3 text-right font-mono text-slate-300">{t.balance.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
                    <td className="py-1.5 pr-3 text-right font-mono text-slate-400">{t.price_usd != null ? fmtUsd(t.price_usd) : '—'}</td>
                    <td className="py-1.5 text-right font-mono text-emerald-300">{t.value_usd != null ? fmtUsd(t.value_usd) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Transacciones */}
      {data.transactions.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 uppercase mb-2">Transacciones recientes</p>
          <div className="space-y-1">
            {data.transactions.map((tx) => (
              <div key={tx.hash} className="flex items-center gap-2 text-[11px] py-1 border-b border-slate-800/60 last:border-0">
                <span className={`font-bold px-1.5 py-0.5 rounded border text-[9px] ${
                  tx.direction === 'out' ? 'bg-red-500/15 text-red-300 border-red-500/30'
                    : tx.direction === 'in' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                      : 'bg-slate-700/40 text-slate-400 border-slate-600/40'}`}>
                  {tx.direction === 'out' ? '↑ OUT' : tx.direction === 'in' ? '↓ IN' : 'SELF'}
                </span>
                <span className="text-slate-400 font-mono">{tx.method || 'transfer'}</span>
                <span className="text-slate-300 font-mono ml-auto">{tx.value_native.toLocaleString(undefined, { maximumFractionDigits: 4 })} {data.native_symbol}</span>
                <span className="text-slate-600">{tx.timestamp ? new Date(tx.timestamp).toLocaleDateString() : ''}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-[10px] text-slate-600">Datos on-chain en vivo desde Blockscout. No es asesoramiento financiero.</p>
    </div>
  )
}

function Metric({ label, value, sub, accent = false }: Readonly<{ label: string; value: string; sub?: string; accent?: boolean }>) {
  return (
    <div>
      <p className="text-[10px] text-slate-500 uppercase">{label}</p>
      <p className={`text-sm font-bold font-mono ${accent ? 'text-emerald-400' : 'text-white'}`}>{value}</p>
      {sub && <p className="text-[10px] text-slate-500 font-mono">{sub}</p>}
    </div>
  )
}
