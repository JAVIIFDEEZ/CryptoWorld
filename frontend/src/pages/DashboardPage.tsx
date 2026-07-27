/**
 * pages/DashboardPage.tsx — Panel de inicio de la aplicación.
 *
 * Responsabilidad: resumen ejecutivo del mercado. Muestra métricas
 * globales, el índice de sentimiento como medidor, el estado del
 * catálogo y los activos con mayores subidas/bajadas en 24h, con un
 * minigráfico de tendencia por activo. Para explorar el catálogo
 * completo, el usuario navega a /market.
 */

import { useState, useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import { marketService, type MarketOverview } from '@/services/marketService'
import { getWatchlist, type WatchlistItem } from '@/services/watchlistService'
import { useCurrency } from '@/hooks/useCurrency'
import StatCard from '@/components/ui/StatCard'
import Gauge from '@/components/ui/Gauge'
import Sparkline from '@/components/ui/Sparkline'
import EmptyState from '@/components/ui/EmptyState'
import DeltaChip from '@/components/ui/DeltaChip'
import { SkeletonRow } from '@/components/ui/Skeleton'
import { useDashboardLayout, WIDGET_LABELS } from '@/hooks/useDashboardLayout'
import { useTranslation } from 'react-i18next'

function fearGreedLabel(v: number): string {
  if (v >= 75) return 'Codicia extrema'
  if (v >= 55) return 'Codicia'
  if (v >= 45) return 'Neutral'
  if (v >= 25) return 'Miedo'
  return 'Miedo extremo'
}

function greetingKey(): string {
  const h = new Date().getHours()
  if (h < 6) return 'dashboard.greetingEvening'
  if (h < 12) return 'dashboard.greetingMorning'
  if (h < 20) return 'dashboard.greetingAfternoon'
  return 'dashboard.greetingEvening'
}

function DashboardPage() {
  const { user } = useAuth()
  const { formatCompact } = useCurrency()
  const [assets, setAssets] = useState<CryptoAsset[]>([])
  const [overview, setOverview] = useState<MarketOverview | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [sparks, setSparks] = useState<Record<string, number[]>>({})
  const [watchlistItems, setWatchlistItems] = useState<WatchlistItem[]>([])
  const { layout, toggle, move, reset } = useDashboardLayout()
  const { t } = useTranslation()
  const [customize, setCustomize] = useState(false)

  useEffect(() => {
    async function load() {
      const [assetsData, overviewData] = await Promise.allSettled([
        analysisService.getAssets(),
        marketService.getMarketOverview(),
      ])
      if (assetsData.status === 'fulfilled') setAssets(assetsData.value)
      if (overviewData.status === 'fulfilled') setOverview(overviewData.value)
      setIsLoading(false)
    }
    load()
  }, [])

  // Cargar watchlist del usuario
  useEffect(() => {
    getWatchlist()
      .then(setWatchlistItems)
      .catch(() => { /* silencioso */ })
  }, [])

  // Mayores subidas y mayores bajadas en 24h
  const { gainers, losers } = useMemo(() => {
    const withChange = assets.map((a) => ({ a, c: parseFloat(a.price_change_24h ?? '0') }))
    const gainers = withChange
      .filter((x) => x.c > 0)
      .sort((x, y) => y.c - x.c)
      .slice(0, 5)
      .map((x) => x.a)
    const losers = withChange
      .filter((x) => x.c < 0)
      .sort((x, y) => x.c - y.c)
      .slice(0, 5)
      .map((x) => x.a)
    return { gainers, losers }
  }, [assets])

  // Carga en segundo plano de los minigráficos (7 velas diarias) de los
  // activos mostrados. No bloquea el render principal y degrada con gracia.
  useEffect(() => {
    const symbols = Array.from(new Set([
      ...gainers.map((a) => a.symbol),
      ...losers.map((a) => a.symbol),
      ...watchlistItems.map((w) => w.symbol),
    ]))
    if (symbols.length === 0) return
    let cancelled = false
    ;(async () => {
      const map = await marketService.getSparklines(symbols)
      if (cancelled) return
      setSparks(map)
    })()
    return () => {
      cancelled = true
    }
  }, [gainers, losers, watchlistItems])

  const bullishCount = assets.filter((a) => a.is_bullish_24h).length
  const bearishCount = assets.length - bullishCount

  function renderWidget(id: string) {
    switch (id) {
      case 'market':
        return (
          <section>
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              {t('dashboard.globalMarket')}
            </h2>
            <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
              <div className="lg:col-span-3 grid grid-cols-1 sm:grid-cols-3 gap-4">
                {overview ? (
                  <>
                    <StatCard label={t('dashboard.totalCap')} value={formatCompact(overview.total_market_cap_usd)} animateValue={Number(overview.total_market_cap_usd)} format={formatCompact} tone="brand" />
                    <StatCard label={t('dashboard.volume24h')} value={formatCompact(overview.total_volume_24h_usd)} animateValue={Number(overview.total_volume_24h_usd)} format={formatCompact} tone="brand" />
                    <StatCard label={t('dashboard.btcDominance')} value={`${parseFloat(overview.btc_dominance_pct).toFixed(1)}%`} animateValue={parseFloat(overview.btc_dominance_pct)} format={(n) => `${n.toFixed(1)}%`} tone="brand" />
                  </>
                ) : (
                  <>
                    <StatCard label={t('dashboard.totalCap')} value="—" />
                    <StatCard label={t('dashboard.volume24h')} value="—" />
                    <StatCard label={t('dashboard.btcDominance')} value="—" />
                  </>
                )}
              </div>

              {/* Fear & Greed como medidor */}
              <div className="bg-slate-800/60 rounded-xl border border-slate-700 px-5 py-4 flex flex-col items-center justify-center">
                <p className="text-slate-500 text-xs self-start mb-1">{t('dashboard.fearGreed')}</p>
                {overview ? (
                  <Gauge value={overview.fear_greed_index} label={fearGreedLabel(overview.fear_greed_index)} />
                ) : (
                  <div className="text-slate-600 text-sm py-6">—</div>
                )}
              </div>
            </div>
          </section>
        )

      case 'catalog':
        return (
          <section>
            <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
              {t('dashboard.catalog')}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <StatCard label={t('dashboard.monitoredAssets')} value={String(assets.length)} animateValue={assets.length} format={(n) => String(Math.round(n))} />
              <StatCard
                label={t('dashboard.bullish24h')}
                value={String(bullishCount)}
                animateValue={bullishCount}
                format={(n) => String(Math.round(n))}
                sub={assets.length ? `${((bullishCount / assets.length) * 100).toFixed(0)}${t('dashboard.ofTotal')}` : '—'}
                tone="positive"
              />
              <StatCard
                label={t('dashboard.bearish24h')}
                value={String(bearishCount)}
                animateValue={bearishCount}
                format={(n) => String(Math.round(n))}
                sub={assets.length ? `${((bearishCount / assets.length) * 100).toFixed(0)}${t('dashboard.ofTotal')}` : '—'}
                tone="negative"
              />
            </div>
          </section>
        )

      case 'watchlist':
        if (watchlistItems.length === 0) return null
        return (
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-2">
                <span className="text-yellow-400">★</span> {t('dashboard.myWatchlist')}
              </h2>
              <Link to="/market" className="text-xs text-blue-400 hover:text-blue-300 transition-colors">
                {t('dashboard.viewInMarket')}
              </Link>
            </div>
            <div className="bg-slate-800 rounded-xl border border-yellow-500/20 overflow-hidden">
              <div className="divide-y divide-slate-700/50">
                {watchlistItems.map((item) => (
                  <WatchlistRow key={item.symbol} item={item} spark={sparks[item.symbol]} />
                ))}
              </div>
            </div>
          </section>
        )

      case 'movers':
        return (
          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {t('dashboard.marketMovement')}
              </h2>
              <Link to="/market" className="text-xs text-blue-400 hover:text-blue-300 transition-colors">
                {t('dashboard.viewFullMarket')}
              </Link>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <MoversCard title={t('dashboard.topGainers')} tone="positive" assets={gainers} sparks={sparks} loading={isLoading} />
              <MoversCard title={t('dashboard.topLosers')} tone="negative" assets={losers} sparks={sparks} loading={isLoading} />
            </div>
          </section>
        )

      default:
        return null
    }
  }

  return (
    <div className="space-y-8 cw-stagger">
      {/* Cabecera */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">{t('dashboard.title')}</h1>
          <p className="text-slate-400 text-sm mt-1">
            {t(greetingKey())},{' '}
            <span className="text-slate-200 font-medium">{user?.username}</span>
            {' '}{t('dashboard.summary')}
          </p>
        </div>
        <button
          onClick={() => setCustomize((v) => !v)}
          className={`shrink-0 inline-flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-colors ${
            customize ? 'border-blue-500/50 text-blue-300 bg-blue-600/10' : 'border-slate-700 text-slate-400 hover:text-slate-200'
          }`}
        >
          ⚙ {t('dashboard.customize')}
        </button>
      </div>

      {/* Panel de personalización: mostrar/ocultar y reordenar widgets */}
      {customize && (
        <div className="bg-slate-800/60 rounded-xl border border-slate-700 p-4">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-semibold text-slate-300">{t('dashboard.customizePanel')}</p>
            <button onClick={reset} className="text-[11px] text-slate-400 hover:text-slate-200">{t('dashboard.reset')}</button>
          </div>
          <div className="space-y-1.5">
            {layout.map((w, i) => (
              <div key={w.id} className="flex items-center gap-2 text-sm">
                <label className="flex items-center gap-2 flex-1 cursor-pointer">
                  <input type="checkbox" checked={w.visible} onChange={() => toggle(w.id)} className="accent-blue-500" />
                  <span className={w.visible ? 'text-slate-200' : 'text-slate-500 line-through'}>{WIDGET_LABELS[w.id] ? t(WIDGET_LABELS[w.id]) : w.id}</span>
                </label>
                <button onClick={() => move(w.id, -1)} disabled={i === 0}
                  className="text-slate-500 hover:text-slate-200 disabled:opacity-30" aria-label="Subir">↑</button>
                <button onClick={() => move(w.id, 1)} disabled={i === layout.length - 1}
                  className="text-slate-500 hover:text-slate-200 disabled:opacity-30" aria-label="Bajar">↓</button>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-slate-600 mt-2">{t('dashboard.savedOnDevice')}</p>
        </div>
      )}

      {/* Widgets en el orden configurado */}
      {layout.filter((w) => w.visible).map((w) => (
        <div key={w.id}>{renderWidget(w.id)}</div>
      ))}
    </div>
  )
}

// ── Subcomponentes ─────────────────────────────────────────────────

function MoversCard({
  title,
  tone,
  assets,
  sparks,
  loading,
}: {
  title: string
  tone: 'positive' | 'negative'
  assets: CryptoAsset[]
  sparks: Record<string, number[]>
  loading: boolean
}) {
  const dot = tone === 'positive' ? 'bg-positive' : 'bg-negative'

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-slate-700/60">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">{title}</h3>
      </div>

      {loading ? (
        <div className="divide-y divide-slate-700/50">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonRow key={i} />
          ))}
        </div>
      ) : assets.length === 0 ? (
        <EmptyState variant="plain" title="Sin datos en esta categoría todavía." />
      ) : (
        <div className="divide-y divide-slate-700/50">
          {assets.map((asset) => (
            <MoverRow key={asset.id} asset={asset} spark={sparks[asset.symbol]} />
          ))}
        </div>
      )}
    </div>
  )
}

function WatchlistRow({ item, spark }: Readonly<{ item: WatchlistItem; spark?: number[] }>) {
  const { formatPrice } = useCurrency()
  const isPositive = parseFloat(item.price_change_24h ?? '0') >= 0
  return (
    <Link
      to={`/assets/${item.symbol}`}
      className="flex items-center gap-3 px-5 py-3 hover:bg-slate-700/30 transition-colors"
    >
      {item.logo_url ? (
        <img src={item.logo_url} alt={item.symbol} className="w-8 h-8 rounded-full shrink-0" />
      ) : (
        <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-yellow-400 shrink-0">
          {item.symbol.slice(0, 2)}
        </div>
      )}

      <div className="min-w-0">
        <p className="text-sm font-medium text-white truncate">{item.symbol}</p>
        <p className="text-xs text-slate-500 truncate">{item.name}</p>
      </div>

      <div className="ml-auto flex items-center gap-4">
        <Sparkline data={spark ?? []} color={isPositive ? '#22c55e' : '#ef4444'} className="hidden sm:block" />
        <div className="text-right">
          <p className="text-sm font-mono text-white tabular-nums">{formatPrice(item.current_price)}</p>
          <DeltaChip value={item.price_change_24h == null ? null : String(item.price_change_24h)} size="sm" className="mt-0.5" />
        </div>
      </div>
    </Link>
  )
}

function MoverRow({ asset, spark }: { asset: CryptoAsset; spark?: number[] }) {
  const { formatPrice } = useCurrency()
  const isPositive = parseFloat(asset.price_change_24h ?? '0') >= 0
  return (
    <div className="flex items-center gap-3 px-5 py-3 hover:bg-slate-700/30 transition-colors">
      {asset.logo_url ? (
        <img src={asset.logo_url} alt={asset.symbol} className="w-8 h-8 rounded-full shrink-0" />
      ) : (
        <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-blue-400 shrink-0">
          {asset.symbol.slice(0, 2)}
        </div>
      )}

      <div className="min-w-0">
        <p className="text-sm font-medium text-white truncate">{asset.symbol}</p>
        <p className="text-xs text-slate-500 truncate">{asset.name}</p>
      </div>

      <div className="ml-auto flex items-center gap-4">
        <Sparkline data={spark ?? []} color={isPositive ? '#22c55e' : '#ef4444'} className="hidden sm:block" />
        <div className="text-right">
          <p className="text-sm font-mono text-white tabular-nums">{formatPrice(asset.current_price)}</p>
          <DeltaChip value={asset.price_change_24h} size="sm" className="mt-0.5" />
        </div>
        <Link
          to={`/assets/${asset.symbol}`}
          className="text-blue-400 hover:text-blue-300 text-xs transition-colors shrink-0"
        >
          Ver →
        </Link>
      </div>
    </div>
  )
}

export default DashboardPage
