/**
 * components/blockchain/ForensicsPanel.tsx — Submódulo forense on-chain.
 *
 * Tres herramientas de grado institucional sobre datos públicos de la cadena:
 *   · Rastreador de flujos: "sigue el dinero" (árbol saliente + patrones).
 *   · Concentración de tenedores de un token (Gini/HHI + veredicto).
 *   · Huella conductual de una wallet (heatmap hora×día + arquetipo).
 */

import { useState } from 'react'
import {
  blockchainService,
  type FlowTrace, type FlowNode, type TokenConcentration, type WalletFingerprint,
  type AddressRisk, type ApprovalsResult, type EntityGraph, type TokenSafety,
  type WashTrading,
} from '@/services/blockchainService'

const CHAINS = ['ethereum', 'base', 'optimism', 'arbitrum', 'gnosis']
const TOOLS = [
  { key: 'dossier', label: 'Dossier forense', icon: '📄', hint: 'Informe unificado imprimible de una dirección' },
  { key: 'risk', label: 'Riesgo de dirección', icon: '🛡️', hint: 'Puntuación 0-100 por exposición y patrones' },
  { key: 'token', label: 'Seguridad de token', icon: '🔬', hint: 'Due diligence: rug/honeypot a nivel de contrato' },
  { key: 'wash', label: 'Wash trading', icon: '🔁', hint: 'Volumen artificial (round-trips)' },
  { key: 'approvals', label: 'Aprobaciones', icon: '⚠️', hint: 'Allowances ERC-20 peligrosas' },
  { key: 'entity', label: 'Grafo de entidad', icon: '🕸️', hint: 'Direcciones que se mueven juntas' },
  { key: 'flow', label: 'Rastreo de flujos', icon: '💸', hint: 'Sigue el dinero: árbol de salidas + patrones' },
  { key: 'concentration', label: 'Concentración', icon: '🎯', hint: 'Reparto de un token entre tenedores' },
  { key: 'fingerprint', label: 'Huella conductual', icon: '🫆', hint: 'Cómo se comporta una dirección' },
] as const

type Tool = typeof TOOLS[number]['key']

function short(a: string): string {
  return a.length > 12 ? `${a.slice(0, 6)}…${a.slice(-4)}` : a
}

