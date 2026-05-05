/**
 * pages/BlockchainPage.tsx — Métricas on-chain de Bitcoin y multi-chain.
 *
 * Fuentes:
 *   - BTC histórico: Blockchain.com Charts API (sin auth)
 *   - Multi-chain snapshot: Blockchair API (BTC, ETH, LTC, DOGE, BCH, XRP, ADA, DOT, XLM, XMR)
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  blockchainService,
  METRIC_LABELS,
  MULTICHAIN_SYMBOLS,
  type OnChainMetric,
  type MetricPoint,
  type MultiChainSymbol,
  type MultiChainStatItem,
} from '../services/blockchainService'

// ────────────────────────── Gráfico SVG simple ────────────────────

function SparkLine({ points, color = '#3b82f6' }: { points: MetricPoint[]; color?: string }) {
  if (points.length < 2) return null

  const values = points.map(p => p.value)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1

  const W = 600
  const H = 120
  const PADDING = { top: 8, bottom: 8, left: 4, right: 4 }
  const innerW = W - PADDING.left - PADDING.right
  const innerH = H - PADDING.top - PADDING.bottom

  const toX = (i: number) => PADDING.left + (i / (points.length - 1)) * innerW
  const toY = (v: number) => PADDING.top + (1 - (v - min) / range) * innerH

  const pathD = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${toX(i).toFixed(1)} ${toY(p.value).toFixed(1)}`)
    .join(' ')

  const areaD = `${pathD} L ${toX(points.length - 1).toFixed(1)} ${H} L ${PADDING.left} ${H} Z`

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-28" preserveAspectRatio="none">
      <defs>
        <linearGradient id="lineGradient" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={areaD} fill="url(#lineGradient)" />
      <path d={pathD} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ────────────────────────── Selector de métricas ─────────────────

const METRIC_COLORS: Record<OnChainMetric, string> = {
  active_addresses: '#3b82f6',
  hashrate: '#f59e0b',
  tx_count: '#10b981',
  difficulty: '#f97316',
  mempool_size: '#8b5cf6',
  miners_revenue: '#ec4899',
  transaction_fees: '#14b8a6',
  avg_block_size: '#a3a3a3',
}

const METRICS_ORDER: OnChainMetric[] = [
  'active_addresses',
  'hashrate',
  'tx_count',
  'difficulty',
  'mempool_size',
  'miners_revenue',
  'transaction_fees',
  'avg_block_size',
]

// ────────────────────────── Panel multi-chain (Blockchair) ────────

const MULTICHAIN_COLORS: Record<string, string> = {
  BTC: '#f59e0b', ETH: '#6366f1', LTC: '#a3a3a3', DOGE: '#d97706',
  BCH: '#22c55e', XRP: '#0ea5e9', ADA: '#3b82f6', DOT: '#e879f9',
  XLM: '#38bdf8', XMR: '#f97316',
}

function fmtStatValue(value: number | string | null, unit: string): string {
  if (value === null || value === undefined) return '—'
  const n = typeof value === 'string' ? Number.parseFloat(value) : value
  if (Number.isNaN(n)) return String(value)
  if (unit === '%') return `${n.toFixed(2)}%`
  if (unit === 'USD') return fmtUsd(n)
  return fmtGeneric(n)
}

function fmtUsd(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (n >= 1e3) return `$${(n / 1e3).toFixed(2)}K`
  return `$${n.toFixed(4)}`
}

function fmtGeneric(n: number): string {
  if (n >= 1e12) return `${(n / 1e12).toFixed(3)}T`
  if (n >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (n >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (n >= 1e3) return `${(n / 1e3).toFixed(2)}K`
  return n.toFixed(n < 1 ? 6 : 2)
}

function MultiChainPanel() {
  const [symbol, setSymbol] = useState<MultiChainSymbol>('ETH')
  const [stats, setStats] = useState<MultiChainStatItem[]>([])
  const [meta, setMeta] = useState<{ best_block_time: string | null; best_block_height: number | null; source: string }>({ best_block_time: null, best_block_height: null, source: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const fetch = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await blockchainService.getMultiChainStats(symbol)
      if (res.error) { setError(res.error); setStats([]) }
      else {
        setStats(res.stats)
        setMeta({ best_block_time: res.best_block_time, best_block_height: res.best_block_height, source: res.source })
      }
    } catch {
      setError('Error al cargar estadísticas multi-chain')
    } finally {
      setLoading(false)
    }
  }, [symbol])

  useEffect(() => { fetch() }, [fetch])

  const color = MULTICHAIN_COLORS[symbol] ?? '#6366f1'

  return (
    <div className="mt-8">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold" style={{ backgroundColor: color + '33', color }}>⛓</div>
        <div>
          <h2 className="text-lg font-bold">Estadísticas Multi-chain</h2>
          <p className="text-xs text-gray-400">Snapshot actual · Fuente: Blockchair</p>
        </div>
      </div>

      {/* Selector de chain */}
      <div className="flex flex-wrap gap-2 mb-5">
        {MULTICHAIN_SYMBOLS.map(s => (
          <button
            key={s}
            onClick={() => setSymbol(s)}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors border ${symbol === s ? 'text-white border-transparent' : 'bg-gray-800 text-gray-400 hover:text-white border-gray-700'}`}
            style={symbol === s ? { backgroundColor: MULTICHAIN_COLORS[s] + '33', borderColor: MULTICHAIN_COLORS[s], color: MULTICHAIN_COLORS[s] } : {}}
          >
            {s}
          </button>
        ))}
      </div>

      {loading && (
        <div className="flex justify-center py-10">
          <div className="w-7 h-7 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: color, borderTopColor: 'transparent' }} />
        </div>
      )}

      {error && !loading && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">{error}</div>
      )}

      {!loading && !error && stats.length > 0 && (
        <>
          {meta.best_block_time && (
            <p className="text-xs text-gray-500 mb-3">
              Último bloque: #{meta.best_block_height?.toLocaleString()} · {new Date(meta.best_block_time).toLocaleString('es-ES')}
            </p>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {stats.map(stat => (
              <div key={stat.key} className="bg-gray-800 rounded-xl p-4 border border-gray-700">
                <p className="text-xs text-gray-400 mb-1 truncate">{stat.label}</p>
                <p className="text-lg font-bold font-mono" style={{ color }}>{fmtStatValue(stat.value, stat.unit)}</p>
                {stat.unit && stat.unit !== 'USD' && stat.unit !== '%' && (
                  <p className="text-xs text-gray-500 mt-0.5">{stat.unit}</p>
                )}
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-600 mt-3">Fuente: {meta.source}</p>
        </>
      )}
    </div>
  )
}

// ────────────────────────── Página principal ─────────────────────

export default function BlockchainPage() {
  const [metric, setMetric] = useState<OnChainMetric>('active_addresses')
  const [days, setDays] = useState(30)
  const [data, setData] = useState<MetricPoint[]>([])
  const [metaInfo, setMetaInfo] = useState({ label: '', description: '', source: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [hovered, setHovered] = useState<MetricPoint | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const fetchMetric = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await blockchainService.getMetrics(metric, days)
      if (res.error) {
        setError(res.error)
        setData([])
      } else {
        setData(res.data)
        setMetaInfo({
          label: res.metric_label,
          description: res.description,
          source: res.source,
        })
      }
    } catch {
      setError('Error al cargar las métricas on-chain')
    } finally {
      setLoading(false)
    }
  }, [metric, days])

  useEffect(() => {
    fetchMetric()
  }, [fetchMetric])

  const fmtValue = (v: number) => {
    if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`
    if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`
    if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`
    if (v >= 1e3) return `${(v / 1e3).toFixed(2)}K`
    return v.toFixed(2)
  }

  const latestValue = data.length > 0 ? data[data.length - 1].value : null
  const firstValue = data.length > 0 ? data[0].value : null
  const pct =
    latestValue != null && firstValue != null && firstValue !== 0
      ? ((latestValue - firstValue) / firstValue) * 100
      : null
  const isUp = pct != null && pct >= 0
  const color = METRIC_COLORS[metric]

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-5xl mx-auto">
        {/* Cabecera */}
        <div className="mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-yellow-500/20 flex items-center justify-center text-xl">₿</div>
            <div>
              <h1 className="text-2xl font-bold">Blockchain Analytics</h1>
              <p className="text-gray-400 text-sm">Métricas on-chain de Bitcoin · Solo BTC</p>
            </div>
          </div>
        </div>

        {/* Selector de métricas */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-6">
          {METRICS_ORDER.map(m => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              className={`px-3 py-2 rounded-xl text-xs font-medium text-left transition-colors ${
                metric === m
                  ? 'text-white border'
                  : 'bg-gray-800 text-gray-400 hover:text-white border border-gray-700'
              }`}
              style={metric === m ? { backgroundColor: `${METRIC_COLORS[m]}22`, borderColor: METRIC_COLORS[m] } : {}}
            >
              {METRIC_LABELS[m]}
            </button>
          ))}
        </div>

        {/* Selector de período */}
        <div className="flex gap-2 mb-6">
          {[7, 30, 90, 180, 365].map(d => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                days === d ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
              }`}
            >
              {d === 365 ? '1A' : d === 180 ? '6M' : d === 90 ? '3M' : d === 30 ? '1M' : '7D'}
            </button>
          ))}
        </div>

        {/* Gráfico */}
        <div className="bg-gray-800 rounded-2xl p-6 border border-gray-700">
          {/* Estadísticas */}
          <div className="flex items-start justify-between mb-4">
            <div>
              <p className="text-xs text-gray-400 mb-1">{metaInfo.label || METRIC_LABELS[metric]}</p>
              {latestValue != null && (
                <p className="text-3xl font-bold font-mono">{fmtValue(latestValue)}</p>
              )}
              {pct != null && (
                <p className={`text-sm font-medium mt-1 ${isUp ? 'text-green-400' : 'text-red-400'}`}>
                  {isUp ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}% en {days}d
                </p>
              )}
              {metaInfo.description && (
                <p className="text-xs text-gray-500 mt-1 max-w-md">{metaInfo.description}</p>
              )}
            </div>
            {hovered && (
              <div className="text-right text-sm">
                <p className="text-gray-400 text-xs">
                  {new Date(hovered.timestamp * 1000).toLocaleDateString('es-ES')}
                </p>
                <p className="font-mono font-bold">{fmtValue(hovered.value)}</p>
              </div>
            )}
          </div>

          {loading && (
            <div className="flex justify-center py-16">
              <div
                className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin"
                style={{ borderColor: color, borderTopColor: 'transparent' }}
              />
            </div>
          )}

          {error && !loading && (
            <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
              {error}
            </div>
          )}

          {!loading && !error && data.length === 1 && (
            <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-xl p-4 text-yellow-400 text-sm text-center py-8">
              Solo hay 1 dato disponible para el período de 7 días en esta métrica.
              <br />
              <span className="text-yellow-500/70 text-xs">Selecciona 1M o más para ver la gráfica.</span>
            </div>
          )}

          {!loading && !error && data.length > 1 && (
            <div
              ref={containerRef}
              className="relative cursor-crosshair"
              onMouseMove={e => {
                if (!containerRef.current) return
                const rect = containerRef.current.getBoundingClientRect()
                const pct = (e.clientX - rect.left) / rect.width
                const idx = Math.round(pct * (data.length - 1))
                const clamped = Math.max(0, Math.min(data.length - 1, idx))
                setHovered(data[clamped])
              }}
              onMouseLeave={() => setHovered(null)}
            >
              <SparkLine points={data} color={color} />
            </div>
          )}

          {!loading && !error && data.length === 0 && (
            <div className="py-12 text-center text-gray-500 text-sm">
              No hay datos disponibles para esta métrica y período.
            </div>
          )}

          {metaInfo.source && (
            <p className="text-xs text-gray-600 mt-3">
              Fuente: {metaInfo.source}
            </p>
          )}
        </div>

        {/* Tabla de últimos valores */}
        {data.length > 0 && !loading && (
          <div className="mt-6 bg-gray-800 rounded-2xl border border-gray-700 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-700">
              <h3 className="text-sm font-medium text-gray-300">Últimos 10 valores</h3>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-400 border-b border-gray-700">
                  <th className="text-left px-4 py-2">Fecha</th>
                  <th className="text-right px-4 py-2">{METRIC_LABELS[metric]}</th>
                  <th className="text-right px-4 py-2">Var. diaria</th>
                </tr>
              </thead>
              <tbody>
                {data.slice(-10).reverse().map((p, i, arr) => {
                  const prev = arr[i + 1]
                  const change = prev ? ((p.value - prev.value) / prev.value) * 100 : null
                  return (
                    <tr key={p.timestamp} className="border-b border-gray-700/40 hover:bg-gray-700/30">
                      <td className="px-4 py-2 text-gray-400">
                        {new Date(p.timestamp * 1000).toLocaleDateString('es-ES')}
                      </td>
                      <td className="text-right px-4 py-2 font-mono">{fmtValue(p.value)}</td>
                      <td className={`text-right px-4 py-2 font-mono text-xs ${change == null ? '' : change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {change != null ? `${change >= 0 ? '+' : ''}${change.toFixed(2)}%` : '—'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Panel multi-chain (Blockchair) */}
        <MultiChainPanel />

      </div>
    </div>
  )
}
