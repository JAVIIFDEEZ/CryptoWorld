/**
 * pages/AssetDetailPage.tsx — Detalle de un activo criptográfico.
 *
 * Muestra información detallada del activo, gráfico OHLCV en tiempo real
 * (datos de Binance vía backend) y análisis técnico.
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import { marketService } from '@/services/marketService'
import { formatPrice, formatCompact } from '@/utils/format'
import DeltaChip from '@/components/ui/DeltaChip'
import OhlcvChart from '@/components/OhlcvChart'
import AnalysisPanel from '@/components/AnalysisPanel'

function AssetDetailPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const navigate = useNavigate()

  const [asset, setAsset] = useState<CryptoAsset | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [dayRange, setDayRange] = useState<{ low: number; high: number } | null>(null)

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

  // Calcular rango del día desde velas 1h (últimas 24)
  useEffect(() => {
    if (!symbol) return
    marketService.getOhlcv(symbol.toUpperCase(), '1h', 24)
      .then((res) => {
        if (res.candles.length === 0) return
        const highs = res.candles.map((c) => Number.parseFloat(c.high))
        const lows = res.candles.map((c) => Number.parseFloat(c.low))
        setDayRange({ low: Math.min(...lows), high: Math.max(...highs) })
      })
      .catch(() => { /* silencioso */ })
  }, [symbol])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400 animate-pulse">
        Cargando...
      </div>
    )
  }

  if (!asset) return null

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
            <p className="text-3xl font-bold font-mono tabular-nums text-white">
              {formatPrice(asset.current_price)}
            </p>
            <div className="flex items-center justify-end gap-2 mt-1">
              <DeltaChip value={asset.price_change_24h} arrow />
              <span className="text-xs text-slate-500">24h</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mt-6 pt-6 border-t border-slate-700">
          <Metric label="Cap. de mercado" value={asset.market_cap ? formatCompact(asset.market_cap) : '—'} />
          <Metric label="Volumen 24h" value={asset.volume_24h ? formatCompact(asset.volume_24h) : '—'} />
          <Metric label="Tendencia" value={asset.is_bullish_24h ? 'Alcista ↑' : 'Bajista ↓'} color={asset.is_bullish_24h ? 'text-positive' : 'text-negative'} />
        </div>

        {/* Barra de rango 24h */}
        {dayRange && (
          <RangeBar current={asset.current_price} low={String(dayRange.low)} high={String(dayRange.high)} />
        )}
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

function Metric({ label, value, color }: Readonly<{ label: string; value: string; color?: string }>) {
  return (
    <div>
      <p className="text-slate-500 text-xs mb-0.5">{label}</p>
      <p className={`text-sm font-medium ${color ?? 'text-white'}`}>{value}</p>
    </div>
  )
}

function RangeBar({
  current,
  low,
  high,
}: Readonly<{
  current: string | null | undefined
  low: string | null | undefined
  high: string | null | undefined
}>) {
  const c = Number.parseFloat(String(current ?? '0'))
  const l = Number.parseFloat(String(low ?? '0'))
  const h = Number.parseFloat(String(high ?? '0'))
  if (!l || !h || h <= l) return null

  const pct = Math.min(100, Math.max(0, ((c - l) / (h - l)) * 100))

  return (
    <div className="mt-5 pt-4 border-t border-slate-700/60">
      <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
        <span>Mín 24h</span>
        <span className="text-slate-400 font-medium">Rango del día</span>
        <span>Máx 24h</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-xs font-mono tabular-nums text-negative shrink-0">
          {formatPrice(low)}
        </span>
        <div className="flex-1 relative h-1.5 bg-slate-700 rounded-full overflow-visible">
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-negative via-caution to-positive"
            style={{ width: '100%' }}
          />
          {/* Indicador de posición actual */}
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white border-2 border-slate-900 shadow-lg"
            style={{ left: `calc(${pct}% - 6px)` }}
          />
        </div>
        <span className="text-xs font-mono tabular-nums text-positive shrink-0">
          {formatPrice(high)}
        </span>
      </div>
    </div>
  )
}

export default AssetDetailPage
