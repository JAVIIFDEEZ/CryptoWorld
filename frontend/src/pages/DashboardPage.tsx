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

function DashboardPage() {
  const { user } = useAuth()
  const [assets, setAssets] = useState<CryptoAsset[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadAssets() {
      try {
        const data = await analysisService.getAssets()
        setAssets(data)
      } catch {
        setError('No se pudieron cargar los activos. Verifica la conexión con la API.')
      } finally {
        setIsLoading(false)
      }
    }

    loadAssets()
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

      {/* Resumen rápido */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
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

function AssetRow({ asset }: { asset: CryptoAsset }) {
  const change = parseFloat(asset.price_change_24h ?? '0')
  const isPositive = change >= 0

  return (
    <tr className="hover:bg-slate-700/30 transition-colors">
      <td className="px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-blue-400">
            {asset.symbol.slice(0, 2)}
          </div>
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
