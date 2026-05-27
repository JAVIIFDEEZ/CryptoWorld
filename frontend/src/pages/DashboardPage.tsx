/**
 * pages/DashboardPage.tsx — Panel de inicio de la aplicación.
 *
 * Responsabilidad: resumen ejecutivo del mercado. Muestra métricas
 * globales, indicadores de sentimiento y los activos con mayor
 * movimiento en las últimas 24h. Para explorar el catálogo completo,
 * el usuario navega a /market.
 */

import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import { marketService, type MarketOverview } from '@/services/marketService'
import * as watchlistService from '@/services/watchlistService'
import type { WatchlistItem } from '@/services/watchlistService'
import FearGreedGauge from '@/components/FearGreedGauge'

function DashboardPage() {
  const { user } = useAuth()
  const [assets, setAssets] = useState<CryptoAsset[]>([])
  const [overview, setOverview] = useState<MarketOverview | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([])

  useEffect(() => {
    async function load() {
      const [assetsData, overviewData, watchlistData] = await Promise.allSettled([
        analysisService.getAssets(),
        marketService.getMarketOverview(),
        watchlistService.getWatchlist(),
      ])
      if (assetsData.status === 'fulfilled') setAssets(assetsData.value)
      if (overviewData.status === 'fulfilled') setOverview(overviewData.value)
      if (watchlistData.status === 'fulfilled') setWatchlist(watchlistData.value)
      setIsLoading(false)
    }
    load()
  }, [])

  // Top 5 activos por variación absoluta en 24h
  const topMovers = useMemo(() => {
    return [...assets]
      .sort(
        (a, b) =>
          Math.abs(parseFloat(b.price_change_24h ?? '0')) -
          Math.abs(parseFloat(a.price_change_24h ?? '0')),
      )
      .slice(0, 5)
  }, [assets])

  const bullishCount = assets.filter((a) => a.is_bullish_24h).length
  const bearishCount = assets.length - bullishCount

  return (
    <div className="space-y-8">
      {/* Cabecera */}
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-slate-400 text-sm mt-1">
          Bienvenido de nuevo,{' '}
          <span className="text-slate-200 font-medium">{user?.username}</span>
        </p>
      </div>

      {/* Métricas globales del mercado */}
      {overview && (
        <section>
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
            Mercado global
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <GlobalCard
              label="Cap. total"
              value={`$${(parseFloat(overview.total_market_cap_usd) / 1e12).toFixed(2)}T`}
            />
            <GlobalCard
              label="Volumen 24h"
              value={`$${(parseFloat(overview.total_volume_24h_usd) / 1e9).toFixed(0)}B`}
            />
            <GlobalCard
              label="Dominancia BTC"
              value={`${parseFloat(overview.btc_dominance_pct).toFixed(1)}%`}
            />
            <div className="bg-slate-800/60 rounded-xl border border-slate-700 px-5 py-4 flex flex-col items-center justify-center">
              <p className="text-slate-500 text-xs mb-2 self-start">Fear & Greed</p>
              <FearGreedGauge value={overview.fear_greed_index} size={110} />
            </div>
          </div>
        </section>
      )}

      {/* Resumen del catálogo */}
      <section>
        <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
          Catálogo
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <SummaryCard label="Activos monitorizados" value={String(assets.length)} />
          <SummaryCard
            label="Alcistas (24h)"
            value={String(bullishCount)}
            sub={assets.length ? `${((bullishCount / assets.length) * 100).toFixed(0)}% del total` : '—'}
            positive
          />
          <SummaryCard
            label="Bajistas (24h)"
            value={String(bearishCount)}
            sub={assets.length ? `${((bearishCount / assets.length) * 100).toFixed(0)}% del total` : '—'}
            negative
          />
        </div>
      </section>

      {/* Top movers */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
            Mayor movimiento (24h)
          </h2>
          <Link
            to="/market"
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            Ver mercado completo →
          </Link>
        </div>

        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
          {isLoading ? (
            <div className="px-6 py-10 text-center text-slate-400 text-sm animate-pulse">
              Cargando...
            </div>
          ) : topMovers.length === 0 ? (
            <div className="px-6 py-10 text-center text-slate-500 text-sm">
              Sin datos. Ejecuta una sincronización desde el panel de administración.
            </div>
          ) : (
            <div className="divide-y divide-slate-700/50">
              {topMovers.map((asset) => (
                <MoverRow key={asset.id} asset={asset} />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Watchlist personal */}
      {watchlist.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              ★ Mis favoritos
            </h2>
            <Link
              to="/market"
              className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
            >
              Gestionar →
            </Link>
          </div>
          <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
            <div className="divide-y divide-slate-700/50">
              {watchlist.map((item) => {
                const change = Number.parseFloat(item.price_change_24h)
                const isPositive = item.is_bullish_24h
                return (
                  <div
                    key={item.symbol}
                    className="flex items-center justify-between px-5 py-3 hover:bg-slate-700/30 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      {item.logo_url ? (
                        <img src={item.logo_url} alt={item.symbol} className="w-7 h-7 rounded-full" />
                      ) : (
                        <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-yellow-400">
                          {item.symbol.slice(0, 2)}
                        </div>
                      )}
                      <div>
                        <p className="text-sm font-medium text-white">{item.symbol}</p>
                        <p className="text-xs text-slate-500 truncate max-w-[120px]">{item.name}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-5">
                      <p className="text-sm font-mono text-white tabular-nums hidden sm:block">
                        ${Number.parseFloat(item.current_price).toLocaleString('es-ES', { minimumFractionDigits: 2 })}
                      </p>
                      <p className={`text-sm font-mono font-semibold tabular-nums w-20 text-right ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                        {isPositive ? '+' : ''}{change.toFixed(2)}%
                      </p>
                      <Link
                        to={`/assets/${item.symbol}`}
                        className="text-blue-400 hover:text-blue-300 text-xs transition-colors"
                      >
                        Ver →
                      </Link>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}

// ── Subcomponentes ─────────────────────────────────────────────────

function GlobalCard({
  label,
  value,
  sub,
  highlight,
}: {
  label: string
  value: string
  sub?: string
  highlight?: 'green' | 'red' | 'neutral'
}) {
  const valueClass =
    highlight === 'green'
      ? 'text-green-400'
      : highlight === 'red'
        ? 'text-red-400'
        : 'text-blue-400'

  return (
    <div className="bg-slate-800/60 rounded-xl border border-slate-700 px-5 py-4">
      <p className="text-slate-500 text-xs mb-1">{label}</p>
      <p className={`text-xl font-bold font-mono ${valueClass}`}>{value}</p>
      {sub && <p className="text-slate-500 text-xs mt-1">{sub}</p>}
    </div>
  )
}

function SummaryCard({
  label,
  value,
  sub,
  positive,
  negative,
}: {
  label: string
  value: string
  sub?: string
  positive?: boolean
  negative?: boolean
}) {
  const valueClass = positive ? 'text-green-400' : negative ? 'text-red-400' : 'text-white'

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 px-5 py-4">
      <p className="text-slate-400 text-xs mb-1">{label}</p>
      <p className={`text-2xl font-bold ${valueClass}`}>{value}</p>
      {sub && <p className="text-slate-500 text-xs mt-1">{sub}</p>}
    </div>
  )
}

function MoverRow({ asset }: { asset: CryptoAsset }) {
  const change = parseFloat(asset.price_change_24h ?? '0')
  const isPositive = change >= 0

  return (
    <div className="flex items-center justify-between px-5 py-3 hover:bg-slate-700/30 transition-colors">
      <div className="flex items-center gap-3">
        {asset.logo_url ? (
          <img src={asset.logo_url} alt={asset.symbol} className="w-8 h-8 rounded-full" />
        ) : (
          <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-blue-400">
            {asset.symbol.slice(0, 2)}
          </div>
        )}
        <div>
          <p className="text-sm font-medium text-white">{asset.symbol}</p>
          <p className="text-xs text-slate-500">{asset.name}</p>
        </div>
      </div>

      <div className="flex items-center gap-6">
        <p className="text-sm font-mono text-white tabular-nums hidden sm:block">
          ${parseFloat(asset.current_price).toLocaleString('es-ES', { minimumFractionDigits: 2 })}
        </p>
        <p
          className={`text-sm font-mono font-semibold tabular-nums w-20 text-right ${
            isPositive ? 'text-green-400' : 'text-red-400'
          }`}
        >
          {isPositive ? '+' : ''}
          {change.toFixed(2)}%
        </p>
        <Link
          to={`/assets/${asset.symbol}`}
          className="text-blue-400 hover:text-blue-300 text-xs transition-colors"
        >
          Ver →
        </Link>
      </div>
    </div>
  )
}

export default DashboardPage