export default function ForensicsPanel() {
  const [tool, setTool] = useState<Tool>('dossier')
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

      {tool === 'dossier' && <DossierLauncher chain={chain} />}
      {tool === 'risk' && <RiskScore chain={chain} />}
      {tool === 'token' && <TokenSafetyView chain={chain} />}
      {tool === 'wash' && <WashTradingView chain={chain} />}
      {tool === 'approvals' && <Approvals chain={chain} />}
      {tool === 'entity' && <EntityGraphView chain={chain} />}
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

// ── Dossier forense (informe unificado imprimible) ──────────────────

function DossierLauncher({ chain }: Readonly<{ chain: string }>) {
  function open(address: string) {
    window.open(`/blockchain/address/${chain}/${address}/dossier`, '_blank', 'noopener,noreferrer')
  }
  return (
    <div className="space-y-3">
      <AddressBar placeholder="Dirección para el informe (0x…)" onRun={open} loading={false} />
      <div className="bg-slate-900/60 rounded-lg border border-slate-700/60 p-4">
        <p className="text-sm text-slate-300 mb-2">📄 Informe forense unificado</p>
        <p className="text-[11px] text-slate-500 leading-relaxed">
          Genera un documento de auditoría imprimible (PDF) que reúne las cinco herramientas de dirección
          —puntuación de riesgo, huella conductual, aprobaciones ERC-20 vivas, entidad probable y patrones de flujo—
          con un veredicto global y los hallazgos clave. Se abre en una pestaña nueva; agrega varios análisis, así que
          tarda unos segundos.
        </p>
      </div>
    </div>
  )
}

// ── Seguridad de token (due diligence) ──────────────────────────────

const SAFETY_STYLE: Record<string, { cls: string; bar: string }> = {
  'PELIGROSO': { cls: 'text-red-300', bar: 'bg-red-500' },
  'RIESGO ALTO': { cls: 'text-amber-300', bar: 'bg-amber-500' },
  'PRECAUCIÓN': { cls: 'text-yellow-300', bar: 'bg-yellow-500' },
  'RAZONABLE': { cls: 'text-emerald-300', bar: 'bg-emerald-500' },
}

function TokenSafetyView({ chain }: Readonly<{ chain: string }>) {
  const [data, setData] = useState<TokenSafety | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function run(token: string) {
    setLoading(true); setError(''); setData(null)
    try {
      const res = await blockchainService.tokenSafety(chain, token)
      if (res.error) setError(res.error)
      else setData(res)
    } catch { setError('No se pudo analizar el token.') } finally { setLoading(false) }
  }

  const style = data ? SAFETY_STYLE[data.verdict] : undefined
  return (
    <div className="space-y-3">
      <AddressBar placeholder="Contrato del token ERC-20 (0x…)" onRun={run} loading={loading} />
      <p className="text-[10px] text-slate-500">Due diligence a nivel de contrato: verificación, proxy actualizable, poderes del propietario (mint/pausa/lista negra/fees) y concentración. Señala CAPACIDADES de abuso, no que se hayan usado.</p>
      {error && <ErrorNote msg={error} />}
      {data && (
        <div className="bg-slate-900/60 rounded-lg border border-slate-700/60 p-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h4 className="text-sm font-semibold text-white">
              {data.token_name} <span className="text-slate-500 font-mono">{data.token_symbol}</span>
            </h4>
            <span className={`text-sm font-bold ${style?.cls}`}>{data.verdict}</span>
          </div>
          {/* Barra de riesgo 0-100 */}
          <div>
            <div className="flex justify-between text-[10px] text-slate-500 mb-0.5">
              <span>Riesgo</span><span className="font-mono">{data.score}/100</span>
            </div>
            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
              <div className={`h-full ${style?.bar}`} style={{ width: `${data.score}%` }} />
            </div>
          </div>
          {/* Estado del contrato */}
          <div className="flex flex-wrap gap-2 text-[10px]">
            <StatusPill ok={data.verified} label={data.verified ? 'Verificado' : 'Sin verificar'} invert={!data.verified} />
            <StatusPill ok={!data.is_proxy} label={data.is_proxy ? 'Proxy actualizable' : 'No proxy'} invert={data.is_proxy} />
            <StatusPill ok={data.ownership_renounced} label={data.ownership_renounced ? 'Propiedad renunciada' : 'Propietario activo'} invert={!data.ownership_renounced} />
          </div>
          {/* Banderas rojas */}
          {data.flags.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] uppercase text-red-400/70">Banderas rojas</p>
              {data.flags.map((f, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px]">
                  <span className="text-red-400 mt-0.5">▲</span>
                  <span><span className="text-slate-200 font-medium">{f.label}.</span> <span className="text-slate-400">{f.detail}</span></span>
                </div>
              ))}
            </div>
          )}
          {/* Señales verdes */}
          {data.green_flags.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] uppercase text-emerald-400/70">A favor</p>
              {data.green_flags.map((g, i) => (
                <div key={i} className="flex items-start gap-2 text-[11px] text-slate-400">
                  <span className="text-emerald-400 mt-0.5">✓</span>{g}
                </div>
              ))}
            </div>
          )}
          <p className="text-[9px] text-slate-600">{data.note}</p>
        </div>
      )}
    </div>
  )
}

function StatusPill({ ok, label, invert }: Readonly<{ ok: boolean; label: string; invert?: boolean }>) {
  const good = invert ? false : ok
  return (
    <span className={`px-2 py-0.5 rounded-full border ${
      good ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
           : 'bg-red-500/10 border-red-500/30 text-red-300'
    }`}>
      {good ? '✓' : '✗'} {label}
    </span>
  )
}

// ── Wash trading (volumen artificial) ───────────────────────────────

