/**
 * components/AnalysisPanel.tsx — Panel de análisis técnico avanzado reutilizable.
 *
 * 5 pestañas:
 *   1. Señales (Signal Dashboard)  — semáforos multi-indicador
 *   2. Indicadores individuales    — cálculo detallado de un indicador
 *   3. Predicción ML               — predicción de dirección de precio
 *   4. Patrones de velas           — detección de patrones chartistas
 *   5. Backtesting                 — simulación de estrategia sobre histórico
 */

import { useState } from 'react'
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

function reliabilityBadge(r: string) {
  const colors: Record<string, string> = {
    'ALTA':  'bg-green-600/30 text-green-300',
    'MEDIA': 'bg-yellow-600/30 text-yellow-300',
    'BAJA':  'bg-slate-600/30 text-slate-300',
  }
  return colors[r] ?? 'bg-slate-600/30 text-slate-300'
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
      const res = await analysisService.backtest(symbol, selStrategy, interval)
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

      {/* ── Contenido ────────────────────────────────────────── */}
      <div className="p-4 min-h-[200px]">
        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-sm mb-4">
            {error}
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center py-12 text-slate-400 text-sm animate-pulse">
            Procesando análisis...
          </div>
        )}

        {!loading && tab === 'signals' && <SignalsTab data={signals} />}
        {!loading && tab === 'indicator' && <IndicatorTab data={indResult} />}
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
  if (!data) return <EmptyState text="Pulsa 'Ejecutar análisis' para ver el panel de señales multi-indicador." />

  const { indicators, summary } = data

  return (
    <div className="space-y-4">
      {/* Veredicto */}
      <div className={`rounded-xl border p-4 text-center ${signalBg(summary.verdict)}`}>
        <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Veredicto Global</p>
        <p className={`text-2xl font-bold ${signalColor(summary.verdict)}`}>
          {signalLabel(summary.verdict)}
        </p>
        <p className="text-xs text-slate-400 mt-1">
          Score: {summary.score} &middot; {summary.buy_count} compra &middot; {summary.sell_count} venta &middot; {summary.neutral_count} neutral
        </p>
      </div>

      {/* Tabla de indicadores */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left text-slate-500 uppercase py-2 px-2">Indicador</th>
              <th className="text-right text-slate-500 uppercase py-2 px-2">Valor</th>
              <th className="text-center text-slate-500 uppercase py-2 px-2">Señal</th>
            </tr>
          </thead>
          <tbody>
            {indicators.map((ind, i) => (
              <tr key={i} className="border-b border-slate-700/40 hover:bg-slate-700/30">
                <td className="py-2 px-2 text-slate-200">{ind.name}</td>
                <td className="py-2 px-2 text-right font-mono text-slate-300">
                  {typeof ind.value === 'number' ? ind.value.toFixed(4) : ind.value}
                </td>
                <td className="py-2 px-2 text-center">
                  <span className={`${signalColor(ind.signal)} font-medium`}>
                    {signalLabel(ind.signal)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}


function IndicatorTab({ data }: { data: AnalysisResult | null }) {
  if (!data) return <EmptyState text="Selecciona un indicador y pulsa 'Ejecutar análisis'." />

  const r = data.result as Record<string, unknown> | null
  if (!r || data.status === 'failed') {
    return <div className="text-red-400 text-sm">{(r as Record<string, string>)?.error ?? 'Error en el análisis.'}</div>
  }

  const signal = (r.signal as string) ?? 'NEUTRAL'
  const interp = (r.interpretation as string) ?? ''

  return (
    <div className="space-y-4">
      {/* Señal */}
      <div className={`rounded-xl border p-4 ${signalBg(signal)}`}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400 uppercase">{r.indicator as string}</p>
            <p className={`text-xl font-bold font-mono ${signalColor(signal)}`}>
              {typeof r.value === 'number' ? (r.value as number).toFixed(4) : String(r.value ?? '—')}
            </p>
          </div>
          <span className={`text-lg font-bold ${signalColor(signal)}`}>
            {signalLabel(signal)}
          </span>
        </div>
        <p className="text-xs text-slate-300 mt-2">{interp}</p>
      </div>

      {/* Datos extra */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {Object.entries(r).map(([key, val]) => {
          if (['indicator', 'signal', 'interpretation', 'series', 'params'].includes(key)) return null
          if (key.startsWith('series_')) return null
          if (val === null || val === undefined) return null
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


function PredictTab({ data }: { data: PredictionResult | null }) {
  if (!data) return <EmptyState text="Pulsa 'Ejecutar análisis' para obtener una predicción ML." />

  if (data.prediction === 'INSUFFICIENT_DATA') {
    return <div className="text-yellow-400 text-sm">{data.message}</div>
  }

  const isBullish = data.prediction === 'ALCISTA'

  return (
    <div className="space-y-4">
      {/* Predicción principal */}
      <div className={`rounded-xl border p-5 text-center ${isBullish ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30'}`}>
        <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Predicción ({data.horizon} velas)</p>
        <p className={`text-3xl font-bold ${isBullish ? 'text-green-400' : 'text-red-400'}`}>
          {isBullish ? 'ALCISTA' : 'BAJISTA'}
        </p>
        <div className="mt-3 flex items-center justify-center gap-3">
          <div>
            <p className="text-[10px] text-slate-500 uppercase">Confianza</p>
            <p className="text-lg font-bold font-mono text-white">{(data.confidence * 100).toFixed(1)}%</p>
          </div>
          {data.cv_accuracy !== undefined && (
            <div>
              <p className="text-[10px] text-slate-500 uppercase">Precisión CV</p>
              <p className="text-lg font-bold font-mono text-white">{(data.cv_accuracy * 100).toFixed(1)}%</p>
            </div>
          )}
        </div>
      </div>

      {/* Feature importances */}
      {data.features_importance && data.features_importance.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 uppercase mb-2">Importancia de variables</p>
          <div className="space-y-1.5">
            {data.features_importance.map((fi) => (
              <div key={fi.feature} className="flex items-center gap-2">
                <span className="text-[11px] text-slate-300 w-28 truncate">{fi.feature}</span>
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

      {/* Disclaimer */}
      {data.disclaimer && (
        <p className="text-[10px] text-slate-500 italic mt-2">{data.disclaimer}</p>
      )}
    </div>
  )
}


function PatternsTab({ data }: { data: PatternsResult | null }) {
  if (!data) return <EmptyState text="Pulsa 'Ejecutar análisis' para detectar patrones de velas." />

  if (data.patterns.length === 0) {
    return (
      <div className="text-center py-8 text-slate-400 text-sm">
        No se detectaron patrones en las últimas velas.
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-400">
        {data.patterns.length} patrón(es) detectado(s) en las últimas velas ({data.total_candles} analizadas)
      </p>
      {data.patterns.map((p, i) => (
        <div key={i} className={`rounded-lg border p-3 ${signalBg(p.signal)}`}>
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-semibold text-white">{p.name}</p>
              <p className="text-xs text-slate-300 mt-0.5">{p.description}</p>
            </div>
            <div className="flex flex-col items-end gap-1">
              <span className={`text-xs font-bold ${signalColor(p.signal)}`}>
                {signalLabel(p.signal)}
              </span>
              <span className={`text-[10px] px-2 py-0.5 rounded-full ${reliabilityBadge(p.reliability)}`}>
                {p.reliability}
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
      <EmptyState text={desc
        ? `Estrategia seleccionada: ${desc}\n\nPulsa 'Ejecutar análisis' para simular.`
        : "Selecciona una estrategia y pulsa 'Ejecutar análisis' para simular el backtesting."
      } />
    )
  }

  const isPositive = data.total_return_pct >= 0
  const beatsBuyHold = data.total_return_pct > data.buy_hold_return_pct

  return (
    <div className="space-y-4">
      {/* Descripción */}
      <div className="bg-slate-900/50 rounded-lg p-3">
        <p className="text-xs text-slate-400 uppercase">{data.strategy}</p>
        <p className="text-xs text-slate-300 mt-1">{data.description}</p>
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
              <span className="text-slate-500 ml-1">(UTC)</span>
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

      {/* Métricas principales */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard
          label="Retorno total"
          value={`${isPositive ? '+' : ''}${data.total_return_pct.toFixed(2)}%`}
          color={isPositive ? 'text-green-400' : 'text-red-400'}
        />
        <MetricCard
          label="Buy & Hold"
          value={`${data.buy_hold_return_pct >= 0 ? '+' : ''}${data.buy_hold_return_pct.toFixed(2)}%`}
          color={data.buy_hold_return_pct >= 0 ? 'text-green-400' : 'text-red-400'}
        />
        <MetricCard label="Win Rate" value={`${data.win_rate_pct.toFixed(1)}%`} color="text-white" />
        <MetricCard label="Max Drawdown" value={`-${data.max_drawdown_pct.toFixed(2)}%`} color="text-red-400" />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Total trades" value={String(data.total_trades)} color="text-white" />
        <MetricCard label="Cap. inicial" value={`$${data.initial_capital.toLocaleString()}`} color="text-slate-300" />
        <MetricCard label="Cap. final" value={`$${data.final_capital.toLocaleString()}`} color={isPositive ? 'text-green-400' : 'text-red-400'} />
        <MetricCard
          label="vs Buy&Hold"
          value={beatsBuyHold ? 'Supera' : 'No supera'}
          color={beatsBuyHold ? 'text-green-400' : 'text-red-400'}
        />
      </div>

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
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${t.result === 'WIN' ? 'bg-green-600/30 text-green-300' : 'bg-red-600/30 text-red-300'}`}>
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


function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex items-center justify-center py-12 text-center">
      <p className="text-slate-400 text-sm max-w-md whitespace-pre-line">{text}</p>
    </div>
  )
}
