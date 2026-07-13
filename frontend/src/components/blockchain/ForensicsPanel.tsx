/**
 * components/blockchain/ForensicsPanel.tsx — Submódulo forense on-chain.
 *
 * Tres herramientas de grado institucional sobre datos públicos de la cadena:
 *   · Rastreador de flujos: "sigue el dinero" (árbol saliente + patrones).
 *   · Concentración de tenedores de un token (Gini/HHI + veredicto).
 *   · Huella conductual de una wallet (heatmap hora×día + arquetipo).
 */

import { useState } from 'react'
import { blockchainService, type FlowTrace, type FlowNode, type TokenConcentration, type WalletFingerprint } from '@/services/blockchainService'

const CHAINS = ['ethereum', 'base', 'optimism', 'arbitrum', 'gnosis']
const TOOLS = [
  { key: 'flow', label: 'Rastreo de flujos', icon: '💸', hint: 'Sigue el dinero: árbol de salidas + patrones' },
  { key: 'concentration', label: 'Concentración', icon: '🎯', hint: 'Reparto de un token entre tenedores' },
  { key: 'fingerprint', label: 'Huella conductual', icon: '🫆', hint: 'Cómo se comporta una dirección' },
] as const

type Tool = typeof TOOLS[number]['key']

function short(a: string): string {
  return a.length > 12 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a
}

