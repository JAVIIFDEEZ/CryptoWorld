/**
 * components/AnalysisPanel.tsx — Panel de análisis técnico avanzado reutilizable.
 *
 * 5 pestañas:
 *   1. Señales        — medidor de sentimiento + semáforos multi-indicador
 *   2. Indicadores    — cálculo detallado con gauge visual contextual
 *   3. Predicción ML  — predicción de dirección + explicación del modelo
 *   4. Patrones       — detección de patrones chartistas con fiabilidad
 *   5. Backtesting    — simulación de estrategia con comparativa vs buy&hold
 */

import { useState, type ReactNode } from 'react'
import {
  analysisService,
  type IntervalType,
  type AnalysisType,
  type SignalsResult,
  type PredictionResult,
  type PatternsResult,
  type BacktestResult,
  type AnalysisResult,
  type StrategyInfo,
} from '@/services/analysisService'
import InfoTooltip from '@/components/ui/InfoTooltip'
import IndicatorsRadar from '@/components/analysis/IndicatorsRadar'

// ── Tipos locales ────────────────────────────────────────────────

type Tab = 'signals' | 'indicator' | 'predict' | 'patterns' | 'backtest'

const TABS: { key: Tab; label: string }[] = [
  { key: 'signals',   label: 'Señales' },
  { key: 'indicator', label: 'Indicadores' },
  { key: 'predict',   label: 'Predicción ML' },
  { key: 'patterns',  label: 'Patrones' },
  { key: 'backtest',  label: 'Backtesting' },
]

const INTERVALS: { label: string; value: IntervalType }[] = [
  { label: '1m',  value: '1m'  },
  { label: '5m',  value: '5m'  },
  { label: '15m', value: '15m' },
  { label: '1h',  value: '1h'  },
  { label: '4h',  value: '4h'  },
  { label: '1d',  value: '1d'  },
]

const ANALYSIS_TYPES: AnalysisType[] = ['RSI', 'MACD', 'SMA', 'EMA', 'BOLLINGER']

// ── Helpers de señal ─────────────────────────────────────────────

function signalColor(signal: string): string {
  switch (signal) {
    case 'COMPRA':
    case 'COMPRA_FUERTE':
      return 'text-green-400'
    case 'VENTA':
    case 'VENTA_FUERTE':
      return 'text-red-400'
    default:
      return 'text-yellow-400'
  }
}

function signalBg(signal: string): string {
  switch (signal) {
    case 'COMPRA':
    case 'COMPRA_FUERTE':
      return 'bg-green-500/20 border-green-500/30'
    case 'VENTA':
    case 'VENTA_FUERTE':
      return 'bg-red-500/20 border-red-500/30'
    default:
      return 'bg-yellow-500/20 border-yellow-500/30'
  }
}

function signalLabel(signal: string): string {
  const map: Record<string, string> = {
    'COMPRA': 'Compra',
    'COMPRA_FUERTE': 'Compra Fuerte',
    'VENTA': 'Venta',
    'VENTA_FUERTE': 'Venta Fuerte',
    'NEUTRAL': 'Neutral',
  }
  return map[signal] ?? signal
}

function signalDot(signal: string): string {
  switch (signal) {
    case 'COMPRA':
    case 'COMPRA_FUERTE':
      return 'bg-green-400'
    case 'VENTA':
    case 'VENTA_FUERTE':
      return 'bg-red-400'
    default:
      return 'bg-yellow-400'
  }
}

function reliabilityBadge(r: string) {
  const colors: Record<string, string> = {
    'ALTA':  'bg-green-600/30 text-green-300',
    'MEDIA': 'bg-yellow-600/30 text-yellow-300',
    'BAJA':  'bg-slate-600/30 text-slate-300',
  }
  return colors[r] ?? 'bg-slate-600/30 text-slate-300'
}

function reliabilityStars(r: string): string {
  const map: Record<string, string> = { 'ALTA': '★★★', 'MEDIA': '★★☆', 'BAJA': '★☆☆' }
  return map[r] ?? '—'
}

// Descripción educativa de 1 frase por indicador. El orden importa:
// los más específicos (Stochastic) se comprueban antes que los genéricos.
function indicatorDescription(name: string): string | null {
  const n = name.toLowerCase()
  if (n.includes('stoch')) return 'Stochastic RSI: aplica el oscilador estocástico sobre el RSI para anticipar giros de precio antes que el RSI clásico.'
  if (n.includes('rsi')) return 'RSI (Índice de Fuerza Relativa): escala de 0 a 100; por encima de 70 indica sobrecompra y por debajo de 30, sobreventa.'
  if (n.includes('macd')) return 'MACD: compara dos medias móviles exponenciales para detectar cambios de momentum y de tendencia.'
  if (n.includes('boll')) return 'Bandas de Bollinger: miden la volatilidad; tocar la banda superior sugiere sobrecompra y la inferior, sobreventa.'
  if (n.includes('sma')) return 'SMA (Media Móvil Simple): precio medio de las últimas N velas; si el precio la supera, la tendencia es alcista.'
  if (n.includes('ema')) return 'EMA (Media Móvil Exponencial): como la SMA pero da más peso a las velas recientes, por lo que reacciona antes.'
  if (n.includes('adx')) return 'ADX: mide la fuerza de la tendencia (no su dirección); por encima de 25 indica una tendencia fuerte.'
  if (n.includes('atr')) return 'ATR (Average True Range): mide la volatilidad media del mercado; valores altos indican movimientos bruscos.'
  if (n.includes('cci')) return 'CCI (Commodity Channel Index): detecta condiciones de sobrecompra/sobreventa y posibles giros de precio.'
  if (n.includes('obv')) return 'OBV (On-Balance Volume): acumula el volumen según la dirección del precio para confirmar tendencias.'
  if (n.includes('vwap')) return 'VWAP: precio medio ponderado por volumen del día; actúa como soporte/resistencia intradiario.'
  if (n.includes('williams')) return 'Williams %R: oscilador de momentum; cerca de 0 indica sobrecompra y cerca de -100, sobreventa.'
  return null
}

