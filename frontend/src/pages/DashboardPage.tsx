/**
 * pages/DashboardPage.tsx — Panel principal de la aplicación.
 *
 * Responsabilidad: mostrar el listado de activos criptográficos
 * obtenidos de la API Django.
 *
 * Patrón usado: load-on-mount con useState + useEffect.
 * En fases posteriores del TFG se puede migrar a React Query
 * para caché, revalidación automática y manejo de errores avanzado.
 */

import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import { marketService, type MarketOverview } from '@/services/marketService'

function DashboardPage() {
  const { user } = useAuth()
  const [assets, setAssets] = useState<CryptoAsset[]>([])
  const [overview, setOverview] = useState<MarketOverview | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const [assetsData, overviewData] = await Promise.allSettled([
          analysisService.getAssets(),
          marketService.getMarketOverview(),
        ])
        if (assetsData.status === 'fulfilled') setAssets(assetsData.value)
        if (overviewData.status === 'fulfilled') setOverview(overviewData.value)
        if (assetsData.status === 'rejected') {
          setError('No se pudieron cargar los activos. Verifica la conexión con la API.')
        }
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div>
      {/* Cabecera */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-slate-400 text-sm mt-1">
          Bienvenido, <span className="text-slate-200">{user?.username}</span>
        </p>
      </div>

      {/* Resumen rápido de activos */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <StatCard label="Activos monitorizados" value={String(assets.length)} />
        <StatCard
          label="Activos alcistas (24h)"
          value={String(assets.filter((a) => a.is_bullish_24h).length)}
          positive
        />
        <StatCard
          label="Activos bajistas (24h)"
          value={String(assets.filter((a) => !a.is_bullish_24h).length)}
          negative
        />
      </div>

      {/* Resumen global del mercado */}
      {overview && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
          <MarketCard
            label="Cap. total mercado"
            value={`$${(parseFloat(overview.total_market_cap_usd) / 1e12).toFixed(2)}T`}
          />
          <MarketCard
            label="Volumen 24h"
            value={`$${(parseFloat(overview.total_volume_24h_usd) / 1e9).toFixed(0)}B`}
          />
          <MarketCard
            label="Dominancia BTC"
            value={`${parseFloat(overview.btc_dominance_pct).toFixed(1)}%`}
          />
          <MarketCard
            label="Fear & Greed"
            value={String(overview.fear_greed_index)}
            highlight={
              overview.fear_greed_index >= 75
                ? 'green'
                : overview.fear_greed_index <= 25
                  ? 'red'
                  : 'neutral'
            }
          />
        </div>
      )}

      {/* Tabla de activos */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-700">
          <h2 className="text-base font-semibold text-white">Mercado</h2>
        </div>

        {isLoading && (
          <div className="px-6 py-12 text-center text-slate-400 text-sm animate-pulse">
            Cargando activos...
          </div>
        )}

        {error && (
          <div className="px-6 py-8 text-center text-red-400 text-sm">{error}</div>
        )}

        {!isLoading && !error && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-slate-400 text-xs uppercase border-b border-slate-700">
                  <th className="text-left px-6 py-3">Activo</th>
                  <th className="text-right px-6 py-3">Precio</th>
                  <th className="text-right px-6 py-3">24h</th>
                  <th className="text-right px-6 py-3">Cap. mercado</th>
                  <th className="text-center px-6 py-3">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {assets.map((asset) => (
                  <AssetRow key={asset.id} asset={asset} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Subcomponentes ─────────────────────────────────────────────────

function StatCard({
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
  const valueClass = positive
    ? 'text-green-400'
    : negative
      ? 'text-red-400'
      : 'text-white'

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 px-5 py-4">
      <p className="text-slate-400 text-xs mb-1">{label}</p>
      <p className={`text-2xl font-bold ${valueClass}`}>{value}</p>
    </div>
  )
}

function MarketCard({
  label,
  value,
  highlight,
}: {
  label: string
  value: string
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
    </div>
  )
}

function AssetRow({ asset }: { asset: CryptoAsset }) {
  const change = parseFloat(asset.price_change_24h ?? '0')
  const isPositive = change >= 0

  return (
    <tr className="hover:bg-slate-700/30 transition-colors">
      <td className="px-6 py-4">
        <div className="flex items-center gap-3">
          {asset.logo_url ? (
            <img src={asset.logo_url} alt={asset.symbol} className="w-8 h-8 rounded-full" />
          ) : (
            <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-blue-400">
              {asset.symbol.slice(0, 2)}
            </div>
          )}
          <div>
            <p className="font-medium text-white">{asset.symbol}</p>
            <p className="text-slate-500 text-xs">{asset.name}</p>
          </div>
        </div>
      </td>
      <td className="px-6 py-4 text-right font-mono text-white">
        ${parseFloat(asset.current_price).toLocaleString('es-ES', { minimumFractionDigits: 2 })}
      </td>
      <td className={`px-6 py-4 text-right font-mono ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
        {isPositive ? '+' : ''}{change.toFixed(2)}%
      </td>
      <td className="px-6 py-4 text-right text-slate-300 font-mono">
        {asset.market_cap
          ? `$${(parseFloat(asset.market_cap) / 1e9).toFixed(1)}B`
          : '—'}
      </td>
      <td className="px-6 py-4 text-center">
        <Link
          to={`/assets/${asset.symbol}`}
          className="text-blue-400 hover:text-blue-300 text-xs transition-colors"
        >
          Ver detalle →
        </Link>
      </td>
    </tr>
  )
}

export default DashboardPage