export default function ForensicsPanel() {
  const [tool, setTool] = useState<Tool>('flow')
  const [chain, setChain] = useState('ethereum')

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {TOOLS.map((tdef) => (
          <button
            key={tdef.key}
            onClick={() => setTool(tdef.key)}
            title={tdef.hint}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              tool === tdef.key
                ? 'bg-blue-600/20 text-blue-300 border-blue-500/40'
                : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
            }`}
          >
            <span className="mr-1.5">{tdef.icon}</span>{tdef.label}
          </button>
        ))}
        <select
          value={chain}
          onChange={(e) => setChain(e.target.value)}
          className="ml-auto bg-slate-800 border border-slate-700 rounded-lg text-xs text-slate-200 px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-blue-500"
        >
          {CHAINS.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {tool === 'flow' && <FlowTracer chain={chain} />}
      {tool === 'concentration' && <Concentration chain={chain} />}
      {tool === 'fingerprint' && <Fingerprint chain={chain} />}
    </div>
  )
}

// ── Barra de entrada de dirección reutilizable ──────────────────────

function AddressBar({ placeholder, onRun, loading }: Readonly<{
  placeholder: string; onRun: (addr: string) => void; loading: boolean
}>) {
  const [value, setValue] = useState('')
  const valid = /^0x[0-9a-fA-F]{40}$/.test(value.trim())
  return (
    <div className="flex gap-2">
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && valid) onRun(value.trim()) }}
        placeholder={placeholder}
        className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-600 font-mono focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      <button
        onClick={() => valid && onRun(value.trim())}
        disabled={!valid || loading}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg text-sm font-medium"
      >
        {loading ? '…' : 'Analizar'}
      </button>
    </div>
  )
}

function ErrorNote({ msg }: Readonly<{ msg: string }>) {
  return <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg p-3">{msg}</p>
}

// ── 1. Rastreador de flujos ─────────────────────────────────────────

const PATTERN_STYLE: Record<string, string> = {
  fan_out: 'bg-amber-500/15 border-amber-500/30 text-amber-300',
  peel_chain: 'bg-red-500/15 border-red-500/30 text-red-300',
}

function FlowBranch({ node, isRoot }: Readonly<{ node: FlowNode; isRoot?: boolean }>) {
  return (
    <div className={isRoot ? '' : 'ml-4 border-l border-slate-700/60 pl-3'}>
      <div className="flex items-center gap-2 py-1 text-xs">
        <span className="font-mono text-slate-200">{short(node.address)}</span>
        {node.revisited && <span className="text-[9px] text-slate-500">↩ visto</span>}
        {node.share != null && (
          <span className="text-[10px] text-slate-500">
            {node.value_in} · {Math.round(node.share * 100)}%
          </span>
        )}
        {node.fan_out >= 8 && <span className="text-[9px] text-amber-400">fan-out {node.fan_out}</span>}
      </div>
      {node.children?.map((c, i) => <FlowBranch key={`${c.address}-${i}`} node={c} />)}
    </div>
  )
}

function FlowTracer({ chain }: Readonly<{ chain: string }>) {
  const [data, setData] = useState<FlowTrace | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function run(address: string) {
    setLoading(true); setError(''); setData(null)
    try {
      const res = await blockchainService.traceFlow(chain, address, 2)
      if (res.error) setError(res.error)
      else setData(res)
    } catch { setError('No se pudo rastrear el flujo.') } finally { setLoading(false) }
  }

  return (
    <div className="space-y-3">
      <AddressBar placeholder="Dirección de origen (0x…)" onRun={run} loading={loading} />
      <p className="text-[10px] text-slate-500">Sigue el valor nativo saliente salto a salto (top contrapartes). Detecta distribución (fan-out) y cadenas de reenvío (peel chain).</p>
      {error && <ErrorNote msg={error} />}
      {data && (
        <div className="bg-slate-900/60 rounded-lg border border-slate-700/60 p-3 space-y-3">
          {data.patterns.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {data.patterns.map((p, i) => (
                <span key={i} className={`text-[10px] px-2 py-0.5 rounded-full border ${PATTERN_STYLE[p.type]}`} title={p.note}>
                  {p.type === 'fan_out' ? `⚠ Fan-out (${p.counterparties})` : `⛓ Peel chain (${p.depth} saltos)`}
                </span>
              ))}
            </div>
          )}
          <FlowBranch node={data.tree} isRoot />
          <p className="text-[9px] text-slate-600">{data.nodes_fetched} nodos consultados · {data.note}</p>
        </div>
      )}
    </div>
  )
}

// ── 2. Concentración de tenedores ───────────────────────────────────

const VERDICT_STYLE: Record<string, string> = {
  'CRÍTICA': 'bg-red-500/15 border-red-500/40 text-red-300',
  'ALTA': 'bg-amber-500/15 border-amber-500/40 text-amber-300',
  'MODERADA': 'bg-yellow-500/10 border-yellow-500/30 text-yellow-300',
  'DISTRIBUIDA': 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300',
}

function Concentration({ chain }: Readonly<{ chain: string }>) {
  const [data, setData] = useState<TokenConcentration | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function run(token: string) {
    setLoading(true); setError(''); setData(null)
    try {
      const res = await blockchainService.tokenConcentration(chain, token)
      if (res.error) setError(res.error)
      else setData(res)
    } catch { setError('No se pudo analizar el token.') } finally { setLoading(false) }
  }

  const c = data?.concentration
  return (
    <div className="space-y-3">
      <AddressBar placeholder="Contrato del token ERC-20 (0x…)" onRun={run} loading={loading} />
      {error && <ErrorNote msg={error} />}
      {data && c && (c.available ? (
        <div className="bg-slate-900/60 rounded-lg border border-slate-700/60 p-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h4 className="text-sm font-semibold text-white">
              {data.token_name} <span className="text-slate-500 font-mono">{data.token_symbol}</span>
            </h4>
            <span className={`text-[11px] px-2 py-0.5 rounded-full border font-medium ${VERDICT_STYLE[c.verdict ?? '']}`}>
              {c.verdict}
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            {[
              ['Top-10', `${c.top10_share_pct}%`],
              ['Top-50', `${c.top50_share_pct}%`],
              ['Gini', c.gini != null ? c.gini.toFixed(2) : '—'],
              ['HHI', c.hhi != null ? c.hhi.toFixed(2) : '—'],
            ].map(([label, value]) => (
              <div key={label} className="bg-slate-800/60 rounded-lg p-2">
                <p className="text-base font-bold font-mono text-white">{value}</p>
                <p className="text-[9px] text-slate-500">{label}</p>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-slate-400">{c.verdict_note}</p>
          <div className="space-y-1">
            <p className="text-[10px] uppercase text-slate-500">Mayores tenedores (muestra)</p>
            {c.top_holders?.slice(0, 8).map((h) => (
              <div key={h.address} className="flex items-center gap-2 text-[11px]">
                <span className="font-mono text-slate-300 w-32">{short(h.address)}</span>
                <div className="flex-1 h-2.5 bg-slate-800 rounded overflow-hidden">
                  <div className="h-full bg-blue-500/60" style={{ width: `${Math.min(100, h.share_pct)}%` }} />
                </div>
                <span className="font-mono text-slate-400 w-12 text-right">{h.share_pct}%</span>
                {h.is_contract && <span className="text-[9px] text-purple-400" title="Contrato (posible LP, bridge, staking)">📄</span>}
              </div>
            ))}
          </div>
          <p className="text-[9px] text-slate-600">{c.note}</p>
        </div>
      ) : (
        <p className="text-xs text-slate-500">{c.note ?? 'Sin datos suficientes.'}</p>
      ))}
    </div>
  )
}

// ── 3. Huella conductual ────────────────────────────────────────────

const DOW = ['L', 'M', 'X', 'J', 'V', 'S', 'D']

function Heatmap({ grid }: Readonly<{ grid: number[][] }>) {
  const max = Math.max(...grid.flat(), 1)
  return (
    <div className="overflow-x-auto">
      <table className="text-[8px] border-separate" style={{ borderSpacing: 1 }}>
        <thead>
          <tr>
            <th />
            {Array.from({ length: 24 }, (_, h) => (
              <th key={h} className="text-slate-600 font-normal w-3">{h % 6 === 0 ? h : ''}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.map((row, d) => (
            <tr key={d}>
              <td className="text-slate-500 pr-1">{DOW[d]}</td>
              {row.map((v, h) => (
                <td
                  key={h}
                  title={`${DOW[d]} ${h}:00 UTC · ${v} tx`}
                  className="w-3 h-3 rounded-sm"
                  style={{ background: v === 0 ? '#1e293b' : `rgba(96,165,250,${0.2 + 0.8 * (v / max)})` }}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Fingerprint({ chain }: Readonly<{ chain: string }>) {
  const [data, setData] = useState<WalletFingerprint | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function run(address: string) {
    setLoading(true); setError(''); setData(null)
    try {
      const res = await blockchainService.walletFingerprint(chain, address)
      if (res.error) setError(res.error)
      else setData(res)
    } catch { setError('No se pudo perfilar la dirección.') } finally { setLoading(false) }
  }

  const fp = data?.fingerprint
  return (
    <div className="space-y-3">
      <AddressBar placeholder="Dirección a perfilar (0x…)" onRun={run} loading={loading} />
      {error && <ErrorNote msg={error} />}
      {data && fp && (fp.available ? (
        <div className="bg-slate-900/60 rounded-lg border border-slate-700/60 p-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <span className="text-sm font-semibold text-white">
              Arquetipo: <span className="text-blue-300">{fp.archetype}</span>
            </span>
            <span className="text-[10px] text-slate-500">{fp.sample_txs} tx · {fp.span_days} días</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            {[
              ['Tx/semana', fp.txs_per_week?.toFixed(1)],
              ['Contrapartes', fp.unique_counterparties],
              ['Diversidad', fp.diversity != null ? `${Math.round(fp.diversity * 100)}%` : '—'],
              ['Sin actividad', fp.days_since_last != null ? `${Math.round(fp.days_since_last)}d` : '—'],
            ].map(([label, value]) => (
              <div key={label} className="bg-slate-800/60 rounded-lg p-2">
                <p className="text-base font-bold font-mono text-white">{value ?? '—'}</p>
                <p className="text-[9px] text-slate-500">{label}</p>
              </div>
            ))}
          </div>
          {fp.heatmap && (
            <div>
              <p className="text-[10px] uppercase text-slate-500 mb-1">Actividad hora × día (UTC)</p>
              <Heatmap grid={fp.heatmap} />
            </div>
          )}
          {fp.traits && fp.traits.length > 0 && (
            <ul className="text-[11px] text-slate-400 space-y-0.5 list-disc list-inside">
              {fp.traits.map((tr, i) => <li key={i}>{tr}</li>)}
            </ul>
          )}
          <p className="text-[9px] text-slate-600">{fp.note}</p>
        </div>
      ) : (
        <p className="text-xs text-slate-500">{fp.note ?? 'Actividad insuficiente para perfilar.'}</p>
      ))}
    </div>
  )
}
