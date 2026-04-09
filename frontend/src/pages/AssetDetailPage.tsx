/**
 * pages/AssetDetailPage.tsx — Detalle de un activo criptográfico.
 *
 * Muestra información detallada del activo, gráfico OHLCV en tiempo real
 * (datos de Binance vía backend) y análisis técnico.
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import OhlcvChart from '@/components/OhlcvChart'
import AnalysisPanel from '@/components/AnalysisPanel'

function AssetDetailPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const navigate = useNavigate()

  const [asset, setAsset] = useState<CryptoAsset | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const assets = await analysisService.getAssets()
        const found = assets.find((a) => a.symbol === symbol?.toUpperCase())
        if (!found) {
          navigate('/dashboard', { replace: true })
          return
        }
        setAsset(found)
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [symbol, navigate])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400 animate-pulse">
        Cargando...
      </div>
    )
  }

  if (!asset) return null

  const change = parseFloat(asset.price_change_24h ?? '0')
  const isPositive = change >= 0

  return (
    <div>
      {/* Breadcrumb */}
      <button
        onClick={() => navigate(-1)}
        className="text-slate-400 hover:text-slate-200 text-sm mb-6 flex items-center gap-1 transition-colors"
      >
        ← Volver al dashboard
      </button>

      {/* Header del activo */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 mb-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            {asset.logo_url ? (
              <img src={asset.logo_url} alt={asset.symbol} className="w-12 h-12 rounded-full" />
            ) : (
              <div className="w-12 h-12 rounded-full bg-slate-700 flex items-center justify-center text-lg font-bold text-blue-400">
                {asset.symbol.slice(0, 2)}
              </div>
            )}
            <div>
              <h1 className="text-2xl font-bold text-white">{asset.name}</h1>
              <p className="text-slate-400 text-sm">{asset.symbol}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-3xl font-bold font-mono text-white">
              ${parseFloat(asset.current_price).toLocaleString('es-ES', { minimumFractionDigits: 2 })}
            </p>
            <p className={`text-sm font-mono mt-1 ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
              {isPositive ? '▲' : '▼'} {Math.abs(change).toFixed(2)}% (24h)
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mt-6 pt-6 border-t border-slate-700">
          <Metric label="Cap. de mercado" value={asset.market_cap ? `$${(parseFloat(asset.market_cap) / 1e9).toFixed(2)}B` : '—'} />
          <Metric label="Volumen 24h" value={asset.volume_24h ? `$${(parseFloat(asset.volume_24h) / 1e9).toFixed(2)}B` : '—'} />
          <Metric label="Tendencia" value={asset.is_bullish_24h ? '📈 Alcista' : '📉 Bajista'} />
        </div>
      </div>

      {/* Gráfico de velas OHLCV */}
      <div className="mb-6">
        <OhlcvChart symbol={asset.symbol} initialInterval="1h" />
      </div>

      {/* Panel de análisis técnico avanzado */}
      <AnalysisPanel symbol={asset.symbol} />
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-slate-500 text-xs mb-0.5">{label}</p>
      <p className="text-white text-sm font-medium">{value}</p>
    </div>
  )
}

export default AssetDetailPage
