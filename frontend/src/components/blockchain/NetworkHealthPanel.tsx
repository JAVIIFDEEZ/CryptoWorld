/**
 * components/blockchain/NetworkHealthPanel.tsx — Salud de red y rastreador de gas.
 *
 * Muestra el estado de una cadena (Ethereum, Base, Optimism…): precios de gas
 * (lento/medio/rápido en Gwei) con un aviso de gas barato/normal/caro específico
 * por red, utilización de la red, tiempo de bloque y precio del nativo. Datos
 * reales vía Blockscout (`/stats`). Responde a "¿es buen momento para operar?".
 */

import { useEffect, useState } from 'react'
import {
  blockchainService,
  type ChainHealth,
  type ChainMetricHistory,
  type WalletChain,
} from '@/services/blockchainService'

const GAS_STYLE: Record<ChainHealth['gas_level'], { chip: string; label: string }> = {
  cheap: { chip: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30', label: '● Gas barato' },
  normal: { chip: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30', label: '● Gas normal' },
  high: { chip: 'bg-red-500/15 text-red-300 border-red-500/30', label: '● Gas caro' },
  unknown: { chip: 'bg-slate-700/40 text-slate-400 border-slate-600/40', label: '○ Sin datos' },
}

function fmtBig(n: string | null): string {
  if (!n) return '—'
  const v = Number(n)
  if (!isFinite(v)) return n
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`
  return String(v)
}

export default function NetworkHealthPanel() {
  const [chains, setChains] = useState<WalletChain[]>([])
  const [chain, setChain] = useState('ethereum')
  const [data, setData] = useState<ChainHealth | null>(null)
  const [history, setHistory] = useState<ChainMetricHistory | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    blockchainService.getWalletChains().then(setChains).catch(() => { /* sin redes */ })
  }, [])

  useEffect(() => {
    setLoading(true)
    blockchainService.getChainHealth(chain)
      .then((d) => setData(d.error ? null : d))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [chain])

  // Serie de gas del almacén propio. Es lo que convierte «12 Gwei» en algo
  // interpretable: un número suelto no dice si eso es mucho o poco.
  useEffect(() => {
    blockchainService.getChainHistory(chain, 'gas_average', 7)
      .then(setHistory)
      .catch(() => setHistory(null))
  }, [chain])

  const gas = data ? GAS_STYLE[data.gas_level] : GAS_STYLE.unknown
  const series = history?.points ?? []

  return (
    <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 mb-6">
      <div className="flex items-center flex-wrap gap-2 mb-1">
        <span className="text-cyan-400">⛽</span>
        <h2 className="text-lg font-bold text-white">Salud de red y gas</h2>
        <select
          value={chain}
          onChange={(e) => setChain(e.target.value)}
          className="ml-auto bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
        >
          {(chains.length ? chains : [{ slug: 'ethereum', name: 'Ethereum' } as WalletChain]).map((c) => (
            <option key={c.slug} value={c.slug}>{c.name}</option>
          ))}
        </select>
      </div>

      {loading && <p className="text-slate-500 text-sm mt-3">Cargando…</p>}

      {!loading && !data && <p className="text-slate-500 text-sm mt-3">No se pudo obtener el estado de la red.</p>}

      {!loading && data?.stale && (
        <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2">
          <p className="text-[11px] text-amber-300">
            ⚠ Datos del almacén propio, no en vivo
            {data.data_age_seconds != null && ` · ${Math.round(data.data_age_seconds / 60)} min de antigüedad`}
          </p>
          <p className="text-[10px] text-amber-200/70 mt-0.5">{data.note}</p>
        </div>
      )}

      {!loading && data && (
        <div className="mt-3 space-y-4">
          {/* Gas */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400 uppercase">Precio de gas ({data.gas_unit})</span>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${gas.chip}`}>{gas.label}</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <GasTier label="Lento" value={data.gas_slow} tone="text-slate-300" />
              <GasTier label="Medio" value={data.gas_average} tone="text-cyan-300" />
              <GasTier label="Rápido" value={data.gas_fast} tone="text-amber-300" />
            </div>
            <p className="text-[11px] text-slate-400 mt-2">{data.gas_text}</p>

            {/* De dónde sale el veredicto. Un juicio sin su base no es
                interpretable, y «percentil de su propia historia» y «umbral
                fijo de hace años» no merecen la misma confianza. */}
            {data.gas_basis === 'fixed' && (
              <p className="text-[10px] text-slate-600 mt-1">
                Veredicto por umbral fijo: aún no hay suficiente histórico propio
                de esta red para compararlo contra sí misma.
              </p>
            )}
            {data.gas_percentile && (
              <p className="text-[10px] text-slate-500 mt-1">
                Rango de los últimos {data.gas_percentile.days} días:{' '}
                {data.gas_percentile.min}–{data.gas_percentile.max} Gwei
                (mediana {data.gas_percentile.median}) sobre{' '}
                {data.gas_percentile.n_points} lecturas.
              </p>
            )}

            <GasSparkline points={series} />
          </div>

          {/* Métricas de red */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Metric label="Utilización" value={data.network_utilization_pct != null ? `${data.network_utilization_pct.toFixed(1)}%` : '—'} />
            <Metric label="Tiempo bloque" value={data.block_time_sec != null ? `${data.block_time_sec}s` : '—'} />
            <Metric label={`Precio ${data.native_symbol}`} value={data.coin_price_usd != null ? `$${data.coin_price_usd.toLocaleString()}` : '—'}
              sub={data.coin_price_change_pct != null ? `${data.coin_price_change_pct >= 0 ? '+' : ''}${data.coin_price_change_pct.toFixed(2)}%` : undefined}
              subTone={(data.coin_price_change_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'} />
            <Metric label="Tx hoy" value={fmtBig(data.transactions_today)} />
          </div>

          <p className="text-[10px] text-slate-600">
            Totales de red: {fmtBig(data.total_transactions)} tx · {fmtBig(data.total_blocks)} bloques · {fmtBig(data.total_addresses)} direcciones. Datos en vivo de Blockscout.
          </p>
        </div>
      )}
    </div>
  )
}

function GasTier({ label, value, tone }: Readonly<{ label: string; value: number | null; tone: string }>) {
  return (
    <div className="bg-slate-900/50 rounded-lg border border-slate-700/60 p-2 text-center">
      <p className="text-[10px] text-slate-500 uppercase">{label}</p>
      <p className={`text-lg font-bold font-mono ${tone}`}>{value != null ? value.toLocaleString(undefined, { maximumFractionDigits: 3 }) : '—'}</p>
    </div>
  )
}

function Metric({ label, value, sub, subTone }: Readonly<{ label: string; value: string; sub?: string; subTone?: string }>) {
  return (
    <div className="bg-slate-900/40 rounded-lg border border-slate-700/50 p-2">
      <p className="text-[10px] text-slate-500 uppercase">{label}</p>
      <p className="text-sm font-bold font-mono text-white">{value}</p>
      {sub && <p className={`text-[10px] font-mono ${subTone ?? 'text-slate-500'}`}>{sub}</p>}
    </div>
  )
}

/**
 * Minigráfica del gas de los últimos días.
 *
 * Deliberadamente austera —SVG inline, sin librería— porque su única función es
 * dar CONTEXTO a un número: ver que 12 Gwei viene de bajar desde 40 dice más
 * que cualquier etiqueta. Mientras el almacén se llena no dibuja nada en vez de
 * pintar cuatro puntos como si fueran una tendencia.
 */
function GasSparkline({ points }: Readonly<{ points: { t: number; v: number }[] }>) {
  if (points.length < 12) {
    return (
      <p className="text-[10px] text-slate-600 mt-2">
        El histórico propio aún se está llenando ({points.length} lecturas): en unas
        horas esta zona mostrará la evolución del gas.
      </p>
    )
  }

  const values = points.map((p) => p.v)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const w = 100
  const h = 24
  const path = points
    .map((p, i) => {
      const x = (i / (points.length - 1)) * w
      const y = h - ((p.v - min) / span) * h
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`
    })
    .join(' ')

  return (
    <div className="mt-2">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-6" role="img"
        aria-label={`Evolución del gas: entre ${min} y ${max} Gwei`}>
        <path d={path} fill="none" stroke="#22d3ee" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="flex justify-between text-[9px] text-slate-600">
        <span>{min} Gwei</span>
        <span>{points.length} lecturas</span>
        <span>{max} Gwei</span>
      </div>
    </div>
  )
}