// ── Iconos SVG de pestañas ───────────────────────────────────────

function IcoSignals() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  )
}
function IcoIndicator() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
    </svg>
  )
}
function IcoPredict() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
    </svg>
  )
}
function IcoPatterns() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
    </svg>
  )
}
function IcoBacktest() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  )
}

const TAB_ICONS: Record<string, JSX.Element> = {
  signals:   <IcoSignals />,
  indicator: <IcoIndicator />,
  predict:   <IcoPredict />,
  patterns:  <IcoPatterns />,
  backtest:  <IcoBacktest />,
}

// ══════════════════════════════════════════════════════════════════
// Componente principal
// ══════════════════════════════════════════════════════════════════

interface Props {
  symbol: string
}

export default function AnalysisPanel({ symbol }: Props) {
  const [tab, setTab]               = useState<Tab>('signals')
  const [interval, setInterval]     = useState<IntervalType>('1h')
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)

  // ── Signals state ──
  const [signals, setSignals]       = useState<SignalsResult | null>(null)

  // ── Indicator state ──
  const [indType, setIndType]       = useState<AnalysisType>('RSI')
  const [indResult, setIndResult]   = useState<AnalysisResult | null>(null)

  // ── Prediction state ──
  const [horizon, setHorizon]       = useState(5)
  const [prediction, setPrediction] = useState<PredictionResult | null>(null)

  // ── Patterns state ──
  const [patterns, setPatterns]     = useState<PatternsResult | null>(null)

  // ── Backtest state ──
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [selStrategy, setSelStrategy] = useState('')
  const [btResult, setBtResult]     = useState<BacktestResult | null>(null)
  const [showBtAdv, setShowBtAdv]   = useState(false)
  const [commissionBps, setCommissionBps] = useState(10)
  const [slippageBps, setSlippageBps]     = useState(5)
  const [stopLossPct, setStopLossPct]     = useState('')   // % (vacío = sin stop)
  const [takeProfitPct, setTakeProfitPct] = useState('')

  // ── Loaders ────────────────────────────────────────────────────

  async function loadSignals() {
    setLoading(true); setError(null)
    try {
      const res = await analysisService.getSignals(symbol, interval)
      if (res.error) { setError(res.error); setSignals(null) }
      else setSignals(res)
    } catch { setError('Error al obtener señales.') }
    finally { setLoading(false) }
  }

  async function loadIndicator() {
    setLoading(true); setError(null)
    try {
      const res = await analysisService.calculateIndicator({
        asset_symbol: symbol,
        analysis_type: indType,
        interval,
      })
      setIndResult(res)
    } catch { setError('Error al calcular indicador.') }
    finally { setLoading(false) }
  }

  async function loadPrediction() {
    setLoading(true); setError(null)
    try {
      const res = await analysisService.predict(symbol, interval, horizon)
      if (res.error) { setError(res.error); setPrediction(null) }
      else setPrediction(res)
    } catch { setError('Error al obtener predicción.') }
    finally { setLoading(false) }
  }

  async function loadPatterns() {
    setLoading(true); setError(null)
    try {
      const res = await analysisService.detectPatterns(symbol, interval)
      if (res.error) { setError(res.error); setPatterns(null) }
      else setPatterns(res)
    } catch { setError('Error al detectar patrones.') }
    finally { setLoading(false) }
  }

  async function loadStrategies() {
    try {
      const res = await analysisService.getStrategies()
      setStrategies(res)
      if (res.length > 0 && !selStrategy) setSelStrategy(res[0].key)
    } catch { /* ignore */ }
  }

  async function loadBacktest() {
    if (!selStrategy) { await loadStrategies(); return }
    setLoading(true); setError(null)
    try {
      const sl = Number.parseFloat(stopLossPct)
      const tp = Number.parseFloat(takeProfitPct)
      const res = await analysisService.backtest(symbol, selStrategy, interval, 1000, 10000, {
        commission_bps: commissionBps,
        slippage_bps: slippageBps,
        stop_loss_pct: Number.isFinite(sl) && sl > 0 ? sl / 100 : null,
        take_profit_pct: Number.isFinite(tp) && tp > 0 ? tp / 100 : null,
      })
      if (res.error) { setError(res.error); setBtResult(null) }
      else setBtResult(res)
    } catch { setError('Error al ejecutar backtest.') }
    finally { setLoading(false) }
  }

  function handleRun() {
    switch (tab) {
      case 'signals':   return loadSignals()
      case 'indicator': return loadIndicator()
      case 'predict':   return loadPrediction()
      case 'patterns':  return loadPatterns()
      case 'backtest':  return loadBacktest()
    }
  }

  // ══════════════════════════════════════════════════════════════
  // JSX
  // ══════════════════════════════════════════════════════════════

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700">
      {/* ── Cabecera: diferencia este panel (interactivo, multi-marco)
             de la ficha de confluencia de arriba (resumen diario fijo) ── */}
      <div className="px-4 pt-4 pb-1">
        <h2 className="text-lg font-semibold text-white">Análisis técnico interactivo</h2>
        <p className="text-xs text-slate-500">
          Indicadores, predicción ML, patrones y backtesting en el marco temporal que elijas.
        </p>
      </div>

      {/* ── Pestañas ─────────────────────────────────────────── */}
      <div className="flex items-center gap-1 px-4 pt-3 pb-2 border-b border-slate-700 overflow-x-auto">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setError(null) }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap ${
              tab === t.key
                ? 'bg-blue-600 text-white'
                : 'text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            {TAB_ICONS[t.key]}
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Controles ────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-slate-700/50">
        {/* Intervalo */}
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-slate-500 uppercase">Intervalo</span>
          <div className="flex gap-0.5 bg-slate-900 rounded-md p-0.5">
            {INTERVALS.map((o) => (
              <button
                key={o.value}
                onClick={() => setInterval(o.value)}
                className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                  interval === o.value ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                {o.label}
              </button>
            ))}
          </div>
        </div>

        {/* Controles específicos por tab */}
        {tab === 'indicator' && (
          <div className="flex items-center gap-1">
            <span className="text-[10px] text-slate-500 uppercase">Indicador</span>
            <div className="flex gap-0.5 bg-slate-900 rounded-md p-0.5">
              {ANALYSIS_TYPES.map((type) => (
                <button
                  key={type}
                  onClick={() => setIndType(type)}
                  className={`px-2 py-0.5 rounded text-[11px] font-medium transition-colors ${
                    indType === type ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>
        )}

        {tab === 'predict' && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500 uppercase">Horizonte</span>
            <select
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-xs text-slate-200"
            >
              {[3, 5, 10, 15, 20].map((h) => (
                <option key={h} value={h}>{h} velas</option>
              ))}
            </select>
          </div>
        )}

        {tab === 'backtest' && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-500 uppercase">Estrategia</span>
            <select
              value={selStrategy}
              onFocus={() => { if (strategies.length === 0) loadStrategies() }}
              onChange={(e) => setSelStrategy(e.target.value)}
              className="bg-slate-900 border border-slate-700 rounded px-2 py-0.5 text-xs text-slate-200 min-w-[160px]"
            >
              {strategies.length === 0 && <option value="">Cargando...</option>}
              {strategies.map((s) => (
                <option key={s.key} value={s.key}>{s.name}</option>
              ))}
            </select>
            <button
              onClick={() => setShowBtAdv((v) => !v)}
              className={`text-[10px] px-2 py-1 rounded border transition-colors ${showBtAdv ? 'border-blue-500/50 text-blue-300' : 'border-slate-700 text-slate-400 hover:text-slate-200'}`}
              title="Costes de transacción y gestión de riesgo"
            >
              ⚙ Realismo
            </button>
          </div>
        )}

        <div className="flex-1" />

        {/* Ejecutar */}
        <button
          onClick={handleRun}
          disabled={loading}
          className="bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:cursor-not-allowed text-white text-xs font-medium px-4 py-1.5 rounded-lg transition-colors"
        >
          {loading ? 'Analizando...' : 'Ejecutar análisis'}
        </button>
      </div>

      {/* ── Realismo del backtest: costes + gestión de riesgo ── */}
      {tab === 'backtest' && showBtAdv && (
        <div className="px-4 py-3 border-b border-slate-700/60 bg-slate-900/30 flex flex-wrap gap-4">
          <NumField label="Comisión (bps)" value={commissionBps} onChange={setCommissionBps} title="Por operación, cada lado. 10 bps = 0,1%" />
          <NumField label="Slippage (bps)" value={slippageBps} onChange={setSlippageBps} title="Deslizamiento de precio por lado" />
          <TextField label="Stop-loss %" value={stopLossPct} onChange={setStopLossPct} placeholder="—" />
          <TextField label="Take-profit %" value={takeProfitPct} onChange={setTakeProfitPct} placeholder="—" />
        </div>
      )}

      {/* ── Contenido ────────────────────────────────────────── */}
      <div className="p-4 min-h-[200px]">
        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-sm mb-4">
            {error}
          </div>
        )}

        {loading && (
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <div className="w-8 h-8 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
            <p className="text-slate-400 text-sm">Procesando análisis...</p>
          </div>
        )}

        {!loading && tab === 'signals' && <SignalsTab data={signals} />}
        {!loading && tab === 'indicator' && <IndicatorTab data={indResult} indType={indType} />}
        {!loading && tab === 'predict' && <PredictTab data={prediction} />}
        {!loading && tab === 'patterns' && <PatternsTab data={patterns} />}
        {!loading && tab === 'backtest' && <BacktestTab data={btResult} strategies={strategies} selected={selStrategy} />}
      </div>
    </div>
  )
}


// ══════════════════════════════════════════════════════════════════
// Sub-componentes de cada pestaña
// ══════════════════════════════════════════════════════════════════

function SignalsTab({ data }: { data: SignalsResult | null }) {
  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        }
        title="Panel de señales multi-indicador"
        description="Analiza simultáneamente RSI, MACD, Bollinger, ADX y más. Cada indicador emite una señal (Compra / Neutral / Venta) y el sistema calcula un veredicto global por consenso ponderado."
      />
    )
  }

  const { indicators, summary } = data
  const maxScore = summary.total * 2
  const buyPct  = summary.total > 0 ? (summary.buy_count  / summary.total) * 100 : 0
  const neutPct = summary.total > 0 ? (summary.neutral_count / summary.total) * 100 : 0
  const sellPct = summary.total > 0 ? (summary.sell_count / summary.total) * 100 : 0

  return (
    <div className="space-y-4">
      {/* Veredicto con medidor visual */}
      <div className={`rounded-xl border p-4 ${signalBg(summary.verdict)}`}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Veredicto Global</p>
            <p className={`text-2xl font-bold ${signalColor(summary.verdict)}`}>
              {signalLabel(summary.verdict)}
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Score {summary.score > 0 ? '+' : ''}{summary.score} de {maxScore} máximo
            </p>
          </div>
          {/* Contadores en badges */}
          <div className="flex gap-2 flex-wrap">
            <span className="bg-green-600/30 text-green-300 text-[11px] font-medium px-2 py-1 rounded-lg">
              ▲ {summary.buy_count} compra
            </span>
            <span className="bg-yellow-600/30 text-yellow-300 text-[11px] font-medium px-2 py-1 rounded-lg">
              — {summary.neutral_count} neutral
            </span>
            <span className="bg-red-600/30 text-red-300 text-[11px] font-medium px-2 py-1 rounded-lg">
              ▼ {summary.sell_count} venta
            </span>
          </div>
        </div>

        {/* Barra de sentimiento */}
        <div className="mt-3 space-y-1">
          <div className="flex h-3 rounded-full overflow-hidden gap-0.5 bg-slate-700">
            {buyPct > 0 && (
              <div className="bg-green-500 h-full transition-all" style={{ width: `${buyPct}%` }} title={`Compra: ${summary.buy_count}`} />
            )}
            {neutPct > 0 && (
              <div className="bg-yellow-500 h-full transition-all" style={{ width: `${neutPct}%` }} title={`Neutral: ${summary.neutral_count}`} />
            )}
            {sellPct > 0 && (
              <div className="bg-red-500 h-full transition-all" style={{ width: `${sellPct}%` }} title={`Venta: ${summary.sell_count}`} />
            )}
          </div>
          <p className="text-[10px] text-slate-500 italic">
            Score ponderado: señales fuertes ×2, señales normales ×1. Rango: −{maxScore} (bajista extremo) a +{maxScore} (alcista extremo).
          </p>
        </div>
      </div>

      {/* Radar de consenso */}
      <IndicatorsRadar indicators={indicators} />

      {/* Tabla de indicadores */}
      <div>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left text-slate-500 uppercase py-2 px-2">Indicador</th>
              <th className="text-right text-slate-500 uppercase py-2 px-2">Valor</th>
              <th className="text-center text-slate-500 uppercase py-2 px-2">Señal</th>
            </tr>
          </thead>
          <tbody>
            {indicators.map((ind, i) => {
              const desc = indicatorDescription(ind.name)
              return (
                <tr key={i} className="border-b border-slate-700/40 hover:bg-slate-700/30">
                  <td className="py-2 px-2 text-slate-200">
                    <span className="inline-flex items-center gap-1.5">
                      {ind.name}
                      {desc && <InfoTooltip text={desc} />}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-slate-300 tabular-nums">
                    {typeof ind.value === 'number' ? ind.value.toFixed(4) : ind.value}
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span className="inline-flex items-center justify-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full shrink-0 ${signalDot(ind.signal)}`} />
                      <span className={`${signalColor(ind.signal)} font-medium`}>
                        {signalLabel(ind.signal)}
                      </span>
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Gauge RSI ─────────────────────────────────────────────────────
function RsiGauge({ value }: { value: number }) {
  const pct = Math.min(Math.max(value, 0), 100)
  const color = pct >= 70 ? 'text-red-400' : pct <= 30 ? 'text-green-400' : 'text-yellow-400'
  const label = pct >= 70 ? 'Sobrecompra ≥ 70' : pct <= 30 ? 'Sobreventa ≤ 30' : 'Zona neutral'
  return (
    <div className="space-y-2">
      <div className="relative h-5 rounded-full overflow-hidden flex">
        <div className="w-[30%] bg-green-900/50 border-r border-slate-700" />
        <div className="w-[40%] bg-slate-700/30 border-r border-slate-700" />
        <div className="w-[30%] bg-red-900/50" />
        <div
          className="absolute top-1 bottom-1 w-2 bg-white rounded-full shadow transition-all"
          style={{ left: `calc(${pct}% - 4px)` }}
        />
      </div>
      <div className="flex justify-between text-[9px] text-slate-500">
        <span className="text-green-500">0 — Sobreventa</span>
        <span>30 &nbsp;&nbsp;&nbsp; 70</span>
        <span className="text-red-500">Sobrecompra — 100</span>
      </div>
      <div className="flex items-baseline gap-2 mt-1">
        <span className={`text-3xl font-bold font-mono ${color}`}>{pct.toFixed(2)}</span>
        <span className="text-xs text-slate-400">{label}</span>
      </div>
    </div>
  )
}

function IndicatorTab({ data, indType }: { data: AnalysisResult | null; indType: AnalysisType }) {
  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
          </svg>
        }
        title="Cálculo individual de indicador"
        description="Selecciona RSI, MACD, SMA, EMA o Bollinger y obtén el valor actual con interpretación detallada sobre datos reales de mercado."
      />
    )
  }

  const r = data.result as Record<string, unknown> | null
  if (!r || data.status === 'failed') {
    return <div className="text-red-400 text-sm">{(r as Record<string, string>)?.error ?? 'Error en el análisis.'}</div>
  }

  const signal = (r.signal as string) ?? 'NEUTRAL'
  const interp = (r.interpretation as string) ?? ''
  const numValue = typeof r.value === 'number' ? r.value : null

  return (
    <div className="space-y-4">
      {/* Señal principal */}
      <div className={`rounded-xl border p-4 ${signalBg(signal)}`}>
        <div className="flex items-center justify-between mb-3">
          <p className="text-xs text-slate-400 uppercase font-medium">{r.indicator as string}</p>
          <span className="inline-flex items-center gap-1.5">
            <span className={`w-2.5 h-2.5 rounded-full ${signalDot(signal)}`} />
            <span className={`text-lg font-bold ${signalColor(signal)}`}>{signalLabel(signal)}</span>
          </span>
        </div>

        {/* RSI: gauge visual */}
        {indType === 'RSI' && numValue !== null ? (
          <RsiGauge value={numValue} />
        ) : (
          <p className={`text-2xl font-bold font-mono ${signalColor(signal)}`}>
            {numValue !== null ? numValue.toFixed(4) : String(r.value ?? '—')}
          </p>
        )}

        {interp && (
          <p className="text-xs text-slate-300 mt-3 pt-3 border-t border-slate-700/50">{interp}</p>
        )}
      </div>

      {/* Datos extra */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Object.entries(r).map(([key, val]) => {
          if (['indicator', 'signal', 'interpretation', 'series', 'params'].includes(key)) return null
          if (key.startsWith('series_')) return null
          if (val === null || val === undefined) return null
          if (key === 'value' && indType === 'RSI') return null  // ya mostrado en gauge
          return (
            <div key={key} className="bg-slate-900/50 rounded-lg p-3">
              <p className="text-[10px] text-slate-500 uppercase">{key.replace(/_/g, ' ')}</p>
              <p className="text-sm font-mono text-slate-200">
                {typeof val === 'number' ? val.toFixed(4) : String(val)}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}


// ── Ring de confianza (SVG) ───────────────────────────────────────
function ConfidenceRing({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const r = 28, circ = 2 * Math.PI * r
  const offset = circ - (pct / 100) * circ
  const color = pct >= 70 ? '#22c55e' : pct >= 50 ? '#eab308' : '#ef4444'
  return (
    <div className="relative inline-flex items-center justify-center shrink-0">
      <svg width="72" height="72" className="-rotate-90">
        <circle cx="36" cy="36" r={r} fill="none" stroke="#334155" strokeWidth="6" />
        <circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth="6"
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <span className="absolute text-sm font-bold font-mono text-white">{pct}%</span>
    </div>
  )
}

const VERDICT_STYLE: Record<string, { chip: string; label: string }> = {
  EDGE: { chip: 'bg-green-500/15 text-green-300 border-green-500/30', label: 'Ventaja detectada' },
  WEAK: { chip: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30', label: 'Señal débil' },
  NO_EDGE: { chip: 'bg-red-500/15 text-red-300 border-red-500/30', label: 'Sin ventaja fiable' },
}

function PredictionVerdict({ data }: { data: PredictionResult }) {
  const v = VERDICT_STYLE[data.verdict ?? 'NO_EDGE']
  return (
    <div className={`rounded-lg border p-3 ${v.chip}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-bold uppercase tracking-wide">{v.label}</span>
        {data.n_oos !== undefined && (
          <span className="text-[11px] opacity-80">· {data.n_oos} muestras OOS en {data.n_splits} tramos</span>
        )}
      </div>
      {data.verdict_text && <p className="text-[11px] mt-1 text-slate-300">{data.verdict_text}</p>}
    </div>
  )
}

function PredictTab({ data }: { data: PredictionResult | null }) {
  const [showHow, setShowHow] = useState(false)

  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        }
        title="Predicción ML de dirección de precio"
        description="Modelo Random Forest entrenado con indicadores técnicos como features. Predice si el precio subirá o bajará en las próximas N velas. Validado con cross-validation de 5 folds."
      />
    )
  }

  if (data.prediction === 'INSUFFICIENT_DATA') {
    return <div className="text-yellow-400 text-sm">{data.message}</div>
  }

  const isBullish = data.prediction === 'ALCISTA'

  return (
    <div className="space-y-4">
      {/* Disclaimer prominente */}
      <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg px-3 py-2 flex items-start gap-2">
        <svg className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <p className="text-[11px] text-amber-300/80">
          {data.disclaimer ?? 'Esta predicción es orientativa. El modelo ML no garantiza resultados futuros. No constituye asesoramiento financiero.'}
        </p>
      </div>

      {/* Predicción principal con ring */}
      <div className={`rounded-xl border p-5 ${isBullish ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30'}`}>
        <div className="flex items-center gap-5">
          <ConfidenceRing value={data.confidence} />
          <div className="flex-1">
            <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">
              Predicción — {data.horizon} velas adelante
            </p>
            <p className={`text-3xl font-bold ${isBullish ? 'text-green-400' : 'text-red-400'}`}>
              {isBullish ? '▲ ALCISTA' : '▼ BAJISTA'}
            </p>
            <div className="flex flex-wrap gap-4 mt-2">
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Confianza del modelo</p>
                <p className="text-sm font-bold font-mono text-white">{(data.confidence * 100).toFixed(1)}%</p>
              </div>
              {data.oos_accuracy !== undefined && (
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Precisión OOS (walk-forward)</p>
                  <p className="text-sm font-bold font-mono text-white">
                    {(data.oos_accuracy * 100).toFixed(1)}%
                    {data.cv_std !== undefined && (
                      <span className="text-slate-500 font-normal ml-1">± {(data.cv_std * 100).toFixed(1)}%</span>
                    )}
                  </p>
                </div>
              )}
              {data.model && (
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Modelo</p>
                  <p className="text-sm font-mono text-slate-300">{data.model}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Veredicto honesto: ¿hay edge fuera de muestra? */}
      {data.verdict && <PredictionVerdict data={data} />}

      {/* Métricas fuera de muestra (lo que realmente importa) */}
      {data.oos_accuracy !== undefined && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard label="Edge sobre el azar" value={`${(data.edge ?? 0) >= 0 ? '+' : ''}${((data.edge ?? 0) * 100).toFixed(1)}%`}
            color={(data.edge ?? 0) >= 0.04 ? 'text-green-400' : (data.edge ?? 0) >= 0.01 ? 'text-yellow-400' : 'text-red-400'} />
          <MetricCard label="Línea base (mayoría)" value={`${((data.baseline_accuracy ?? 0) * 100).toFixed(1)}%`} color="text-slate-300" />
          <MetricCard label="AUC" value={data.auc != null ? data.auc.toFixed(3) : '—'}
            color={(data.auc ?? 0) >= 0.55 ? 'text-green-400' : 'text-slate-300'} />
          <MetricCard label="F1 (subida)" value={data.f1_up != null ? data.f1_up.toFixed(2) : '—'} color="text-slate-300" />
        </div>
      )}

      {/* ¿Cómo funciona? — colapsable */}
      <div className="border border-slate-700 rounded-lg overflow-hidden">
        <button
          onClick={() => setShowHow(!showHow)}
          className="w-full flex items-center justify-between px-4 py-2.5 text-xs text-slate-300 hover:bg-slate-700/30 transition-colors"
        >
          <span className="font-medium">¿Cómo funciona este modelo?</span>
          <svg className={`w-4 h-4 text-slate-500 transition-transform ${showHow ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {showHow && (
          <div className="px-4 py-3 bg-slate-900/40 border-t border-slate-700 space-y-2 text-[11px] text-slate-400 leading-relaxed">
            <p><span className="text-slate-300 font-medium">Algoritmo:</span> Random Forest — ensemble de árboles de decisión. Combina múltiples modelos débiles para reducir overfitting y mejorar la generalización.</p>
            <p><span className="text-slate-300 font-medium">Features:</span> Indicadores técnicos calculados sobre las últimas N velas: RSI, MACD, Bollinger, ATR, ADX, EMA, volumen relativo y variaciones de precio.</p>
            <p><span className="text-slate-300 font-medium">Target:</span> Variable binaria — ¿sube o baja el precio en las próximas {data.horizon} velas?</p>
            <p><span className="text-slate-300 font-medium">Validación walk-forward:</span> se entrena en el pasado y se valida en el futuro (TimeSeriesSplit), nunca al revés — así la precisión OOS es honesta, sin fuga del futuro. El <span className="text-slate-300">edge</span> es la ventaja sobre predecir siempre la clase mayoritaria: si es ~0, no hay señal real aunque la precisión parezca alta.</p>
          </div>
        )}
      </div>

      {/* Feature importances */}
      {data.features_importance && data.features_importance.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 uppercase mb-2">Variables más influyentes</p>
          <div className="space-y-1.5">
            {data.features_importance.map((fi) => (
              <div key={fi.feature} className="flex items-center gap-2">
                <span className="text-[11px] text-slate-300 w-28 truncate" title={fi.feature}>{fi.feature}</span>
                <div className="flex-1 bg-slate-700 rounded-full h-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full transition-all"
                    style={{ width: `${Math.min(fi.importance * 100 / (data.features_importance![0]?.importance || 1), 100)}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-slate-400 w-12 text-right">
                  {(fi.importance * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}


function PatternsTab({ data }: { data: PatternsResult | null }) {
  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        }
        title="Detección de patrones de velas"
        description="Identifica formaciones chartistas clásicas (Doji, Hammer, Engulfing, etc.) en las últimas velas. Cada patrón incluye señal alcista/bajista y fiabilidad histórica."
      />
    )
  }

  if (data.patterns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3 text-center">
        <svg className="w-8 h-8 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p className="text-slate-400 text-sm">No se detectaron patrones en las últimas velas.</p>
        <p className="text-[11px] text-slate-500 max-w-xs">
          Los patrones requieren condiciones específicas de precio y volumen. Prueba con otro intervalo temporal.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-400">
        {data.patterns.length} patrón(es) detectado(s) — {data.total_candles} velas analizadas
      </p>
      {data.patterns.map((p, i) => (
        <div key={i} className={`rounded-lg border p-3 ${signalBg(p.signal)}`}>
          <div className="flex items-start justify-between">
            <div className="flex-1 mr-3">
              <p className="text-sm font-semibold text-white">{p.name}</p>
              <p className="text-xs text-slate-300 mt-0.5">{p.description}</p>
            </div>
            <div className="flex flex-col items-end gap-1.5 shrink-0">
              <span className="inline-flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full shrink-0 ${signalDot(p.signal)}`} />
                <span className={`text-xs font-bold ${signalColor(p.signal)}`}>{signalLabel(p.signal)}</span>
              </span>
              <span className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full ${reliabilityBadge(p.reliability)}`}>
                <span>{reliabilityStars(p.reliability)}</span>
                <span>{p.reliability}</span>
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}


function BacktestTab({ data, strategies, selected }: { data: BacktestResult | null; strategies: StrategyInfo[]; selected: string }) {
  if (!data) {
    const desc = strategies.find((s) => s.key === selected)?.description
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
        title="Simulación de estrategia sobre histórico"
        description={desc ?? 'Selecciona una estrategia de trading y simula su rendimiento sobre datos históricos reales. Compara el resultado con la estrategia pasiva Buy & Hold.'}
      />
    )
  }

  const isPositive = data.total_return_pct >= 0
  const beatsBuyHold = data.total_return_pct > data.buy_hold_return_pct
  const alpha = data.total_return_pct - data.buy_hold_return_pct
  const maxAbs = Math.max(Math.abs(data.total_return_pct), Math.abs(data.buy_hold_return_pct), 1)

  return (
    <div className="space-y-4">
      {/* Descripción de estrategia */}
      <div className="bg-slate-900/50 rounded-lg p-3">
        <p className="text-xs text-slate-400 uppercase mb-1">{data.strategy}</p>
        <p className="text-xs text-slate-300">{data.description}</p>
      </div>

      {/* Periodo analizado */}
      {(data.start_date || data.candles_count) && (
        <div className="bg-blue-950/40 border border-blue-700/30 rounded-lg px-3 py-2 flex flex-wrap gap-x-5 gap-y-1">
          {data.start_date && data.end_date && (
            <span className="text-[11px]">
              <span className="text-slate-500 uppercase text-[10px] mr-1">Periodo:</span>
              <span className="text-slate-300 font-mono">{data.start_date}</span>
              <span className="mx-1 text-slate-600">→</span>
              <span className="text-slate-300 font-mono">{data.end_date}</span>
            </span>
          )}
          {data.candles_count && (
            <span className="text-[11px]">
              <span className="text-slate-500 uppercase text-[10px] mr-1">Velas:</span>
              <span className="text-slate-300">{data.candles_count.toLocaleString()}</span>
            </span>
          )}
          {data.interval && (
            <span className="text-[11px]">
              <span className="text-slate-500 uppercase text-[10px] mr-1">Intervalo:</span>
              <span className="text-slate-300">{data.interval}</span>
            </span>
          )}
        </div>
      )}

      {/* Comparativa visual retorno estrategia vs Buy & Hold */}
      <div className="space-y-2 bg-slate-900/30 rounded-lg p-3">
        <p className="text-[10px] text-slate-500 uppercase mb-3">Retorno — Estrategia vs Buy & Hold</p>
        {[
          { label: 'Estrategia', value: data.total_return_pct, color: isPositive ? 'bg-blue-600' : 'bg-red-700' },
          { label: 'Buy & Hold', value: data.buy_hold_return_pct, color: data.buy_hold_return_pct >= 0 ? 'bg-slate-500' : 'bg-red-900' },
        ].map(({ label, value, color }) => (
          <div key={label} className="flex items-center gap-2">
            <span className="text-[10px] text-slate-400 w-20 truncate">{label}</span>
            <div className="flex-1 h-6 bg-slate-700 rounded overflow-hidden">
              <div
                className={`h-full rounded flex items-center justify-end pr-2 transition-all ${color}`}
                style={{ width: `${Math.max((Math.abs(value) / maxAbs) * 100, 4)}%` }}
              >
                <span className="text-[10px] font-bold text-white whitespace-nowrap">
                  {value >= 0 ? '+' : ''}{value.toFixed(2)}%
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Alpha badge */}
      <div className={`flex items-center gap-2 rounded-lg px-3 py-2 ${beatsBuyHold ? 'bg-green-900/30 border border-green-700/30' : 'bg-red-900/20 border border-red-700/20'}`}>
        <svg className={`w-4 h-4 ${beatsBuyHold ? 'text-green-400' : 'text-red-400'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d={beatsBuyHold ? 'M5 10l7-7m0 0l7 7m-7-7v18' : 'M19 14l-7 7m0 0l-7-7m7 7V3'} />
        </svg>
        <p className="text-xs text-slate-300">
          <span className={`font-bold ${beatsBuyHold ? 'text-green-400' : 'text-red-400'}`}>
            {beatsBuyHold ? 'Supera' : 'No supera'} al Buy & Hold
          </span>
          {' '}— Alpha:{' '}
          <span className={`font-mono font-medium ${alpha >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {alpha >= 0 ? '+' : ''}{alpha.toFixed(2)}%
          </span>
          <span className="text-slate-500 ml-1 text-[10px]">(retorno estrategia − retorno pasivo)</span>
        </p>
      </div>

      {/* Métricas */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Retorno total" value={`${isPositive ? '+' : ''}${data.total_return_pct.toFixed(2)}%`} color={isPositive ? 'text-green-400' : 'text-red-400'} />
        <MetricCard label="Buy & Hold" value={`${data.buy_hold_return_pct >= 0 ? '+' : ''}${data.buy_hold_return_pct.toFixed(2)}%`} color={data.buy_hold_return_pct >= 0 ? 'text-green-400' : 'text-red-400'} />
        <MetricCard label="Win Rate" value={`${data.win_rate_pct.toFixed(1)}%`} color="text-white" />
        <MetricCard label="Max Drawdown" value={`-${data.max_drawdown_pct.toFixed(2)}%`} color="text-red-400" />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Total trades" value={String(data.total_trades)} color="text-white" />
        <MetricCard label="Cap. inicial" value={`$${data.initial_capital.toLocaleString()}`} color="text-slate-300" />
        <MetricCard label="Cap. final" value={`$${data.final_capital.toLocaleString()}`} color={isPositive ? 'text-green-400' : 'text-red-400'} />
        <MetricCard label="Avg Win / Avg Loss" value={`${data.avg_win_pct.toFixed(1)}% / ${data.avg_loss_pct.toFixed(1)}%`} color="text-slate-300" />
      </div>

      {/* Realismo de ejecución: coste, rotación y motivos de salida */}
      {(data.total_commission_pct != null || data.turnover != null || data.exit_reasons) && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard label="Coste en comisiones" value={`-${(data.total_commission_pct ?? 0).toFixed(2)}%`} color="text-amber-400" />
          <MetricCard label="Rotación (×capital)" value={`${(data.turnover ?? 0).toFixed(1)}×`} color="text-slate-300" />
          {data.exit_reasons && (
            <div className="col-span-2 bg-slate-900/40 rounded-lg p-3">
              <p className="text-[10px] text-slate-500 uppercase mb-1.5">Motivos de salida</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(data.exit_reasons).map(([reason, count]) => (
                  <span key={reason} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
                    {EXIT_REASON_LABEL[reason] ?? reason}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Últimas trades */}
      {data.trades.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 uppercase mb-2">Últimas operaciones</p>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-1.5 px-2 text-slate-500">#</th>
                  <th className="text-right py-1.5 px-2 text-slate-500">Entrada</th>
                  <th className="text-right py-1.5 px-2 text-slate-500">Salida</th>
                  <th className="text-right py-1.5 px-2 text-slate-500">P&L</th>
                  <th className="text-center py-1.5 px-2 text-slate-500">Resultado</th>
                </tr>
              </thead>
              <tbody>
                {data.trades.map((t, i) => (
                  <tr key={i} className="border-b border-slate-700/30">
                    <td className="py-1.5 px-2 text-slate-400">{i + 1}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-slate-300">${t.entry_price}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-slate-300">${t.exit_price}</td>
                    <td className={`py-1.5 px-2 text-right font-mono font-medium ${t.pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct}%
                    </td>
                    <td className="py-1.5 px-2 text-center">
                      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] ${t.result === 'WIN' ? 'bg-green-600/30 text-green-300' : 'bg-red-600/30 text-red-300'}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${t.result === 'WIN' ? 'bg-green-400' : 'bg-red-400'}`} />
                        {t.result}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}


function MetricCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-slate-900/50 rounded-lg p-3">
      <p className="text-[10px] text-slate-500 uppercase">{label}</p>
      <p className={`text-sm font-bold font-mono ${color}`}>{value}</p>
    </div>
  )
}

const EXIT_REASON_LABEL: Record<string, string> = {
  signal: 'Señal', stop_loss: 'Stop-loss', take_profit: 'Take-profit',
  trailing_stop: 'Trailing', end_of_data: 'Fin de datos',
}

function NumField({ label, value, onChange, title }: { label: string; value: number; onChange: (n: number) => void; title?: string }) {
  return (
    <label className="text-[10px] text-slate-400" title={title}>
      <span className="block mb-1 uppercase">{label}</span>
      <input
        type="number" min={0} value={value}
        onChange={(e) => onChange(Math.max(0, Number.parseFloat(e.target.value) || 0))}
        className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 w-24 focus:ring-1 focus:ring-blue-500 outline-none"
      />
    </label>
  )
}

function TextField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (s: string) => void; placeholder?: string }) {
  return (
    <label className="text-[10px] text-slate-400">
      <span className="block mb-1 uppercase">{label}</span>
      <input
        type="number" min={0} step="0.5" value={value} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 w-24 focus:ring-1 focus:ring-blue-500 outline-none"
      />
    </label>
  )
}


function EmptyState({ icon, title, description }: { icon: ReactNode; title: string; description: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center gap-3">
      <div className="text-slate-600">{icon}</div>
      <div>
        <p className="text-slate-300 text-sm font-medium">{title}</p>
        <p className="text-slate-500 text-xs max-w-md mt-1 leading-relaxed">{description}</p>
      </div>
      <p className="text-[10px] text-slate-600 mt-1">Pulsa "Ejecutar análisis" para comenzar</p>
    </div>
  )
}
