/**
 * pages/BlockchainPage.tsx — Explorador on-chain multi-chain.
 *
 * Arquitectura de fuentes:
 *   - Blockchair API   → estadísticas actuales (snapshot) para las 10 chains
 *   - Blockchain.com   → series históricas de 8 métricas (solo BTC, gratuito)
 *
 * UX: el usuario navega por chain; Blockchair es la fuente principal;
 * cuando se selecciona BTC se muestra además la sección de gráficos históricos.
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
import MultiChainComparePanel from '@/components/blockchain/MultiChainComparePanel'
import WalletExplorerPanel from '@/components/blockchain/WalletExplorerPanel'
import NetworkHealthPanel from '@/components/blockchain/NetworkHealthPanel'
import WhaleMovementsPanel from '@/components/blockchain/WhaleMovementsPanel'
import OnChainPressurePanel from '@/components/blockchain/OnChainPressurePanel'
import WatchlistPanel from '@/components/blockchain/WatchlistPanel'

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

// ────────────────────────── Colores por chain ────────────────────

const CHAIN_COLORS: Record<string, string> = {
  BTC: '#f59e0b', ETH: '#6366f1', LTC: '#a3a3a3', DOGE: '#d97706',
  BCH: '#22c55e', XRP: '#0ea5e9', ADA: '#3b82f6', DOT: '#e879f9',
  XLM: '#38bdf8', XMR: '#f97316',
}

// ────────────────────────── Helpers de formato ───────────────────

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

function fmtValue(v: number): string {
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}T`
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`
  if (v >= 1e3) return `${(v / 1e3).toFixed(2)}K`
  return v.toFixed(2)
}

// ────────────────────────── Página principal ─────────────────────

type BlockchainView = 'network' | 'whales' | 'wallets' | 'market'

const BLOCKCHAIN_TABS: { key: BlockchainView; label: string; icon: string }[] = [
  { key: 'network', label: 'Red y gas', icon: '⛽' },
  { key: 'whales', label: 'Movimientos', icon: '🐋' },
  { key: 'wallets', label: 'Wallets', icon: '🔍' },
  { key: 'market', label: 'Mercado on-chain', icon: '📊' },
]

export default function BlockchainPage() {
  const [view, setView] = useState<BlockchainView>('network')
  const [chain, setChain] = useState<MultiChainSymbol>('BTC')

  // ── Blockchair snapshot ──
  const [snapStats, setSnapStats] = useState<MultiChainStatItem[]>([])
  const [snapMeta, setSnapMeta] = useState<{
    best_block_time: string | null
    best_block_height: number | null
    source: string
  }>({ best_block_time: null, best_block_height: null, source: '' })
  const [snapLoading, setSnapLoading] = useState(false)
  const [snapError, setSnapError] = useState('')

  // ── Blockchain.com historical (BTC only) ──
  const [metric, setMetric] = useState<OnChainMetric>('active_addresses')
  const [days, setDays] = useState(30)
  const [chartData, setChartData] = useState<MetricPoint[]>([])
  const [chartMeta, setChartMeta] = useState({ label: '', description: '', source: '' })
  const [chartLoading, setChartLoading] = useState(false)
  const [chartError, setChartError] = useState('')
  const [hovered, setHovered] = useState<MetricPoint | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  const color = CHAIN_COLORS[chain] ?? '#6366f1'
  const chartColor = METRIC_COLORS[metric]

  // Cargar snapshot Blockchair al cambiar chain
  const fetchSnapshot = useCallback(async () => {
    setSnapLoading(true)
    setSnapError('')
    try {
      const res = await blockchainService.getMultiChainStats(chain)
      if (res.error) {
        setSnapError(res.error)
        setSnapStats([])
      } else {
        setSnapStats(res.stats)
        setSnapMeta({
          best_block_time: res.best_block_time,
          best_block_height: res.best_block_height,
          source: res.source,
        })
      }
    } catch {
      setSnapError('Error al cargar estadísticas de la blockchain')
    } finally {
      setSnapLoading(false)
    }
  }, [chain])

  useEffect(() => { fetchSnapshot() }, [fetchSnapshot])

  // Cargar gráfico Blockchain.com (solo cuando chain == BTC)
  const fetchChart = useCallback(async () => {
    if (chain !== 'BTC') return
    setChartLoading(true)
    setChartError('')
    try {
      const res = await blockchainService.getMetrics(metric, days)
      if (res.error) {
        setChartError(res.error)
        setChartData([])
      } else {
        setChartData(res.data)
        setChartMeta({ label: res.metric_label, description: res.description, source: res.source })
      }
    } catch {
      setChartError('Error al cargar las métricas históricas')
    } finally {
      setChartLoading(false)
    }
  }, [chain, metric, days])

  useEffect(() => { fetchChart() }, [fetchChart])

  const latestValue = chartData.length > 0 ? chartData[chartData.length - 1].value : null
  const firstValue = chartData.length > 0 ? chartData[0].value : null
  const pct =
    latestValue != null && firstValue != null && firstValue !== 0
      ? ((latestValue - firstValue) / firstValue) * 100
      : null
  const isUp = pct != null && pct >= 0

  return (
    <div>

        {/* ── Cabecera ── */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white">Blockchain Analytics</h1>
          <p className="text-slate-400 text-sm mt-1">
            Estadísticas on-chain en tiempo real · 10 blockchains
          </p>
        </div>

        {/* ── Sub-navegación por submódulos ── */}
        <div className="flex flex-wrap gap-1 mb-6 border-b border-slate-700">
          {BLOCKCHAIN_TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setView(t.key)}
              className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
                view === t.key ? 'border-blue-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <span className="mr-1.5">{t.icon}</span>{t.label}
            </button>
          ))}
        </div>

        {/* ── Red y gas (Blockscout) ── */}
        {view === 'network' && <NetworkHealthPanel />}

        {/* ── Movimientos / ballenas: presión de exchanges + feed (Blockscout) ── */}
        {view === 'whales' && (
          <>
            <OnChainPressurePanel />
            <WhaleMovementsPanel />
          </>
        )}

        {/* ── Wallets: explorador + vigilancia (Blockscout) ── */}
        {view === 'wallets' && (
          <>
            <WalletExplorerPanel />
            <WatchlistPanel />
          </>
        )}

        {/* ── Mercado on-chain: comparador + estadísticas por cadena ── */}
        {view === 'market' && (
          <>
        {/* ── Selector de chain ── */}
        <div className="flex flex-wrap gap-2 mb-6">
          {MULTICHAIN_SYMBOLS.map(s => (
            <button
              key={s}
              onClick={() => setChain(s)}
              className={`px-4 py-2 rounded-xl text-sm font-bold transition-colors border ${
                chain === s ? 'text-white border-transparent' : 'bg-slate-800 text-slate-400 hover:text-white border-slate-700'
              }`}
              style={chain === s ? { backgroundColor: CHAIN_COLORS[s] + '33', borderColor: CHAIN_COLORS[s], color: CHAIN_COLORS[s] } : {}}
            >
              {s}
            </button>
          ))}
        </div>

        {/* ── Comparador multi-cadena (3D/2D) ── */}
        <div className="mb-6">
          <MultiChainComparePanel />
        </div>

        {/* ── Snapshot Blockchair ── */}
        <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div
                className="w-9 h-9 rounded-xl flex items-center justify-center text-sm font-bold"
                style={{ backgroundColor: color + '33', color }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
              </div>
              <div>
                <h2 className="text-lg font-bold">{chain} — Estadísticas actuales</h2>
                <p className="text-xs text-slate-400">Snapshot · Fuente: Blockchair</p>
              </div>
            </div>
            <button
              onClick={fetchSnapshot}
              disabled={snapLoading}
              className="text-xs text-slate-400 hover:text-white px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 transition-colors disabled:opacity-50"
            >
              ↻ Actualizar
            </button>
          </div>

          {snapMeta.best_block_time && (
            <p className="text-xs text-slate-500 mb-4">
              Último bloque: #{snapMeta.best_block_height?.toLocaleString()} ·{' '}
              {new Date(snapMeta.best_block_time).toLocaleString('es-ES')}
            </p>
          )}

          {snapLoading && (
            <div className="flex justify-center py-10">
              <div
                className="w-7 h-7 border-2 rounded-full animate-spin"
                style={{ borderColor: color, borderTopColor: 'transparent' }}
              />
            </div>
          )}

          {snapError && !snapLoading && (
            <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
              {snapError}
            </div>
          )}

          {!snapLoading && !snapError && snapStats.length > 0 && (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                {snapStats.map(stat => (
                  <div key={stat.key} className="bg-slate-700/50 rounded-xl p-4 border border-slate-600/50">
                    <p className="text-xs text-slate-400 mb-1 truncate">{stat.label}</p>
                    <p className="text-lg font-bold font-mono" style={{ color }}>
                      {fmtStatValue(stat.value, stat.unit)}
                    </p>
                    {stat.unit && stat.unit !== 'USD' && stat.unit !== '%' && (
                      <p className="text-xs text-slate-500 mt-0.5">{stat.unit}</p>
                    )}
                  </div>
                ))}
              </div>
              <p className="text-xs text-slate-600 mt-3">Fuente: {snapMeta.source}</p>
            </>
          )}
        </div>

        {/* ── Sección histórica BTC (solo si chain == BTC) ── */}
        {chain === 'BTC' && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <div className="w-2 h-2 rounded-full bg-yellow-500" />
              <h2 className="text-base font-semibold text-slate-200">
                Histórico BTC — Series temporales
              </h2>
              <span className="text-xs text-slate-500 ml-1">Fuente: Blockchain.com</span>
            </div>

            {/* Selector de métricas */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-4">
              {METRICS_ORDER.map(m => (
                <button
                  key={m}
                  onClick={() => setMetric(m)}
                  className={`px-3 py-2 rounded-xl text-xs font-medium text-left transition-colors ${
                    metric === m
                      ? 'text-white border'
                      : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
                  }`}
                  style={metric === m ? { backgroundColor: `${chartColor}22`, borderColor: chartColor } : {}}
                >
                  {METRIC_LABELS[m]}
                </button>
              ))}
            </div>

            {/* Selector de período */}
            <div className="flex gap-2 mb-4">
              {[7, 30, 90, 180, 365].map(d => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium ${
                    days === d ? 'bg-yellow-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'
                  }`}
                >
                  {d === 365 ? '1A' : d === 180 ? '6M' : d === 90 ? '3M' : d === 30 ? '1M' : '7D'}
                </button>
              ))}
            </div>

            {/* Gráfico */}
            <div className="bg-slate-800 rounded-xl p-6 border border-slate-700">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <p className="text-xs text-slate-400 mb-1">{chartMeta.label || METRIC_LABELS[metric]}</p>
                  {latestValue != null && (
                    <p className="text-3xl font-bold font-mono">{fmtValue(latestValue)}</p>
                  )}
                  {pct != null && (
                    <p className={`text-sm font-medium mt-1 ${isUp ? 'text-green-400' : 'text-red-400'}`}>
                      {isUp ? '▲' : '▼'} {Math.abs(pct).toFixed(2)}% en {days}d
                    </p>
                  )}
                  {chartMeta.description && (
                    <p className="text-xs text-slate-500 mt-1 max-w-md">{chartMeta.description}</p>
                  )}
                </div>
                {hovered && (
                  <div className="text-right text-sm">
                    <p className="text-slate-400 text-xs">
                      {new Date(hovered.timestamp * 1000).toLocaleDateString('es-ES')}
                    </p>
                    <p className="font-mono font-bold">{fmtValue(hovered.value)}</p>
                  </div>
                )}
              </div>

              {chartLoading && (
                <div className="flex justify-center py-16">
                  <div
                    className="w-8 h-8 border-2 border-t-transparent rounded-full animate-spin"
                    style={{ borderColor: chartColor, borderTopColor: 'transparent' }}
                  />
                </div>
              )}

              {chartError && !chartLoading && (
                <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
                  {chartError}
                </div>
              )}

              {!chartLoading && !chartError && chartData.length === 1 && (
                <div className="bg-yellow-900/20 border border-yellow-700/50 rounded-xl p-4 text-yellow-400 text-sm text-center py-8">
                  Solo hay 1 dato disponible para el período de 7 días en esta métrica.
                  <br />
                  <span className="text-yellow-500/70 text-xs">Selecciona 1M o más para ver la gráfica.</span>
                </div>
              )}

              {!chartLoading && !chartError && chartData.length > 1 && (
                <div
                  ref={containerRef}
                  className="relative cursor-crosshair"
                  onMouseMove={e => {
                    if (!containerRef.current) return
                    const rect = containerRef.current.getBoundingClientRect()
                    const pct = (e.clientX - rect.left) / rect.width
                    const idx = Math.round(pct * (chartData.length - 1))
                    const clamped = Math.max(0, Math.min(chartData.length - 1, idx))
                    setHovered(chartData[clamped])
                  }}
                  onMouseLeave={() => setHovered(null)}
                >
                  <SparkLine points={chartData} color={chartColor} />
                </div>
              )}

              {!chartLoading && !chartError && chartData.length === 0 && (
                <div className="py-12 text-center text-slate-500 text-sm">
                  No hay datos disponibles para esta métrica y período.
                </div>
              )}

              {chartMeta.source && (
                <p className="text-xs text-slate-600 mt-3">Fuente: {chartMeta.source}</p>
              )}
            </div>

            {/* Tabla de últimos valores */}
            {chartData.length > 0 && !chartLoading && (
              <div className="mt-4 bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
                <div className="px-4 py-3 border-b border-slate-700">
                  <h3 className="text-sm font-medium text-slate-300">Últimos 10 valores</h3>
                </div>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-slate-400 border-b border-slate-700">
                      <th className="text-left px-4 py-2">Fecha</th>
                      <th className="text-right px-4 py-2">{METRIC_LABELS[metric]}</th>
                      <th className="text-right px-4 py-2">Var. diaria</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chartData.slice(-10).reverse().map((p, i, arr) => {
                      const prev = arr[i + 1]
                      const change = prev ? ((p.value - prev.value) / prev.value) * 100 : null
                      return (
                        <tr key={p.timestamp} className="border-b border-slate-700/40 hover:bg-slate-700/30">
                          <td className="px-4 py-2 text-slate-400">
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
          </div>
        )}
          </>
        )}

    </div>
  )
}