const WASH_STYLE: Record<string, { cls: string; bar: string }> = {
  'MANIPULADO': { cls: 'text-red-300', bar: 'bg-red-500' },
  'SOSPECHOSO': { cls: 'text-amber-300', bar: 'bg-amber-500' },
  'DUDOSO': { cls: 'text-yellow-300', bar: 'bg-yellow-500' },
  'ORGÁNICO': { cls: 'text-emerald-300', bar: 'bg-emerald-500' },
}

function WashTradingView({ chain }: Readonly<{ chain: string }>) {
  const [data, setData] = useState<WashTrading | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function run(token: string) {
    setLoading(true); setError(''); setData(null)
    try {
      const res = await blockchainService.washTrading(chain, token)
      if (res.error) setError(res.error)
      else setData(res)
    } catch { setError('No se pudo analizar el token.') } finally { setLoading(false) }
  }

  const style = data?.verdict ? WASH_STYLE[data.verdict] : undefined
  return (
    <div className="space-y-3">
      <AddressBar placeholder="Contrato del token ERC-20 (0x…)" onRun={run} loading={loading} />
      <p className="text-[10px] text-slate-500">Detecta volumen inflado por transferencias circulares (ida y vuelta entre las mismas direcciones): la firma del wash trading. Señala patrones, no prueba intención.</p>
      {error && <ErrorNote msg={error} />}
      {data && (data.available ? (
        <div className="bg-slate-900/60 rounded-lg border border-slate-700/60 p-4 space-y-3">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h4 className="text-sm font-semibold text-white">
              {data.token_name} <span className="text-slate-500 font-mono">{data.token_symbol}</span>
            </h4>
            <span className={`text-sm font-bold ${style?.cls}`}>{data.verdict}</span>
          </div>
          <div>
            <div className="flex justify-between text-[10px] text-slate-500 mb-0.5">
              <span>Índice de wash</span><span className="font-mono">{data.wash_score}/100</span>
            </div>
            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
              <div className={`h-full ${style?.bar}`} style={{ width: `${data.wash_score}%` }} />
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center">
            {[
              ['Round-trip', `${data.round_trip_volume_pct}%`],
              ['Top-5 pares', `${data.top5_pair_share_pct}%`],
              ['Transfers', data.total_transfers],
              ['Direcciones', data.unique_addresses],
            ].map(([label, value]) => (
              <div key={label} className="bg-slate-800/60 rounded-lg p-2">
                <p className="text-base font-bold font-mono text-white">{value}</p>
                <p className="text-[9px] text-slate-500">{label}</p>
              </div>
            ))}
          </div>
          {data.suspicious_pairs && data.suspicious_pairs.length > 0 && (
            <div className="space-y-1">
              <p className="text-[10px] uppercase text-slate-500">Pares con round-trip</p>
              {data.suspicious_pairs.slice(0, 6).map((p, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  <span className="font-mono text-slate-300">{short(p.a)} ⇄ {short(p.b)}</span>
                  <span className="text-slate-500">{p.transfers} tx</span>
                  <span className="ml-auto font-mono text-amber-300">{p.share_pct}%</span>
                </div>
              ))}
            </div>
          )}
          <p className="text-[9px] text-slate-600">{data.note}</p>
        </div>
      ) : (
        <p className="text-xs text-slate-500">{data.note ?? 'Datos insuficientes.'}</p>
      ))}
    </div>
  )
}

// ── 4. Puntuación de riesgo ─────────────────────────────────────────

const RISK_BAND: Record<string, { cls: string; ring: string }> = {
  'SEVERO': { cls: 'text-red-300', ring: 'text-red-500' },
  'ALTO': { cls: 'text-amber-300', ring: 'text-amber-500' },
  'MEDIO': { cls: 'text-yellow-300', ring: 'text-yellow-500' },
  'BAJO': { cls: 'text-emerald-300', ring: 'text-emerald-500' },
}

