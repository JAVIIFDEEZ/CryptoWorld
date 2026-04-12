/**
 * components/OhlcvChart.tsx — Gráfico profesional tipo TradingView.
 *
 * KLineChart v9 con:
 *   - 15 herramientas de dibujo built-in verificadas
 *   - 20+ indicadores técnicos toggleables
 *   - Gráfico redimensionable (drag vertical)
 *   - Modo imán, deshacer, limpiar, tipo de gráfico
 *   - Zoom con botones + rueda, scroll temporal
 *   - Datos reales de Binance via backend
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { init, dispose } from 'klinecharts'
import type { Chart as KLChart } from 'klinecharts'
import { marketService, type OhlcvInterval } from '@/services/marketService'

/* eslint-disable @typescript-eslint/no-explicit-any */

// ── Intervalos ────────────────────────────────────────────────────

const INTERVALS: { label: string; value: OhlcvInterval }[] = [
  { label: '1m',  value: '1m'  },
  { label: '5m',  value: '5m'  },
  { label: '15m', value: '15m' },
  { label: '1h',  value: '1h'  },
  { label: '4h',  value: '4h'  },
  { label: '1d',  value: '1d'  },
  { label: '1w',  value: '1w'  },
]

// ── Herramientas de dibujo ────────────────────────────────────────
// SOLO los 15 built-in overlays verificados en KLineChart v9 docs.

interface ToolItem { readonly id: string; readonly label: string; readonly icon: string }
interface ToolCategory {
  readonly key: string
  readonly label: string
  readonly tools: readonly ToolItem[]
}

const TOOL_CATEGORIES: readonly ToolCategory[] = [
  {
    key: 'trending', label: 'Tendencia',
    tools: [
      { id: 'segment',        label: 'Segmento',      icon: '╱' },
      { id: 'straightLine',   label: 'Línea recta',    icon: '⟋' },
      { id: 'rayLine',        label: 'Rayo',           icon: '→' },
      { id: 'priceLine',      label: 'Línea de precio', icon: '$' },
    ],
  },
  {
    key: 'horizontal', label: 'Horizontal / Vertical',
    tools: [
      { id: 'horizontalStraightLine', label: 'Horizontal',            icon: '─' },
      { id: 'horizontalRayLine',      label: 'Rayo horizontal',       icon: '⟶' },
      { id: 'horizontalSegment',      label: 'Segmento horizontal',   icon: '━' },
      { id: 'verticalStraightLine',   label: 'Vertical',              icon: '│' },
      { id: 'verticalRayLine',        label: 'Rayo vertical',         icon: '↓' },
      { id: 'verticalSegment',        label: 'Segmento vertical',     icon: '┃' },
    ],
  },
  {
    key: 'tools', label: 'Herramientas',
    tools: [
      { id: 'parallelStraightLine', label: 'Canal paralelo',  icon: '⫼' },
      { id: 'priceChannelLine',     label: 'Canal de precio',  icon: '⫿' },
      { id: 'fibonacciLine',        label: 'Fibonacci',        icon: 'φ' },
      { id: 'simpleAnnotation',     label: 'Anotación',        icon: '📝' },
      { id: 'simpleTag',            label: 'Etiqueta',         icon: '🏷' },
    ],
  },
]

// ── Indicadores disponibles ───────────────────────────────────────
// Documentación: Solo BBI, BOLL, EMA, MA, SAR, SMA son candle-compatible.

interface IndicatorDef {
  readonly name: string
  readonly label: string
  readonly onCandle: boolean
}

