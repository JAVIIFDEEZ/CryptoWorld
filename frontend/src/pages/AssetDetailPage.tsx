/**
 * pages/AssetDetailPage.tsx — Detalle de un activo criptográfico.
 *
 * Muestra información detallada del activo, gráfico OHLCV en tiempo real
 * (datos de Binance vía backend) y análisis técnico.
 */

import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import { marketService, type AssetInfo } from '@/services/marketService'
import { formatPrice, formatCompact, formatNumber } from '@/utils/format'
import DeltaChip from '@/components/ui/DeltaChip'
import OhlcvChart from '@/components/OhlcvChart'
import AnalysisPanel from '@/components/AnalysisPanel'

function AssetDetailPage() {
  const { symbol } = useParams<{ symbol: string }>()
  const navigate = useNavigate()

  const [asset, setAsset] = useState<CryptoAsset | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [dayRange, setDayRange] = useState<{ low: number; high: number } | null>(null)
  const [assetInfo, setAssetInfo] = useState<AssetInfo | null>(null)

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

  // Cargar info de proyecto desde el backend (CoinGecko proxied)
  useEffect(() => {
    if (!symbol) return
    marketService.getAssetInfo(symbol.toUpperCase())
      .then(setAssetInfo)
      .catch(() => { /* silencioso si CoinGecko no responde */ })
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

      {/* Información de proyecto (backend → CoinGecko) */}
      {assetInfo && <ProjectCard info={assetInfo} symbol={asset.symbol} />}

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

// ── Iconos SVG inline ──────────────────────────────────────────────

function GlobeIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-4 h-4 shrink-0">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 2c-3 3-4.5 6.5-4.5 10s1.5 7 4.5 10M12 2c3 3 4.5 6.5 4.5 10s-1.5 7-4.5 10M2 12h20" />
    </svg>
  )
}

function DocumentIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-4 h-4 shrink-0">
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5.586a1 1 0 0 1 .707.293l5.414 5.414a1 1 0 0 1 .293.707V19a2 2 0 0 1-2 2z" />
    </svg>
  )
}

function XIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 shrink-0">
      <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.75l7.73-8.835L1.254 2.25H8.08l4.26 5.632zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
    </svg>
  )
}

function RedditIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 shrink-0">
      <path d="M12 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0zm5.01 4.744c.688 0 1.25.561 1.25 1.249a1.25 1.25 0 0 1-2.498.056l-2.597-.547-.8 3.747c1.824.07 3.48.632 4.674 1.488.308-.309.73-.491 1.207-.491.968 0 1.754.786 1.754 1.754 0 .716-.435 1.333-1.01 1.614a3.111 3.111 0 0 1 .042.52c0 2.694-3.13 4.87-7.004 4.87-3.874 0-7.004-2.176-7.004-4.87 0-.183.015-.366.043-.534A1.748 1.748 0 0 1 4.028 12c0-.968.786-1.754 1.754-1.754.463 0 .898.196 1.207.49 1.207-.883 2.878-1.43 4.744-1.487l.885-4.182a.342.342 0 0 1 .14-.197.35.35 0 0 1 .238-.042l2.906.617a1.214 1.214 0 0 1 1.108-.701zM9.25 12C8.561 12 8 12.562 8 13.25c0 .687.561 1.248 1.25 1.248.687 0 1.248-.561 1.248-1.249 0-.688-.561-1.249-1.249-1.249zm5.5 0c-.687 0-1.248.561-1.248 1.25 0 .687.561 1.248 1.249 1.248.688 0 1.249-.561 1.249-1.249 0-.687-.562-1.249-1.25-1.249zm-5.466 3.99a.327.327 0 0 0-.231.094.33.33 0 0 0 0 .463c.842.842 2.484.913 2.961.913.477 0 2.105-.056 2.961-.913a.361.361 0 0 0 .029-.463.33.33 0 0 0-.464 0c-.547.533-1.684.73-2.512.73-.828 0-1.979-.196-2.512-.73a.326.326 0 0 0-.232-.095z" />
    </svg>
  )
}

function TelegramIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 shrink-0">
      <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.96 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
    </svg>
  )
}

function GitHubIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 shrink-0">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  )
}

// ── Subcomponentes ProjectCard ─────────────────────────────────────

