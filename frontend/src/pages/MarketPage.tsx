import { lazy, useMemo, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { type CryptoAsset } from '@/services/analysisService'
import { useAssets, useSparklines, useToggleWatchlist, useWatchlist } from '@/hooks/queries/useMarketData'
import { useCurrency } from '@/hooks/useCurrency'
import DeltaChip from '@/components/ui/DeltaChip'
import StatCard from '@/components/ui/StatCard'
import Sparkline from '@/components/ui/Sparkline'
import { SkeletonRow } from '@/components/ui/Skeleton'
import Viz3DSwitch from '@/components/viz3d/Viz3DSwitch'
import MarketTreemap2D from '@/components/market/MarketTreemap2D'
import MarketRegimePanel from '@/components/market/MarketRegimePanel'
import LeadLagPanel from '@/components/market/LeadLagPanel'
import { buildMarketBodies } from '@/components/market/marketViz'

const MarketUniverse3D = lazy(() => import('@/components/market/MarketUniverse3D'))

type SortField = 'symbol' | 'price' | 'change' | 'volume' | 'marketCap'
type SortDirection = 'asc' | 'desc'

function parseNumeric(value: string | null | undefined): number {
  if (!value) return 0
  const parsed = Number.parseFloat(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

function MarketPage() {
  const { t } = useTranslation()
  const { formatPrice, formatCompact } = useCurrency()
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('marketCap')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [showAll, setShowAll] = useState(false)

  const INITIAL_LIMIT = 20

  // Capa de datos declarativa (TanStack Query): caché compartida entre vistas,
  // deduplicación y revalidación al volver a la pestaña — sin useEffect manual.
  const { data: assetsData, isLoading, isError: error } = useAssets()
  const assets: CryptoAsset[] = useMemo(() => assetsData ?? [], [assetsData])

  // Sparklines 7d de los 25 activos de mayor capitalización (batch dedicado).
  // Se ordena por market_cap aquí para garantizar que los activos visibles por
  // defecto (top-20 por cap.) siempre tengan sparkline.
  const top25 = useMemo(() => [...assets]
    .sort((a, b) => parseNumeric(b.market_cap) - parseNumeric(a.market_cap))
    .slice(0, 25)
    .map((a) => a.symbol), [assets])
  const sparklinesQuery = useSparklines(top25)
  const sparks = sparklinesQuery.data ?? {}
  const sparksLoaded = sparklinesQuery.isFetched

  // Watchlist con actualización optimista: la estrella responde al instante.
  const { data: watchlistSymbols } = useWatchlist()
  const watchlist = useMemo(() => new Set(watchlistSymbols ?? []), [watchlistSymbols])
  const toggleMutation = useToggleWatchlist()
  const watchlistLoading = useMemo(() => new Set<string>(
    toggleMutation.isPending && toggleMutation.variables ? [toggleMutation.variables.symbol] : [],
  ), [toggleMutation.isPending, toggleMutation.variables])

  const filteredAndSorted = useMemo(() => {
    const filtered = assets.filter((asset) => {
      const query = search.trim().toLowerCase()
      if (!query) return true
      return (
        asset.symbol.toLowerCase().includes(query) ||
        asset.name.toLowerCase().includes(query)
      )
    })
    return filtered.sort((a, b) => {
      const dir = sortDirection === 'asc' ? 1 : -1
      if (sortField === 'symbol') return a.symbol.localeCompare(b.symbol) * dir
      if (sortField === 'price') return (parseNumeric(a.current_price) - parseNumeric(b.current_price)) * dir
      if (sortField === 'change') return (parseNumeric(a.price_change_24h) - parseNumeric(b.price_change_24h)) * dir
      if (sortField === 'volume') return (parseNumeric(a.volume_24h) - parseNumeric(b.volume_24h)) * dir
      return (parseNumeric(a.market_cap) - parseNumeric(b.market_cap)) * dir
    })
  }, [assets, search, sortField, sortDirection])

  function handleSort(field: SortField) {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'))
      return
    }
    setSortField(field)
    setSortDirection('desc')
  }

  const toggleWatchlist = useCallback((symbol: string, e: React.MouseEvent) => {
    e.stopPropagation()
    toggleMutation.mutate({ symbol, inWatchlist: watchlist.has(symbol) })
  }, [watchlist, toggleMutation])

  const bullishCount = assets.filter((a) => a.is_bullish_24h).length
  const bearishCount = assets.length - bullishCount
  const displayedAssets = (search.trim() || showAll) ? filteredAndSorted : filteredAndSorted.slice(0, INITIAL_LIMIT)

  const marketBodies = useMemo(() => buildMarketBodies(assets, sparks, 30), [assets, sparks])
  const goToAsset = useCallback((sym: string) => navigate(`/assets/${sym}`), [navigate])

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-white">{t('market.title')}</h1>
        <p className="text-slate-400 text-sm mt-1">
          {t('market.subtitle')}
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard label={t('market.listedAssets')} value={String(assets.length)} animateValue={assets.length} format={(n) => String(Math.round(n))} />
        <StatCard label={t('market.bullish24h')} value={String(bullishCount)} animateValue={bullishCount} format={(n) => String(Math.round(n))} tone="positive" />
        <StatCard label={t('market.bearish24h')} value={String(bearishCount)} animateValue={bearishCount} format={(n) => String(Math.round(n))} tone="negative" />
      </div>

      {/* Régimen de mercado + correlaciones cross-asset de la cesta */}
      <MarketRegimePanel />

      {/* Señales lead-lag: qué activos adelantan a cuáles */}
      <LeadLagPanel />

      {/* Universo de mercado: galaxia 3D (tamaño=cap, color=cambio) con treemap 2D */}
      {!isLoading && !error && marketBodies.length > 0 && (
        <Viz3DSwitch
          title={t('market.universeTitle')}
          hint={t('market.universeHint')}
          threeD={<MarketUniverse3D bodies={marketBodies} onSelect={goToAsset} />}
          twoD={<MarketTreemap2D bodies={marketBodies} onSelect={goToAsset} />}
        />
      )}

      {/* Sección: Mi seguimiento */}
      {!isLoading && !error && !search.trim() && assets.some((a) => watchlist.has(a.symbol)) && (
        <WatchlistSection
          assets={assets.filter((a) => watchlist.has(a.symbol))}
          sparks={sparks}
          sparksLoaded={sparksLoaded}
          watchlist={watchlist}
          watchlistLoading={watchlistLoading}
          onToggle={toggleWatchlist}
          onNavigate={(sym) => navigate(`/assets/${sym}`)}
        />
      )}

      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        {/* Cabecera de la tabla */}
        <div className="px-4 py-3 border-b border-slate-700 flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
          <p className="text-sm font-medium text-slate-300">
            {t('market.assetsCount', { count: filteredAndSorted.length })}
          </p>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('market.searchPlaceholder')}
            className="w-full sm:w-72 bg-slate-900 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all"
          />
        </div>

        {isLoading && (
          <div className="divide-y divide-slate-700/60">
            {Array.from({ length: 10 }).map((_, i) => (
              <SkeletonRow key={i} />
            ))}
          </div>
        )}
        {error && <p className="p-6 text-sm text-red-400">{t('market.loadError')}</p>}

        {!isLoading && !error && (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-700/80 bg-slate-900/40 uppercase text-[11px] tracking-wider">
                    <th className="w-10 pl-4 pr-2 py-3 text-center">#</th>
                    <th className="w-8 px-2 py-3" />
                    <HeaderCell label={t('market.colAsset')} field="symbol" sortField={sortField} sortDirection={sortDirection} onClick={() => handleSort('symbol')} />
                    <HeaderCell label={t('market.colPrice')} field="price" align="right" sortField={sortField} sortDirection={sortDirection} onClick={() => handleSort('price')} />
                    <HeaderCell label={t('market.col24h')} field="change" align="right" sortField={sortField} sortDirection={sortDirection} onClick={() => handleSort('change')} />
                    <HeaderCell label={t('market.colVolume')} field="volume" align="right" sortField={sortField} sortDirection={sortDirection} onClick={() => handleSort('volume')} />
                    <HeaderCell label={t('market.colMarketCap')} field="marketCap" align="right" sortField={sortField} sortDirection={sortDirection} onClick={() => handleSort('marketCap')} />
                    <th className="px-4 py-3 text-center hidden lg:table-cell">7d</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700/40">
                  {displayedAssets.map((asset, idx) => {
                    const marketCap = parseNumeric(asset.market_cap)
                    const volume = parseNumeric(asset.volume_24h)
                    const inWatchlist = watchlist.has(asset.symbol)
                    const wlPending = watchlistLoading.has(asset.symbol)
                    const sparkData = sparks[asset.symbol]

                    return (
                      <tr
                        key={asset.id}
                        onClick={() => navigate(`/assets/${asset.symbol}`)}
                        className="hover:bg-slate-700/30 transition-colors cursor-pointer group"
                      >
                        {/* Rank */}
                        <td className="pl-4 pr-2 py-3.5 text-center text-slate-500 text-xs tabular-nums">
                          {idx + 1}
                        </td>

                        {/* Watchlist star */}
                        <td className="px-2 py-3.5 text-center">
                          <button
                            onClick={(e) => toggleWatchlist(asset.symbol, e)}
                            disabled={wlPending}
                            className={`transition-colors text-base leading-none ${
                              inWatchlist
                                ? 'text-yellow-400 hover:text-yellow-300'
                                : 'text-slate-600 hover:text-slate-400 opacity-0 group-hover:opacity-100'
                            }`}
                            title={inWatchlist ? t('market.removeWatchlist') : t('market.addWatchlist')}
                            aria-label={inWatchlist ? t('market.removeWatchlist') : t('market.addWatchlist')}
                          >
                            {inWatchlist ? '★' : '☆'}
                          </button>
                        </td>

                        {/* Nombre + logo */}
                        <td className="px-4 py-3.5">
                          <div className="flex items-center gap-3">
                            {asset.logo_url ? (
                              <img src={asset.logo_url} alt={asset.symbol} className="w-8 h-8 rounded-full shrink-0" />
                            ) : (
                              <div className="w-8 h-8 rounded-full bg-slate-700 text-blue-400 text-xs font-bold flex items-center justify-center shrink-0">
                                {asset.symbol.slice(0, 2)}
                              </div>
                            )}
                            <div className="min-w-0">
                              <p className="font-semibold text-white text-sm">{asset.symbol}</p>
                              <p className="text-xs text-slate-500 truncate max-w-[120px]">{asset.name}</p>
                            </div>
                          </div>
                        </td>

                        {/* Precio */}
                        <td className="px-4 py-3.5 text-right text-white font-mono tabular-nums font-medium">
                          {formatPrice(asset.current_price)}
                        </td>

                        {/* Cambio 24h */}
                        <td className="px-4 py-3.5 text-right">
                          <DeltaChip value={asset.price_change_24h} size="sm" />
                        </td>

                        {/* Volumen */}
                        <td className="px-4 py-3.5 text-right text-slate-400 font-mono tabular-nums text-xs">
                          {volume > 0 ? formatCompact(volume) : '—'}
                        </td>

                        {/* Cap. mercado */}
                        <td className="px-4 py-3.5 text-right text-slate-300 font-mono tabular-nums text-xs">
                          {marketCap > 0 ? formatCompact(marketCap) : '—'}
                        </td>

                        {/* Sparkline 7d */}
                        <td className="px-4 py-3.5 text-center hidden lg:table-cell">
                          {sparkData && sparkData.length >= 2 ? (
                            <Sparkline data={sparkData} width={80} height={32} />
                          ) : sparksLoaded ? (
                            <span className="text-slate-600 text-xs">—</span>
                          ) : (
                            <div className="w-20 h-8 mx-auto cw-shimmer rounded" />
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {!showAll && !search.trim() && filteredAndSorted.length > INITIAL_LIMIT && (
              <div className="p-4 text-center border-t border-slate-700">
                <button
                  onClick={() => setShowAll(true)}
                  className="text-sm text-blue-400 hover:text-blue-300 transition-colors font-medium"
                >
                  {t('market.showAll', { count: filteredAndSorted.length - INITIAL_LIMIT })}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </section>
  )
}

function WatchlistSection({
  assets,
  sparks,
  sparksLoaded,
  watchlist,
  watchlistLoading,
  onToggle,
  onNavigate,
}: Readonly<{
  assets: CryptoAsset[]
  sparks: Record<string, number[]>
  sparksLoaded: boolean
  watchlist: Set<string>
  watchlistLoading: Set<string>
  onToggle: (symbol: string, e: React.MouseEvent) => void
  onNavigate: (symbol: string) => void
}>) {
  const { t } = useTranslation()
  const { formatPrice, formatCompact } = useCurrency()
  return (
    <div className="bg-slate-800 border border-yellow-500/20 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-700/60 flex items-center gap-2">
        <span className="text-yellow-400 text-sm">★</span>
        <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">{t('market.myWatchlist')}</h3>
        <span className="text-slate-600 text-xs ml-1">({assets.length})</span>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <tbody className="divide-y divide-slate-700/40">
            {assets.map((asset, idx) => {
              const marketCap = parseNumeric(asset.market_cap)
              const volume = parseNumeric(asset.volume_24h)
              const inWatchlist = watchlist.has(asset.symbol)
              const wlPending = watchlistLoading.has(asset.symbol)
              const sparkData = sparks[asset.symbol]

              return (
                <tr
                  key={asset.id}
                  onClick={() => onNavigate(asset.symbol)}
                  className="hover:bg-slate-700/30 transition-colors cursor-pointer group"
                >
                  <td className="pl-4 pr-2 py-3.5 text-center text-slate-500 text-xs tabular-nums">
                    {idx + 1}
                  </td>
                  <td className="px-2 py-3.5 text-center">
                    <button
                      onClick={(e) => onToggle(asset.symbol, e)}
                      disabled={wlPending}
                      className={`transition-colors text-base leading-none ${
                        inWatchlist
                          ? 'text-yellow-400 hover:text-yellow-300'
                          : 'text-slate-600 hover:text-slate-400 opacity-0 group-hover:opacity-100'
                      }`}
                      title={inWatchlist ? t('market.removeWatchlist') : t('market.addWatchlist')}
                      aria-label={inWatchlist ? t('market.removeWatchlist') : t('market.addWatchlist')}
                    >
                      {inWatchlist ? '★' : '☆'}
                    </button>
                  </td>
                  <td className="px-4 py-3.5">
                    <div className="flex items-center gap-3">
                      {asset.logo_url ? (
                        <img src={asset.logo_url} alt={asset.symbol} className="w-8 h-8 rounded-full shrink-0" />
                      ) : (
                        <div className="w-8 h-8 rounded-full bg-slate-700 text-blue-400 text-xs font-bold flex items-center justify-center shrink-0">
                          {asset.symbol.slice(0, 2)}
                        </div>
                      )}
                      <div className="min-w-0">
                        <p className="font-semibold text-white text-sm">{asset.symbol}</p>
                        <p className="text-xs text-slate-500 truncate max-w-[120px]">{asset.name}</p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3.5 text-right text-white font-mono tabular-nums font-medium">
                    {formatPrice(asset.current_price)}
                  </td>
                  <td className="px-4 py-3.5 text-right">
                    <DeltaChip value={asset.price_change_24h} size="sm" />
                  </td>
                  <td className="px-4 py-3.5 text-right text-slate-400 font-mono tabular-nums text-xs">
                    {volume > 0 ? formatCompact(volume) : '—'}
                  </td>
                  <td className="px-4 py-3.5 text-right text-slate-300 font-mono tabular-nums text-xs">
                    {marketCap > 0 ? formatCompact(marketCap) : '—'}
                  </td>
                  <td className="px-4 py-3.5 text-center hidden lg:table-cell">
                    {sparkData && sparkData.length >= 2 ? (
                      <Sparkline data={sparkData} width={80} height={32} />
                    ) : sparksLoaded ? (
                      <span className="text-slate-600 text-xs">—</span>
                    ) : (
                      <div className="w-20 h-8 mx-auto cw-shimmer rounded" />
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function HeaderCell({
  label,
  field,
  sortField,
  sortDirection,
  align = 'left',
  onClick,
}: {
  label: string
  field: SortField
  sortField: SortField
  sortDirection: SortDirection
  align?: 'left' | 'right'
  onClick: () => void
}) {
  const isActive = sortField === field

  return (
    <th className={`px-4 py-3 ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <button
        onClick={onClick}
        className={`inline-flex items-center gap-1 transition-colors ${
          isActive ? 'text-blue-400' : 'text-slate-500 hover:text-slate-300'
        }`}
      >
        {label}
        <span className={`text-[10px] w-2 inline-block ${isActive ? 'opacity-100' : 'opacity-0'}`}>
          {isActive ? (sortDirection === 'asc' ? '↑' : '↓') : ''}
        </span>
      </button>
    </th>
  )
}

export default MarketPage