const INDICATORS: readonly IndicatorDef[] = [
  // Sobre velas (candle-compatible)
  { name: 'MA',   label: 'MA (Media Móvil)',    onCandle: true  },
  { name: 'EMA',  label: 'EMA',                 onCandle: true  },
  { name: 'SMA',  label: 'SMA',                 onCandle: true  },
  { name: 'BOLL', label: 'Bollinger',           onCandle: true  },
  { name: 'SAR',  label: 'SAR Parabólico',      onCandle: true  },
  { name: 'BBI',  label: 'BBI',                 onCandle: true  },
  // Sub-paneles
  { name: 'VOL',  label: 'Volumen',             onCandle: false },
  { name: 'MACD', label: 'MACD',                onCandle: false },
  { name: 'RSI',  label: 'RSI',                 onCandle: false },
  { name: 'KDJ',  label: 'KDJ',                 onCandle: false },
  { name: 'OBV',  label: 'OBV',                 onCandle: false },
  { name: 'CCI',  label: 'CCI',                 onCandle: false },
  { name: 'WR',   label: 'Williams %R',         onCandle: false },
  { name: 'MTM',  label: 'Momentum',            onCandle: false },
  { name: 'DMI',  label: 'DMI',                 onCandle: false },
  { name: 'CR',   label: 'CR',                  onCandle: false },
  { name: 'AO',   label: 'Awesome Osc.',        onCandle: false },
  { name: 'BIAS', label: 'BIAS',                onCandle: false },
  { name: 'BRAR', label: 'BRAR',                onCandle: false },
  { name: 'PSY',  label: 'PSY',                 onCandle: false },
  { name: 'DMA',  label: 'DMA',                 onCandle: false },
  { name: 'TRIX', label: 'TRIX',                onCandle: false },
  { name: 'ROC',  label: 'ROC',                 onCandle: false },
  { name: 'VR',   label: 'VR',                  onCandle: false },
  { name: 'EMV',  label: 'EMV',                 onCandle: false },
  { name: 'PVT',  label: 'PVT',                 onCandle: false },
]

// ── Tipos de gráfico ─────────────────────────────────────────────

const CHART_TYPES = [
  { type: 'candle_solid',  label: 'Velas',    icon: '🕯' },
  { type: 'candle_stroke', label: 'Huecas',   icon: '⬜' },
  { type: 'ohlc',          label: 'OHLC',     icon: '┤' },
  { type: 'area',          label: 'Área',     icon: '▓' },
] as const

// ── Tema oscuro ──────────────────────────────────────────────────

const DARK_STYLES: Record<string, any> = {
  grid: {
    horizontal: { color: '#1e293b', size: 1 },
    vertical:   { color: '#1e293b', size: 1 },
  },
  candle: {
    bar: {
      upColor: '#22c55e', downColor: '#ef4444', noChangeColor: '#94a3b8',
      upBorderColor: '#22c55e', downBorderColor: '#ef4444', noChangeBorderColor: '#94a3b8',
      upWickColor: '#22c55e', downWickColor: '#ef4444', noChangeWickColor: '#94a3b8',
    },
    tooltip: {
      showRule: 'follow_cross',
      text: { color: '#94a3b8', size: 12 },
    },
    priceMark: {
      last: { show: true, upColor: '#22c55e', downColor: '#ef4444', noChangeColor: '#94a3b8' },
    },
  },
  indicator: {
    tooltip: { text: { color: '#94a3b8', size: 11 } },
  },
  xAxis: {
    axisLine: { color: '#334155' }, tickLine: { color: '#334155' },
    tickText: { color: '#64748b', size: 11 },
  },
  yAxis: {
    axisLine: { color: '#334155' }, tickLine: { color: '#334155' },
    tickText: { color: '#64748b', size: 11 },
  },
  crosshair: {
    show: true,
    horizontal: {
      show: true,
      line: { show: true, color: '#475569', style: 'dashed', dashedValue: [4, 4] },
      text: { show: true, backgroundColor: '#1d4ed8', color: '#fff', size: 11 },
    },
    vertical: {
      show: true,
      line: { show: true, color: '#475569', style: 'dashed', dashedValue: [4, 4] },
      text: { show: true, backgroundColor: '#1d4ed8', color: '#fff', size: 11 },
    },
  },
  overlay: {
    point: {
      color: '#3b82f6', borderColor: '#3b82f6', borderSize: 1, radius: 4,
      activeColor: '#60a5fa', activeBorderColor: '#60a5fa', activeBorderSize: 2, activeRadius: 6,
    },
    line: { color: '#3b82f6', size: 1.5 },
    text: { color: '#e2e8f0', size: 12, backgroundColor: '#1e293b', borderColor: '#334155' },
  },
  separator: { color: '#334155', size: 2, activeBackgroundColor: '#475569' },
}