function RiskGauge({ score, band }: Readonly<{ score: number; band: string }>) {
  const R = 40, C = 2 * Math.PI * R
  const dash = (score / 100) * C
  const color = RISK_BAND[band]?.ring ?? 'text-slate-500'
  return (
    <div className="relative w-28 h-28 shrink-0">
      <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
        <circle cx="50" cy="50" r={R} fill="none" stroke="#1e293b" strokeWidth="8" />
        <circle cx="50" cy="50" r={R} fill="none" strokeWidth="8" strokeLinecap="round"
                className={color} stroke="currentColor"
                strokeDasharray={`${dash} ${C}`} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-2xl font-bold font-mono ${RISK_BAND[band]?.cls}`}>{score}</span>
        <span className="text-[9px] text-slate-500">/ 100</span>
      </div>
    </div>
  )
}

function RiskScore({ chain }: Readonly<{ chain: string }>) {
  const [data, setData] = useState<AddressRisk | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function run(address: string) {
    setLoading(true); setError(''); setData(null)
    try {
      const res = await blockchainService.addressRisk(chain, address)
      if (res.error) setError(res.error)
      else setData(res)
    } catch { setError('No se pudo puntuar la dirección.') } finally { setLoading(false) }
  }

  return (
    <div className="space-y-3">
      <AddressBar placeholder="Dirección a evaluar (0x…)" onRun={run} loading={loading} />
      <p className="text-[10px] text-slate-500">Combina exposición a etiquetas de sanciones/mixers/scams (propia y de contrapartes) con patrones on-chain. Heurístico, no atribución de identidad.</p>
      {error && <ErrorNote msg={error} />}
      {data && (
        <div className="bg-slate-900/60 rounded-lg border border-slate-700/60 p-4">
          <div className="flex items-center gap-4 mb-3">
            <RiskGauge score={data.score} band={data.band} />
            <div>
              <p className={`text-lg font-bold ${RISK_BAND[data.band]?.cls}`}>Riesgo {data.band}</p>
              <p className="text-[11px] text-slate-400 mt-0.5">
                {data.flagged_counterparties} contraparte(s) señaladas · {data.counterparties_analyzed} analizadas
              </p>
              {data.self_labels && data.self_labels.length > 0 && (
                <p className="text-[10px] text-slate-500 mt-1">Etiquetas: {data.self_labels.join(', ')}</p>
              )}
            </div>
          </div>
          {data.factors.length > 0 ? (
            <ul className="space-y-1">
              {data.factors.map((f, i) => (
                <li key={i} className="flex items-center gap-2 text-[11px]">
                  <span className="w-8 text-right font-mono text-slate-400">+{f.weight}</span>
                  <span className="text-slate-300">{f.detail}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-emerald-400/80">Sin factores de riesgo detectados en la muestra.</p>
          )}
          <p className="text-[9px] text-slate-600 mt-2">{data.note}</p>
        </div>
      )}
    </div>
  )
}

// ── 5. Aprobaciones ERC-20 ──────────────────────────────────────────

const APPROVAL_STYLE: Record<string, string> = {
  'SEVERO': 'bg-red-500/15 border-red-500/40 text-red-300',
  'ALTO': 'bg-amber-500/15 border-amber-500/40 text-amber-300',
  'MEDIO': 'bg-yellow-500/10 border-yellow-500/30 text-yellow-300',
  'BAJO': 'bg-slate-700/40 border-slate-600 text-slate-400',
}

function Approvals({ chain }: Readonly<{ chain: string }>) {
  const [data, setData] = useState<ApprovalsResult | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function run(address: string) {
    setLoading(true); setError(''); setData(null)
    try {
      const res = await blockchainService.approvals(chain, address)
      if (res.error) setError(res.error)
      else setData(res)
    } catch { setError('No se pudieron leer las aprobaciones.') } finally { setLoading(false) }
  }

  return (
    <div className="space-y-3">
      <AddressBar placeholder="Dirección de la wallet (0x…)" onRun={run} loading={loading} />
      <p className="text-[10px] text-slate-500">Aprobaciones ERC-20 activas. Las ilimitadas a contratos sin verificar son el principal vector de drenaje: revócalas si no las usas.</p>
      {error && <ErrorNote msg={error} />}
      {data && (
        <div className="bg-slate-900/60 rounded-lg border border-slate-700/60 p-4 space-y-2">
          <div className="flex items-center gap-3 text-[11px] flex-wrap">
            <span className="text-slate-300">{data.total} aprobación(es) activas</span>
            {data.unlimited > 0 && <span className="text-amber-300">· {data.unlimited} ilimitadas</span>}
            <span className={`ml-auto px-2 py-0.5 rounded-full border text-[10px] ${APPROVAL_STYLE[data.worst] ?? APPROVAL_STYLE.BAJO}`}>
              Peor: {data.worst}
            </span>
          </div>
          {data.approvals.length === 0 ? (
            <p className="text-xs text-emerald-400/80">Sin aprobaciones activas: la wallet no ha delegado gasto de tokens.</p>
          ) : (
            <div className="space-y-1.5">
              {data.approvals.slice(0, 12).map((a, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px] py-1 border-b border-slate-700/40">
                  <span className={`px-1.5 py-0.5 rounded border text-[9px] font-medium ${APPROVAL_STYLE[a.risk]}`}>{a.risk}</span>
                  <span className="font-mono text-slate-200">{a.token_symbol}</span>
                  <span className="text-slate-500">→ {short(a.spender)}</span>
                  {a.is_unlimited && <span className="text-[9px] text-amber-400">∞</span>}
                  {!a.spender_verified && <span className="text-[9px] text-red-400" title="Contrato sin verificar">⚠ sin verificar</span>}
                  <span className="ml-auto text-[10px] text-slate-500 truncate max-w-[40%]" title={a.reason}>{a.reason}</span>
                </div>
              ))}
            </div>
          )}
          <p className="text-[9px] text-slate-600">{data.note}</p>
        </div>
      )}
    </div>
  )
}

// ── 6. Grafo de entidad ─────────────────────────────────────────────

function EntityGraphView({ chain }: Readonly<{ chain: string }>) {
  const [data, setData] = useState<EntityGraph | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function run(address: string) {
    setLoading(true); setError(''); setData(null)
    try {
      const res = await blockchainService.entityGraph(chain, address)
      if (res.error) setError(res.error)
      else setData(res)
    } catch { setError('No se pudo construir el grafo.') } finally { setLoading(false) }
  }

  const maxStrength = data ? Math.max(...data.nodes.map((n) => n.strength), 1) : 1
  return (
    <div className="space-y-3">
      <AddressBar placeholder="Dirección raíz (0x…)" onRun={run} loading={loading} />
      <p className="text-[10px] text-slate-500">Agrupa direcciones fuertemente conectadas a la raíz por co-movimiento (nº de transferencias). Sugiere control común, no lo prueba.</p>
      {error && <ErrorNote msg={error} />}
      {data && (
        <div className="bg-slate-900/60 rounded-lg border border-slate-700/60 p-4 space-y-3">
          <div className="flex items-center gap-3 text-[11px] flex-wrap">
            <span className="px-2 py-0.5 rounded-full bg-blue-500/15 border border-blue-500/30 text-blue-300">
              Entidad probable: {data.entity_size} direcciones
            </span>
            <span className="text-slate-500">{data.nodes.length} nodos · {data.neighbors_scanned} vecinos escaneados · {data.components} grupos</span>
          </div>
          <div className="space-y-1">
            {data.nodes.slice(0, 14).map((n) => (
              <div key={n.address} className={`flex items-center gap-2 text-[11px] px-2 py-1 rounded ${n.in_entity ? 'bg-blue-500/5' : ''}`}>
                <span className={`font-mono w-32 ${n.is_root ? 'text-white font-bold' : 'text-slate-300'}`}>
                  {n.is_root ? '★ ' : ''}{short(n.address)}
                </span>
                <div className="flex-1 h-2 bg-slate-800 rounded overflow-hidden">
                  <div className={`h-full ${n.in_entity ? 'bg-blue-500/60' : 'bg-slate-600/50'}`}
                       style={{ width: `${(n.strength / maxStrength) * 100}%` }} />
                </div>
                <span className="text-slate-500 w-16 text-right font-mono">{n.degree} conex.</span>
                {n.in_entity && !n.is_root && <span className="text-[9px] text-blue-400">entidad</span>}
              </div>
            ))}
          </div>
          <p className="text-[9px] text-slate-600">{data.note}</p>
        </div>
      )}
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
