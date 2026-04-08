/**
 * components/OhlcvChart.tsx — Gráfico de velas OHLCV con herramientas de dibujo.
 *
 * Usa KLineChart (Apache 2.0) — librería financiera con soporte nativo de:
 *   - Drawing tools: Fibonacci, canales, pitchfork, tendencias, medición...
 *   - Indicadores técnicos built-in: MA, Bollinger, RSI, MACD, Volumen...
 *   - Datos reales de Binance via backend
 *
 * Props:
 *   symbol          — símbolo del activo (ej: "BTC")
 *   initialInterval — intervalo de las velas (ej: "1h")
 *   height          — altura del área de gráfico en px (default 460)
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { init, dispose } from 'klinecharts'
import type { Chart as KLChart } from 'klinecharts'
import { marketService, type OhlcvInterval } from '@/services/marketService'

// ── Intervalos disponibles ─────────────────────────────────────────

const INTERVALS: { label: string; value: OhlcvInterval }[] = [
  { label: '1m',  value: '1m'  },
  { label: '15m', value: '15m' },
  { label: '1h',  value: '1h'  },
  { label: '4h',  value: '4h'  },
  { label: '1d',  value: '1d'  },
  { label: '1w',  value: '1w'  },
]

// ── Herramientas de dibujo ─────────────────────────────────────────

interface DrawTool {
  id: string
  label: string
  icon: string
}

const DRAW_TOOLS: DrawTool[] = [
  { id: 'segment',                label: 'Tendencia',  icon: '╱'  },
  { id: 'horizontalStraightLine', label: 'Horizontal', icon: '—'  },
  { id: 'verticalStraightLine',   label: 'Vertical',   icon: '│'  },
  { id: 'fibonacciLine',          label: 'Fibonacci',  icon: 'φ'  },
  { id: 'fibonacciExtension',     label: 'Fib. Ext.',  icon: 'φ↑' },
  { id: 'priceChannelLine',       label: 'Canal',      icon: '⧈'  },
  { id: 'andrewsPitchfork',       label: 'Pitchfork',  icon: '⑁'  },
  { id: 'measurementTool',        label: 'Medición',   icon: '↔'  },
  { id: 'rect',                   label: 'Rectángulo', icon: '▭'  },
]

// ── Tema oscuro (palette Tailwind slate) ───────────────────────────

/* eslint-disable @typescript-eslint/no-explicit-any */
const DARK_STYLES: Record<string, any> = {
  grid: {
    horizontal: { color: '#1e293b', size: 1 },
    vertical:   { color: '#1e293b', size: 1 },
  },
  candle: {
    bar: {
      upColor:             '#22c55e',
      downColor:           '#ef4444',
      noChangeColor:       '#94a3b8',
      upBorderColor:       '#22c55e',
      downBorderColor:     '#ef4444',
      noChangeBorderColor: '#94a3b8',
      upWickColor:         '#22c55e',
      downWickColor:       '#ef4444',
      noChangeWickColor:   '#94a3b8',
    },
    tooltip: {
      text: { color: '#94a3b8', size: 12 },
    },
  },
  xAxis: {
    axisLine: { color: '#334155' },
    tickLine: { color: '#334155' },
    tickText: { color: '#64748b', size: 11 },
  },
  yAxis: {
    axisLine: { color: '#334155' },
    tickLine: { color: '#334155' },
    tickText: { color: '#64748b', size: 11 },
  },
  crosshair: {
    horizontal: {
      line: { color: '#475569', style: 'dashed', dashedValue: [4, 4] },
      text: { backgroundColor: '#1d4ed8', color: '#ffffff', size: 11 },
    },
    vertical: {
      line: { color: '#475569', style: 'dashed', dashedValue: [4, 4] },
      text: { backgroundColor: '#1d4ed8', color: '#ffffff', size: 11 },
    },
  },
  separator: {
    color: '#334155',
    activeBackgroundColor: '#475569',
  },
}

// ── Componente ─────────────────────────────────────────────────────

interface Props {
  readonly symbol: string
  readonly initialInterval?: OhlcvInterval
  readonly height?: number
}