// ── Constantes ───────────────────────────────────────────────────

const MIN_HEIGHT = 300
const MAX_HEIGHT = 900
const DEFAULT_HEIGHT = 520

// ══════════════════════════════════════════════════════════════════
// Componente
// ══════════════════════════════════════════════════════════════════

interface Props {
  readonly symbol: string
  readonly initialInterval?: OhlcvInterval
}

export default function OhlcvChart({ symbol, initialInterval = '1h' }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef     = useRef<KLChart | null>(null)

  // Estado
  const [interval, setInterval]                 = useState<OhlcvInterval>(initialInterval)
  const [isLoading, setIsLoading]               = useState(true)
  const [error, setError]                       = useState<string | null>(null)
  const [chartHeight, setChartHeight]           = useState(DEFAULT_HEIGHT)
  const [dataSource, setDataSource]             = useState<string | null>(null)

  // Herramientas
  const [activeTool, setActiveTool]             = useState<string | null>(null)
  const [openDropdown, setOpenDropdown]         = useState<string | null>(null)
  const [magnetOn, setMagnetOn]                 = useState(false)
  const overlayIds                              = useRef<string[]>([])

  // Indicadores
  const [showIndicators, setShowIndicators]     = useState(false)
  const [activeIndicators, setActiveIndicators] = useState<Set<string>>(() => new Set(['MA', 'VOL']))
  const indicatorPaneMap                        = useRef<Map<string, string>>(new Map())

  // Tipo de gráfico
  const [chartType, setChartType]               = useState<string>('candle_solid')
  const [showChartTypes, setShowChartTypes]     = useState(false)

  // Resize handle
  const resizingRef = useRef(false)
  const startYRef   = useRef(0)
  const startHRef   = useRef(0)

  // ── Cerrar popups ─────────────────────────────────────────────
  function closePopups() {
    setOpenDropdown(null)
    setShowIndicators(false)
    setShowChartTypes(false)
  }

  // ── Inicializar chart ─────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return
    const chart = init(containerRef.current, { styles: DARK_STYLES as any })
    if (!chart) return
    chartRef.current = chart

    // Indicadores iniciales
    const maPaneId  = chart.createIndicator({ name: 'MA', calcParams: [7, 25, 99] } as any, true)
    const volPaneId = chart.createIndicator('VOL', false, { height: 80, minHeight: 60 })
    if (maPaneId)  indicatorPaneMap.current.set('MA',  maPaneId)
    if (volPaneId) indicatorPaneMap.current.set('VOL', volPaneId)

    const container = containerRef.current
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(container)

    return () => {
      ro.disconnect()
      dispose(container)
      chartRef.current = null
    }
  }, [])

  // ── Cargar datos ──────────────────────────────────────────────
  const loadData = useCallback(async () => {
    if (!chartRef.current) return
    setIsLoading(true)
    setError(null)
    try {
      const response = await marketService.getOhlcv(symbol, interval, 300)
      setDataSource(response.source)
      const data = response.candles
        .map((c) => ({
          timestamp: new Date(c.open_time).getTime(),
          open:      Number.parseFloat(c.open),
          high:      Number.parseFloat(c.high),
          low:       Number.parseFloat(c.low),
          close:     Number.parseFloat(c.close),
          volume:    Number.parseFloat(c.volume),
        }))
        .sort((a, b) => a.timestamp - b.timestamp)
      chartRef.current.applyNewData(data)

      // Si la fuente es CoinGecko (sin volumen), quitar indicador VOL
      if (response.source === 'coingecko') {
        const volPaneId = indicatorPaneMap.current.get('VOL')
        if (volPaneId) {
          chartRef.current.removeIndicator(volPaneId, 'VOL')
          indicatorPaneMap.current.delete('VOL')
          setActiveIndicators((prev: Set<string>) => { const s = new Set(prev); s.delete('VOL'); return s })
        }
      }
    } catch (err: any) {
      if (err?.response?.status === 404) {
        setError(`No hay datos de gráfico disponibles para ${symbol}. El activo no está listado en Binance ni tiene datos en CoinGecko.`)
      } else {
        setError('No se pudieron cargar los datos del gráfico.')
      }
    } finally {
      setIsLoading(false)
    }
  }, [symbol, interval])

  useEffect(() => { loadData() }, [loadData])

  // ── Cambiar tipo de gráfico ───────────────────────────────────
  useEffect(() => {
    if (!chartRef.current) return
    chartRef.current.setStyles({
      candle: { type: chartType },
    } as any)
  }, [chartType])

  // ── Herramienta de dibujo ─────────────────────────────────────
  function selectDrawTool(toolId: string) {
    if (!chartRef.current) return
    setActiveTool(toolId)
    setOpenDropdown(null)

    const id = chartRef.current.createOverlay({
      name: toolId,
      mode: magnetOn ? 'weak_magnet' : 'normal',
      onDrawEnd: () => { setActiveTool(null); return false },
    } as any)

    if (typeof id === 'string') overlayIds.current.push(id)
  }

  function undoLastOverlay() {
    const id = overlayIds.current.pop()
    if (id) chartRef.current?.removeOverlay({ id } as any)
  }

  function clearAllOverlays() {
    chartRef.current?.removeOverlay()
    overlayIds.current = []
    setActiveTool(null)
  }

  function cancelCurrentDraw() {
    if (!activeTool) return
    chartRef.current?.removeOverlay()
    setActiveTool(null)
  }

  // ── Indicadores ───────────────────────────────────────────────
  function toggleIndicator(def: IndicatorDef) {
    const chart = chartRef.current
    if (!chart) return

    // Bloquear indicadores de volumen si la fuente es CoinGecko
    if (dataSource === 'coingecko' && (def.name === 'VOL' || def.name === 'OBV' || def.name === 'PVT' || def.name === 'VR' || def.name === 'EMV')) {
      return
    }

    if (activeIndicators.has(def.name)) {
      const paneId = indicatorPaneMap.current.get(def.name)
      if (paneId) chart.removeIndicator(paneId, def.name)
      indicatorPaneMap.current.delete(def.name)
      setActiveIndicators((prev: Set<string>) => { const s = new Set(prev); s.delete(def.name); return s })
    } else {
      let paneId: string | null = null
      if (def.onCandle) {
        paneId = chart.createIndicator(def.name, true, { id: 'candle_pane' }) as string | null
      } else {
        paneId = chart.createIndicator(def.name, false, { height: 80, minHeight: 60 }) as string | null
      }
      if (paneId) indicatorPaneMap.current.set(def.name, paneId)
      setActiveIndicators((prev: Set<string>) => new Set(prev).add(def.name))
    }
  }

  // ── Zoom ──────────────────────────────────────────────────────
  function zoomIn()  { chartRef.current?.zoomAtCoordinate?.(1.2 as any) }
  function zoomOut() { chartRef.current?.zoomAtCoordinate?.(0.8 as any) }
  function scrollToEnd() { chartRef.current?.scrollToRealTime?.() }

  // ── Resize handle ─────────────────────────────────────────────
  function handleResizeStart(e: React.MouseEvent) {
    e.preventDefault()
    resizingRef.current = true
    startYRef.current = e.clientY
    startHRef.current = chartHeight

    function handleResizeMove(ev: MouseEvent) {
      if (!resizingRef.current) return
      const delta = ev.clientY - startYRef.current
      const newH = Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, startHRef.current + delta))
      setChartHeight(newH)
    }

    function handleResizeEnd() {
      resizingRef.current = false
      document.removeEventListener('mousemove', handleResizeMove)
      document.removeEventListener('mouseup', handleResizeEnd)
      setTimeout(() => chartRef.current?.resize(), 0)
    }

    document.addEventListener('mousemove', handleResizeMove)
    document.addEventListener('mouseup', handleResizeEnd)
  }

  // ── Escape para cancelar dibujo ───────────────────────────────
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') cancelCurrentDraw()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  })

  // ── Helpers para render ───────────────────────────────────────
  const allTools     = TOOL_CATEGORIES.flatMap((c) => c.tools)
  const activeLabel  = allTools.find((t) => t.id === activeTool)?.label
  const candleInds   = INDICATORS.filter((i) => i.onCandle)
  const subPaneInds  = INDICATORS.filter((i) => !i.onCandle)
  const VOLUME_INDICATORS = new Set(['VOL', 'OBV', 'PVT', 'VR', 'EMV'])

  // ══════════════════════════════════════════════════════════════
  // JSX
  // ══════════════════════════════════════════════════════════════

  return (
    <div
      className="bg-slate-900 rounded-xl border border-slate-700 select-none"
      onClick={closePopups}
    >
      {/* ── Barra superior ─────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-slate-700">

        {/* Symbol + intervals */}
        <span className="text-sm font-bold text-white mr-1">{symbol}/USDT</span>

        {/* Data source badge */}
        {dataSource && (
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded-full font-medium ${
              dataSource === 'binance'
                ? 'bg-green-900/40 text-green-400 border border-green-700/50'
                : 'bg-amber-900/40 text-amber-400 border border-amber-700/50'
            }`}
            title={
              dataSource === 'binance'
                ? 'Datos OHLCV completos de Binance (incluye volumen)'
                : 'Datos OHLC de CoinGecko (sin volumen real)'
            }
          >
            {dataSource === 'binance' ? '● Binance' : '● CoinGecko'}
          </span>
        )}

        <div className="flex gap-0.5 bg-slate-800 rounded-md p-0.5">
          {INTERVALS.map((o) => (
            <button
              key={o.value}
              onClick={(e: React.MouseEvent) => { e.stopPropagation(); setInterval(o.value) }}
              className={`px-2 py-0.5 rounded text-xs font-medium transition-colors ${
                interval === o.value ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>

        <div className="w-px h-5 bg-slate-700 mx-1" />

        {/* Tipo de gráfico */}
        <div className="relative" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
          <button
            onClick={() => { setShowChartTypes((v: boolean) => !v); setOpenDropdown(null); setShowIndicators(false) }}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
            title="Tipo de gráfico"
          >
            {CHART_TYPES.find((ct) => ct.type === chartType)?.icon ?? '🕯'} Tipo ▾
          </button>
          {showChartTypes && (
            <div className="absolute left-0 top-full mt-1 w-40 bg-slate-800 border border-slate-600 rounded-lg shadow-2xl z-50 py-1">
              {CHART_TYPES.map((ct) => (
                <button
                  key={ct.type}
                  onClick={() => { setChartType(ct.type); setShowChartTypes(false) }}
                  className={`w-full text-left flex items-center gap-2 px-3 py-1.5 text-xs transition-colors ${
                    chartType === ct.type ? 'bg-blue-600/30 text-blue-300' : 'text-slate-200 hover:bg-slate-700'
                  }`}
                >
                  <span>{ct.icon}</span> {ct.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Indicadores */}
        <div className="relative" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
          <button
            onClick={() => { setShowIndicators((v: boolean) => !v); setOpenDropdown(null); setShowChartTypes(false) }}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
              showIndicators ? 'bg-blue-600 text-white' : 'text-slate-300 hover:text-white hover:bg-slate-700'
            }`}
          >
            📊 Indicadores
            <span className="text-[10px] bg-slate-600 text-slate-200 rounded-full w-4 h-4 inline-flex items-center justify-center ml-0.5">
              {activeIndicators.size}
            </span>
          </button>

          {showIndicators && (
            <div className="absolute left-0 top-full mt-1 w-56 bg-slate-800 border border-slate-600 rounded-lg shadow-2xl z-50 py-1 max-h-[420px] overflow-y-auto">
              {/* Sobre velas */}
              <div className="px-3 py-1.5 text-[10px] text-slate-500 uppercase tracking-wider font-semibold">
                Sobre velas
              </div>
              {candleInds.map((ind) => (
                <button
                  key={ind.name}
                  onClick={() => toggleIndicator(ind)}
                  className="w-full flex items-center justify-between px-3 py-1.5 text-xs hover:bg-slate-700 transition-colors"
                >
                  <span className="text-slate-200">{ind.label}</span>
                  {activeIndicators.has(ind.name)
                    ? <span className="text-green-400 text-sm font-bold">✓</span>
                    : <span className="text-slate-600 text-sm">○</span>}
                </button>
              ))}
              {/* Sub-paneles */}
              <div className="px-3 py-1.5 text-[10px] text-slate-500 uppercase tracking-wider font-semibold border-t border-slate-700 mt-1">
                Sub-paneles
              </div>
              {subPaneInds.map((ind) => {
                const isVolDisabled = dataSource === 'coingecko' && VOLUME_INDICATORS.has(ind.name)
                return (
                <button
                  key={ind.name}
                  onClick={() => toggleIndicator(ind)}
                  className={`w-full flex items-center justify-between px-3 py-1.5 text-xs transition-colors ${
                    isVolDisabled ? 'opacity-40 cursor-not-allowed' : 'hover:bg-slate-700'
                  }`}
                  disabled={isVolDisabled}
                  title={isVolDisabled ? 'No disponible (fuente CoinGecko sin volumen)' : ind.label}
                >
                  <span className="text-slate-200">{ind.label}{isVolDisabled ? ' ⚠' : ''}</span>
                  {activeIndicators.has(ind.name)
                    ? <span className="text-green-400 text-sm font-bold">✓</span>
                    : <span className="text-slate-600 text-sm">○</span>}
                </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Zoom / scroll controls */}
        <div className="flex items-center gap-0.5">
          <button onClick={(e: React.MouseEvent) => { e.stopPropagation(); zoomIn() }} title="Zoom +" className="px-1.5 py-0.5 rounded text-xs text-slate-400 hover:text-white hover:bg-slate-700 transition-colors">＋</button>
          <button onClick={(e: React.MouseEvent) => { e.stopPropagation(); zoomOut() }} title="Zoom −" className="px-1.5 py-0.5 rounded text-xs text-slate-400 hover:text-white hover:bg-slate-700 transition-colors">−</button>
          <button onClick={(e: React.MouseEvent) => { e.stopPropagation(); scrollToEnd() }} title="Ir al último dato" className="px-1.5 py-0.5 rounded text-xs text-slate-400 hover:text-white hover:bg-slate-700 transition-colors">▸▸</button>
        </div>

        {/* Magnet */}
        <button
          onClick={(e: React.MouseEvent) => { e.stopPropagation(); setMagnetOn((v: boolean) => !v) }}
          title={magnetOn ? 'Desactivar imán' : 'Activar imán (snap OHLC)'}
          className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
            magnetOn ? 'bg-amber-600 text-white' : 'text-slate-400 hover:text-white hover:bg-slate-700'
          }`}
        >
          🧲
        </button>
      </div>

      {/* ── Barra de herramientas de dibujo ──────────────────────── */}
      <div className="flex items-center gap-0.5 px-2 py-1 border-b border-slate-700/60 bg-slate-800/40 flex-wrap">

        {/* Category dropdowns */}
        {TOOL_CATEGORIES.map((cat) => (
          <div key={cat.key} className="relative" onClick={(e: React.MouseEvent) => e.stopPropagation()}>
            <button
              onClick={() => { setOpenDropdown(openDropdown === cat.key ? null : cat.key); setShowIndicators(false); setShowChartTypes(false) }}
              title={cat.label}
              className={`flex items-center gap-1 px-2 py-1 rounded text-xs whitespace-nowrap transition-colors ${
                openDropdown === cat.key
                  ? 'bg-slate-600 text-white'
                  : 'text-slate-300 hover:text-white hover:bg-slate-700'
              }`}
            >
              <span className="text-[11px]">{cat.label}</span>
              <span className="text-[9px] text-slate-500">▾</span>
            </button>

            {openDropdown === cat.key && (
              <div className="absolute left-0 bottom-full mb-0.5 w-52 bg-slate-800 border border-slate-600 rounded-lg shadow-2xl z-[9999] py-1">
                {cat.tools.map((tool) => (
                  <button
                    key={tool.id}
                    onClick={() => selectDrawTool(tool.id)}
                    className={`w-full text-left flex items-center gap-2 px-3 py-1.5 text-xs transition-colors ${
                      activeTool === tool.id
                        ? 'bg-blue-600/30 text-blue-300'
                        : 'text-slate-200 hover:bg-slate-700'
                    }`}
                  >
                    <span className="w-5 text-center opacity-70">{tool.icon}</span>
                    {tool.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}

        {/* Separator */}
        <div className="w-px h-4 bg-slate-600 mx-1 shrink-0" />

        {/* Active tool badge */}
        {activeLabel && (
          <span className="text-[11px] text-blue-400 bg-blue-900/30 px-2 py-0.5 rounded-full whitespace-nowrap shrink-0 animate-pulse">
            ● {activeLabel}
            <button
              onClick={(e: React.MouseEvent) => { e.stopPropagation(); cancelCurrentDraw() }}
              className="ml-1.5 text-slate-400 hover:text-red-400"
              title="Cancelar (Esc)"
            >
              ✕
            </button>
          </span>
        )}

        <div className="flex-1" />

        {/* Undo + Clear */}
        <button
          onClick={(e: React.MouseEvent) => { e.stopPropagation(); undoLastOverlay() }}
          title="Deshacer último dibujo"
          className="px-2 py-1 rounded text-xs text-slate-400 hover:text-white hover:bg-slate-700 transition-colors shrink-0"
        >
          ↩ Deshacer
        </button>
        <button
          onClick={(e: React.MouseEvent) => { e.stopPropagation(); clearAllOverlays() }}
          title="Eliminar todos los dibujos"
          className="px-2 py-1 rounded text-xs text-slate-400 hover:text-red-400 hover:bg-red-900/20 transition-colors shrink-0"
        >
          🗑 Limpiar
        </button>
      </div>

      {/* ── Área del gráfico ─────────────────────────────────────── */}
      <div className="relative">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-10" style={{ height: chartHeight }}>
            <span className="text-slate-400 text-sm animate-pulse">Cargando datos...</span>
          </div>
        )}
        {error && !isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-slate-900/80 z-10" style={{ height: chartHeight }}>
            <span className="text-red-400 text-sm">{error}</span>
          </div>
        )}
        <div
          ref={containerRef}
          className="bg-slate-900"
          style={{ height: chartHeight, cursor: activeTool ? 'crosshair' : 'default' }}
        />
      </div>

      {/* ── Barra de redimensión (drag) ──────────────────────────── */}
      <div
        className="h-2 bg-slate-800 hover:bg-slate-700 cursor-row-resize flex items-center justify-center border-t border-slate-700/60 rounded-b-xl transition-colors group"
        onMouseDown={handleResizeStart}
        title="Arrastrar para redimensionar"
      >
        <div className="w-10 h-0.5 bg-slate-600 group-hover:bg-slate-400 rounded-full transition-colors" />
      </div>
    </div>
  )
}
