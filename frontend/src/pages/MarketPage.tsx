import { useEffect, useMemo, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import { marketService } from '@/services/marketService'
import { getWatchlist, addToWatchlist, removeFromWatchlist } from '@/services/watchlistService'
import { formatPrice, formatCompact } from '@/utils/format'
import DeltaChip from '@/components/ui/DeltaChip'
import StatCard from '@/components/ui/StatCard'
import Sparkline from '@/components/ui/Sparkline'
import { SkeletonRow } from '@/components/ui/Skeleton'

type SortField = 'symbol' | 'price' | 'change' | 'volume' | 'marketCap'
type SortDirection = 'asc' | 'desc'

function parseNumeric(value: string | null | undefined): number {
  if (!value) return 0
  const parsed = Number.parseFloat(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

function MarketPage() {
  const navigate = useNavigate()
  const [assets, setAssets] = useState<CryptoAsset[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('marketCap')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')
  const [showAll, setShowAll] = useState(false)
  const [sparks, setSparks] = useState<Record<string, number[]>>({})
  const [sparksLoaded, setSparksLoaded] = useState(false)
  const [watchlist, setWatchlist] = useState<Set<string>>(new Set())
  const [watchlistLoading, setWatchlistLoading] = useState<Set<string>>(new Set())

  const INITIAL_LIMIT = 20

  useEffect(() => {
    async function loadAssets() {
      try {
        const data = await analysisService.getAssets()
        setAssets(data)
      } catch {
        setError('No se pudo cargar el mercado. Verifica la conexion con la API.')
      } finally {
        setIsLoading(false)
      }
    }
    loadAssets()
  }, [])

  // Cargar watchlist del usuario autenticado
  useEffect(() => {
    getWatchlist()
      .then((items) => setWatchlist(new Set(items.map((i) => i.symbol))))
      .catch(() => { /* silencioso si no está autenticado */ })
  }, [])

  // Cargar sparklines 7d para los activos visibles (batch vía endpoint dedicado)
  useEffect(() => {
    if (assets.length === 0) return
    const symbols = assets.slice(0, 25).map((a) => a.symbol)
    let cancelled = false
    ;(async () => {
      const map = await marketService.getSparklines(symbols)
      if (cancelled) return
      setSparks(map)
      setSparksLoaded(true)
    })()
    return () => { cancelled = true }
  }, [assets])

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

  const toggleWatchlist = useCallback(async (symbol: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setWatchlistLoading((prev) => new Set(prev).add(symbol))
    try {
      if (watchlist.has(symbol)) {
        await removeFromWatchlist(symbol)
        setWatchlist((prev) => { const s = new Set(prev); s.delete(symbol); return s })
      } else {
        await addToWatchlist(symbol)
        setWatchlist((prev) => new Set(prev).add(symbol))
      }
    } catch {
      // silencioso
    } finally {
      setWatchlistLoading((prev) => { const s = new Set(prev); s.delete(symbol); return s })
    }
  }, [watchlist])

  const bullishCount = assets.filter((a) => a.is_bullish_24h).length
  const bearishCount = assets.length - bullishCount
  const displayedAssets = (search.trim() || showAll) ? filteredAndSorted : filteredAndSorted.slice(0, INITIAL_LIMIT)

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Mercado</h1>
        <p className="text-slate-400 text-sm mt-1">
          Catálogo completo de activos. Busca, ordena y accede al detalle de cada criptomoneda.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard label="Activos listados" value={String(assets.length)} />
        <StatCard label="Alcistas (24h)" value={String(bullishCount)} tone="positive" />
        <StatCard label="Bajistas (24h)" value={String(bearishCount)} tone="negative" />
      </div>

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
            {filteredAndSorted.length} activos
          </p>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por símbolo o nombre..."
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
        {error && <p className="p-6 text-sm text-red-400">{error}</p>}

        {!isLoading && !error && (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-700/80 bg-slate-900/40 uppercase text-[11px] tracking-wider">
                    <th className="w-10 pl-4 pr-2 py-3 text-center">#</th>
                    <th className="w-8 px-2 py-3" />
                    <HeaderCell label="Activo" field="symbol" sortField={sortField} sortDirection={sortDirection} onClick={() => handleSort('symbol')} />
                    <HeaderCell label="Precio" field="price" align="right" sortField={sortField} sortDirection={sortDirection} onClick={() => handleSort('price')} />
                    <HeaderCell label="24h" field="change" align="right" sortField={sortField} sortDirection={sortDirection} onClick={() => handleSort('change')} />
                    <HeaderCell label="Volumen 24h" field="volume" align="right" sortField={sortField} sortDirection={sortDirection} onClick={() => handleSort('volume')} />
                    <HeaderCell label="Cap. mercado" field="marketCap" align="right" sortField={sortField} sortDirection={sortDirection} onClick={() => handleSort('marketCap')} />
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
                            title={inWatchlist ? 'Quitar de watchlist' : 'Añadir a watchlist'}
                            aria-label={inWatchlist ? 'Quitar de watchlist' : 'Añadir a watchlist'}
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
                  Mostrar todos ({filteredAndSorted.length - INITIAL_LIMIT} activos más)
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
  return (
    <div className="bg-slate-800 border border-yellow-500/20 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-700/60 flex items-center gap-2">
        <span className="text-yellow-400 text-sm">★</span>
        <h3 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Mi seguimiento</h3>
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
                      title={inWatchlist ? 'Quitar de watchlist' : 'Añadir a watchlist'}
                      aria-label={inWatchlist ? 'Quitar de watchlist' : 'Añadir a watchlist'}
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
