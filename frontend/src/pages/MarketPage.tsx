import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { analysisService, type CryptoAsset } from '@/services/analysisService'

type SortField = 'symbol' | 'price' | 'change' | 'marketCap'
type SortDirection = 'asc' | 'desc'

function parseNumeric(value: string | null | undefined): number {
  if (!value) return 0
  const parsed = Number.parseFloat(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

function MarketPage() {
  const [assets, setAssets] = useState<CryptoAsset[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('marketCap')
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc')

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

      if (sortField === 'symbol') {
        return a.symbol.localeCompare(b.symbol) * dir
      }

      if (sortField === 'price') {
        return (parseNumeric(a.current_price) - parseNumeric(b.current_price)) * dir
      }

      if (sortField === 'change') {
        return (parseNumeric(a.price_change_24h) - parseNumeric(b.price_change_24h)) * dir
      }

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

  const bullishCount = assets.filter((a) => a.is_bullish_24h).length
  const bearishCount = assets.length - bullishCount

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-white">Mercado</h1>
        <p className="text-slate-400 text-sm mt-1">
          Vista inspirada en el prototipo Figma y conectada al endpoint real de activos.
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MetricCard label="Activos listados" value={String(assets.length)} />
        <MetricCard label="Alcistas (24h)" value={String(bullishCount)} positive />
        <MetricCard label="Bajistas (24h)" value={String(bearishCount)} negative />
      </div>

      <div className="bg-slate-800 border border-slate-700 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-slate-700 flex flex-col md:flex-row gap-3 md:items-center md:justify-between">
          <p className="text-sm text-slate-300">Tabla de mercado</p>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por simbolo o nombre..."
            className="w-full md:w-72 bg-slate-700 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {isLoading && <p className="p-6 text-sm text-slate-400 animate-pulse">Cargando mercado...</p>}
        {error && <p className="p-6 text-sm text-red-400">{error}</p>}

        {!isLoading && !error && (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left text-slate-400 border-b border-slate-700 uppercase text-xs">
                  <HeaderCell label="Activo" onClick={() => handleSort('symbol')} />
                  <HeaderCell label="Precio" align="right" onClick={() => handleSort('price')} />
                  <HeaderCell label="24h" align="right" onClick={() => handleSort('change')} />
                  <HeaderCell label="Cap. mercado" align="right" onClick={() => handleSort('marketCap')} />
                  <th className="px-4 py-3 text-center">Detalle</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/60">
                {filteredAndSorted.map((asset) => {
                  const change = parseNumeric(asset.price_change_24h)
                  const isPositive = change >= 0
                  const marketCap = parseNumeric(asset.market_cap)

                  return (
                    <tr key={asset.id} className="hover:bg-slate-700/25 transition-colors">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-slate-700 text-blue-400 text-xs font-bold flex items-center justify-center">
                            {asset.symbol.slice(0, 2)}
                          </div>
                          <div>
                            <p className="font-medium text-white">{asset.symbol}</p>
                            <p className="text-xs text-slate-500">{asset.name}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right text-white font-mono">
                        ${parseNumeric(asset.current_price).toLocaleString('es-ES', { minimumFractionDigits: 2 })}
                      </td>
                      <td className={`px-4 py-3 text-right font-mono ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                        {isPositive ? '+' : ''}{change.toFixed(2)}%
                      </td>
                      <td className="px-4 py-3 text-right text-slate-300 font-mono">
                        {marketCap > 0 ? `$${(marketCap / 1e9).toFixed(2)}B` : '—'}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Link
                          to={`/assets/${asset.symbol}`}
                          className="text-blue-400 hover:text-blue-300 text-xs"
                        >
                          Ver
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}

function HeaderCell({
  label,
  align = 'left',
  onClick,
}: {
  label: string
  align?: 'left' | 'right'
  onClick: () => void
}) {
  return (
    <th className={`px-4 py-3 ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <button onClick={onClick} className="hover:text-slate-200 transition-colors">
        {label}
      </button>
    </th>
  )
}

function MetricCard({
  label,
  value,
  positive,
  negative,
}: {
  label: string
  value: string
  positive?: boolean
  negative?: boolean
}) {
  const colorClass = positive ? 'text-emerald-400' : negative ? 'text-red-400' : 'text-white'

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
      <p className="text-xs text-slate-500 uppercase">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${colorClass}`}>{value}</p>
    </div>
  )
}

export default MarketPage
