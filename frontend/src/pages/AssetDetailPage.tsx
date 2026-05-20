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

// ── Tipos ficha CoinGecko ──────────────────────────────────────────

interface CoinDetail {
  links?: {
    homepage?: string[]
    whitepaper?: string
    twitter_screen_name?: string
    subreddit_url?: string
  }
  market_data?: {
    ath?: { usd: number }
    ath_date?: { usd: string }
    atl?: { usd: number }
    circulating_supply?: number
    max_supply?: number | null
    total_supply?: number | null
  }
  categories?: string[]
  description?: { en?: string }
}

function AssetDetailPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const navigate = useNavigate()

  const [asset, setAsset] = useState<CryptoAsset | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [coinDetail, setCoinDetail] = useState<CoinDetail | null>(null)

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

        // Fetch ficha CoinGecko si hay coingecko_id
        if (found.coingecko_id) {
          fetch(
            `https://api.coingecko.com/api/v3/coins/${found.coingecko_id}?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false&sparkline=false`,
          )
            .then((r) => r.json())
            .then((data: CoinDetail) => setCoinDetail(data))
            .catch(() => { /* silencioso */ })
        }
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
          <Metric label="Tendencia" value={asset.is_bullish_24h ? 'Alcista' : 'Bajista'} />
        </div>
      </div>

      {/* Gráfico de velas OHLCV */}
      <div className="mb-6">
        <OhlcvChart symbol={asset.symbol} initialInterval="1h" />
      </div>

      {/* Ficha del proyecto (CoinGecko) */}
      {coinDetail && <ProjectCard coin={coinDetail} assetName={asset.name} />}

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

// ── Ficha del proyecto ─────────────────────────────────────────────

function ProjectCard({ coin, assetName }: { coin: CoinDetail; assetName: string }) {
  const homepage = coin.links?.homepage?.find(Boolean) ?? null
  const whitepaper = coin.links?.whitepaper ?? null
  const twitter = coin.links?.twitter_screen_name
    ? `https://twitter.com/${coin.links.twitter_screen_name}`
    : null
  const reddit = coin.links?.subreddit_url ?? null

  const ath = coin.market_data?.ath?.usd
  const athDate = coin.market_data?.ath_date?.usd
    ? new Date(coin.market_data.ath_date.usd).toLocaleDateString('es-ES', { year: 'numeric', month: 'short', day: 'numeric' })
    : null
  const circulatingSupply = coin.market_data?.circulating_supply
  const maxSupply = coin.market_data?.max_supply
  const categories = coin.categories?.slice(0, 4) ?? []

  const hasLinks = homepage || whitepaper || twitter || reddit
  const hasStats = ath || circulatingSupply

  if (!hasLinks && !hasStats && !categories.length) return null

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5 mb-6">
      <h3 className="text-sm font-semibold text-slate-300 mb-4">Ficha del proyecto</h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Links oficiales */}
        {hasLinks && (
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Links</p>
            <div className="flex flex-wrap gap-2">
              {homepage && (
                <a href={homepage} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md px-2.5 py-1 transition-colors">
                  🌐 Web oficial
                </a>
              )}
              {whitepaper && (
                <a href={whitepaper} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md px-2.5 py-1 transition-colors">
                  📄 Whitepaper
                </a>
              )}
              {twitter && (
                <a href={twitter} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md px-2.5 py-1 transition-colors">
                  𝕏 Twitter
                </a>
              )}
              {reddit && (
                <a href={reddit} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-md px-2.5 py-1 transition-colors">
                  Reddit
                </a>
              )}
            </div>
          </div>
        )}

        {/* Stats clave */}
        {hasStats && (
          <div>
            <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Estadísticas</p>
            <div className="space-y-1.5">
              {ath && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">ATH</span>
                  <span className="text-white font-mono">
                    ${ath.toLocaleString('es-ES', { minimumFractionDigits: 2 })}
                    {athDate && <span className="text-slate-500 text-xs ml-1">({athDate})</span>}
                  </span>
                </div>
              )}
              {circulatingSupply && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Supply circulante</span>
                  <span className="text-white font-mono">
                    {(circulatingSupply / 1e6).toFixed(2)}M {assetName.split(' ')[0]}
                  </span>
                </div>
              )}
              {maxSupply && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Supply máximo</span>
                  <span className="text-white font-mono">
                    {(maxSupply / 1e6).toFixed(2)}M
                  </span>
                </div>
              )}
              {!maxSupply && circulatingSupply && (
                <div className="flex justify-between text-sm">
                  <span className="text-slate-400">Supply máximo</span>
                  <span className="text-slate-500">Sin límite</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Categorías */}
      {categories.length > 0 && (
        <div className="mt-4 pt-4 border-t border-slate-700/60">
          <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Categorías</p>
          <div className="flex flex-wrap gap-1.5">
            {categories.map((cat) => (
              <span key={cat} className="text-xs bg-blue-500/15 text-blue-300 border border-blue-500/20 rounded-full px-2.5 py-0.5">
                {cat}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default AssetDetailPage
