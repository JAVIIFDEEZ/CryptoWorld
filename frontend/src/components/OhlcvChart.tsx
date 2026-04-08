/**
 * components/OhlcvChart.tsx — Gráfico de velas OHLCV.
 *
 * Usa TradingView Lightweight Charts v4 para mostrar velas OHLCV
 * con datos reales de Binance.
 *
 * Props:
 *   symbol    — símbolo del activo (ej: "BTC")
 *   interval  — intervalo de las velas (ej: "1h", "4h", "1d")
 *   height    — altura del contenedor en px (default 380)
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { createChart, type IChartApi, type ISeriesApi, type UTCTimestamp, ColorType } from 'lightweight-charts'
import { marketService, type OhlcvInterval } from '@/services/marketService'

interface Props {
  symbol: string
  initialInterval?: OhlcvInterval
  height?: number
}

const INTERVALS: { label: string; value: OhlcvInterval }[] = [
  { label: '1m',  value: '1m'  },
  { label: '15m', value: '15m' },
  { label: '1h',  value: '1h'  },
  { label: '4h',  value: '4h'  },
  { label: '1d',  value: '1d'  },
  { label: '1w',  value: '1w'  },
]

// Convierte ISO 8601 a timestamp Unix en segundos (requerido por lightweight-charts v4)
function isoToUnix(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000)
}

export default function OhlcvChart({
  symbol,
  initialInterval = '1h',
  height = 380,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<IChartApi | null>(null)
  const seriesRef    = useRef<ISeriesApi<'Candlestick'> | null>(null)

  const [interval, setInterval]   = useState<OhlcvInterval>(initialInterval)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError]         = useState<string | null>(null)

  // ── Crear el chart una sola vez ───────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: '#0f172a' },
        textColor:  '#94a3b8',
      },
      grid: {
        vertLines:   { color: '#1e293b' },
        horzLines:   { color: '#1e293b' },
      },
      crosshair: {
        vertLine:   { labelBackgroundColor: '#1d4ed8' },
        horzLine:   { labelBackgroundColor: '#1d4ed8' },
      },
      rightPriceScale: {
        borderColor: '#334155',
      },
      timeScale: {
        borderColor:      '#334155',
        timeVisible:      true,
        secondsVisible:   false,
      },
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor:        '#22c55e',
      downColor:      '#ef4444',
      borderUpColor:  '#22c55e',
      borderDownColor:'#ef4444',
      wickUpColor:    '#22c55e',
      wickDownColor:  '#ef4444',
    })

    chartRef.current  = chart
    seriesRef.current = candleSeries

    // Responsive resize
    const observer = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    })
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      chart.remove()
      chartRef.current  = null
      seriesRef.current = null
    }
  }, [height])

  // ── Cargar datos cuando cambia symbol o interval ───────────────
  const loadData = useCallback(async () => {
    if (!seriesRef.current) return
    setIsLoading(true)
    setError(null)

    try {
      const candles = await marketService.getOhlcv(symbol, interval, 200)

      const chartData = candles
        .map((c) => ({
          time:  isoToUnix(c.open_time) as UTCTimestamp,
          open:  parseFloat(c.open),
          high:  parseFloat(c.high),
          low:   parseFloat(c.low),
          close: parseFloat(c.close),
        }))
        // lightweight-charts requiere orden cronológico ascendente
        .sort((a, b) => (a.time as number) - (b.time as number))

      seriesRef.current.setData(chartData)
      chartRef.current?.timeScale().fitContent()
    } catch {
      setError('No se pudieron cargar los datos del gráfico.')
    } finally {
      setIsLoading(false)
    }
  }, [symbol, interval])

  useEffect(() => {
    loadData()
  }, [loadData])

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 overflow-hidden">
      {/* Barra de controles */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
        <span className="text-sm font-semibold text-white">
          {symbol}/USDT — Gráfico de velas
        </span>
        <div className="flex gap-1">
          {INTERVALS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setInterval(opt.value)}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                interval === opt.value
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Área del chart */}
      <div className="relative">
        {isLoading && (
          <div
            className="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-10"
            style={{ height }}
          >
            <span className="text-slate-400 text-sm animate-pulse">Cargando datos...</span>
          </div>
        )}
        {error && (
          <div
            className="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-10"
            style={{ height }}
          >
            <span className="text-red-400 text-sm">{error}</span>
          </div>
        )}
        <div ref={containerRef} style={{ height }} />
      </div>
    </div>
  )
}