function SupplyBar({ circulating, max }: Readonly<{ circulating: number; max: number }>) {
  const pct = Math.min(100, (circulating / max) * 100)
  return (
    <div className="mt-1">
      <div className="flex justify-between text-[10px] text-slate-500 mb-1">
        <span>Circulante</span>
        <span>{pct.toFixed(1)}% del máximo</span>
      </div>
      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full bg-gradient-to-r from-blue-500 to-blue-400"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function MetricRow({ label, children }: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] text-slate-500 uppercase tracking-wide">{label}</span>
      <div className="text-sm text-white">{children}</div>
    </div>
  )
}

function ProjectCard({ info, symbol }: Readonly<{ info: AssetInfo; symbol: string }>) {
  const [expanded, setExpanded] = useState(false)

  const plainDescription = info.description
    ? info.description.replace(/<[^>]+>/g, '').trim()
    : null

  const truncated = plainDescription && plainDescription.length > 280
  const displayDescription = truncated && !expanded
    ? plainDescription.slice(0, 280) + '…'
    : plainDescription

  const links: { label: string; href: string | null; icon: React.ReactNode }[] = [
    { label: 'Web oficial',  href: info.homepage,   icon: <GlobeIcon /> },
    { label: 'Whitepaper',   href: info.whitepaper, icon: <DocumentIcon /> },
    { label: 'Twitter / X',  href: info.twitter,    icon: <XIcon /> },
    { label: 'Reddit',       href: info.reddit,     icon: <RedditIcon /> },
    { label: 'Telegram',     href: info.telegram,   icon: <TelegramIcon /> },
    { label: 'GitHub',       href: info.github,     icon: <GitHubIcon /> },
  ].filter((l) => l.href)

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden mb-6">
      {/* Header */}
      <div className="px-6 py-4 border-b border-slate-700/60 flex items-center gap-3">
        <div className="w-1 h-5 rounded-full bg-blue-500" />
        <h2 className="text-sm font-semibold text-white">Información del proyecto</h2>
        <span className="ml-auto text-xs text-slate-500 font-mono">{symbol}</span>
      </div>

      <div className="p-6 space-y-6">
        {/* Descripción */}
        {displayDescription && (
          <div>
            <p className="text-sm text-slate-300 leading-relaxed">{displayDescription}</p>
            {truncated && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="text-xs text-blue-400 hover:text-blue-300 mt-2 transition-colors"
              >
                {expanded ? 'Leer menos ↑' : 'Leer más ↓'}
              </button>
            )}
          </div>
        )}

        {/* Categorías */}
        {info.categories.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {info.categories.map((cat) => (
              <span
                key={cat}
                className="px-2.5 py-0.5 rounded-full text-xs bg-blue-500/10 text-blue-400 border border-blue-500/20"
              >
                {cat}
              </span>
            ))}
          </div>
        )}

        {/* Dos columnas: métricas + enlaces */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {/* Métricas de mercado */}
          <div className="space-y-4">
            <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Datos de mercado</p>

            {info.ath != null && (
              <MetricRow label="ATH">
                <span className="font-mono tabular-nums">{formatPrice(String(info.ath))}</span>
                {info.ath_date && (
                  <span className="text-slate-500 text-xs ml-2">
                    {new Date(info.ath_date).toLocaleDateString('es-ES', { year: 'numeric', month: 'short', day: 'numeric' })}
                  </span>
                )}
              </MetricRow>
            )}

            {info.circulating_supply != null && (
              <MetricRow label="Suministro circulante">
                <span className="font-mono tabular-nums">{formatNumber(info.circulating_supply)} {symbol}</span>
                {info.max_supply != null && (
                  <SupplyBar circulating={info.circulating_supply} max={info.max_supply} />
                )}
              </MetricRow>
            )}

            {info.max_supply != null && (
              <MetricRow label="Suministro máximo">
                <span className="font-mono tabular-nums">{formatNumber(info.max_supply)} {symbol}</span>
              </MetricRow>
            )}
          </div>

          {/* Enlaces */}
          {links.length > 0 && (
            <div className="space-y-4">
              <p className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Enlaces</p>
              <div className="grid grid-cols-1 gap-2">
                {links.map(({ label, href, icon }) => (
                  <a
                    key={label}
                    href={href!}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-slate-700/40 hover:bg-slate-700 border border-slate-700/60 text-sm text-slate-200 hover:text-white transition-colors group"
                  >
                    <span className="text-blue-400 group-hover:text-blue-300 transition-colors">{icon}</span>
                    <span className="flex-1">{label}</span>
                    <span className="text-slate-600 group-hover:text-slate-400 text-xs transition-colors">↗</span>
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