export default function OhlcvChart({
  symbol,
  initialInterval = '1h',
  height = 460,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<KLChart | null>(null)

  const [interval, setInterval] = useState<OhlcvInterval>(initialInterval)
  const [isLoading, setIsLoading]   = useState(true)
  const [error, setError]           = useState<string | null>(null)
  const [activeTool, setActiveTool] = useState<string | null>(null)

  // ── Inicializar chart (solo al montar) ────────────────────────
  useEffect(() => {
    if (!containerRef.current) return

    const chart = init(containerRef.current, { styles: DARK_STYLES as any })
    if (!chart) return

    chartRef.current = chart

    // Indicadores por defecto sobre las velas
    chart.createIndicator({ name: 'MA', calcParams: [7, 25, 99] } as any, true)
    // Volumen en un panel separado inferior
    chart.createIndicator('VOL', false, { height: 80, minHeight: 60 })

    // Resize responsivo
    const container = containerRef.current
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(container)

    return () => {
      ro.disconnect()
      dispose(container)
      chartRef.current = null
    }
  }, []) // Solo al montar

  // ── Cargar datos cuando cambia symbol o interval ───────────────
  const loadData = useCallback(async () => {
    if (!chartRef.current) return
    setIsLoading(true)
    setError(null)

    try {
      const candles = await marketService.getOhlcv(symbol, interval, 300)

      const data = candles
        .map((c) => ({
          timestamp: new Date(c.open_time).getTime(), // KLineChart usa milisegundos
          open:      Number.parseFloat(c.open),
          high:      Number.parseFloat(c.high),
          low:       Number.parseFloat(c.low),
          close:     Number.parseFloat(c.close),
          volume:    Number.parseFloat(c.volume),
        }))
        .sort((a, b) => a.timestamp - b.timestamp)

      chartRef.current.applyNewData(data)
    } catch {
      setError('No se pudieron cargar los datos del gráfico.')
    } finally {
      setIsLoading(false)
    }
  }, [symbol, interval])

  useEffect(() => {
    loadData()
  }, [loadData])

  // ── Handlers de herramientas de dibujo ─────────────────────────
  function handleToolClick(toolId: string) {
    if (!chartRef.current) return

    if (activeTool === toolId) {
      // Toggle off: el usuario ya está dibujando — limpiar estado visual
      setActiveTool(null)
      return
    }

    setActiveTool(toolId)
    chartRef.current.createOverlay({
      name: toolId,
      onDrawEnd: () => {
        // El dibujo se ha completado — resetear indicador visual
        setActiveTool(null)
        return false
      },
    } as any)
  }

  function handleClearOverlays() {
    chartRef.current?.removeOverlay()
    setActiveTool(null)
  }

  function handleIntervalChange(newInterval: OhlcvInterval) {
    setActiveTool(null)
    setInterval(newInterval)
  }

  // ── Render ─────────────────────────────────────────────────────
  const activeToolLabel = DRAW_TOOLS.find((t) => t.id === activeTool)?.label

  return (
    <div className="bg-slate-900 rounded-xl border border-slate-700 overflow-hidden">

      {/* ── Barra superior: título + selectores de intervalo ────── */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white">
            {symbol}/USDT
          </span>
          {activeToolLabel && (
            <span className="text-xs text-blue-400 bg-blue-900/40 px-2 py-0.5 rounded-full">
              Dibujando: {activeToolLabel}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          {INTERVALS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => handleIntervalChange(opt.value)}
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

      {/* ── Barra de herramientas de dibujo ─────────────────────── */}
      <div className="flex items-center gap-0.5 px-3 py-1.5 border-b border-slate-700/60 bg-slate-800/50 flex-wrap">
        <span className="text-[10px] text-slate-500 mr-2 uppercase tracking-wide">
          Dibujo
        </span>

        {DRAW_TOOLS.map((tool) => (
          <button
            key={tool.id}
            onClick={() => handleToolClick(tool.id)}
            title={tool.label}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs transition-colors ${
              activeTool === tool.id
                ? 'bg-blue-600 text-white'
                : 'text-slate-300 hover:text-white hover:bg-slate-700'
            }`}
          >
            <span className="font-mono">{tool.icon}</span>
            <span className="hidden md:inline text-[11px]">{tool.label}</span>
          </button>
        ))}

        <div className="w-px h-4 bg-slate-600 mx-1.5" />

        <button
          onClick={handleClearOverlays}
          title="Eliminar todos los dibujos"
          className="flex items-center gap-1 px-2 py-0.5 rounded text-xs text-slate-400 hover:text-red-400 hover:bg-red-900/20 transition-colors"
        >
          <span>✕</span>
          <span className="hidden md:inline text-[11px]">Limpiar</span>
        </button>
      </div>

      {/* ── Área del gráfico ─────────────────────────────────────── */}
      <div className="relative">
        {isLoading && (
          <div
            className="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-10"
            style={{ height }}
          >
            <span className="text-slate-400 text-sm animate-pulse">Cargando datos...</span>
          </div>
        )}
        {error && !isLoading && (
          <div
            className="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-10"
            style={{ height }}
          >
            <span className="text-red-400 text-sm">{error}</span>
          </div>
        )}
        {/* KLineChart monta sus canvas aquí. bg-slate-900 actúa de fondo del canvas. */}
        <div ref={containerRef} className="bg-slate-900" style={{ height }} />
      </div>
    </div>
  )
}
