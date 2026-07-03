/**
 * components/analysis/AnalysisPanel.tsx — Panel de análisis técnico interactivo.
 *
 * Orquestador: gestiona estado, marco temporal y carga de datos, y delega el
 * render de cada pestaña a su componente en ./tabs/:
 *   1. Señales        — medidor de sentimiento + semáforos multi-indicador
 *   2. Indicadores    — cálculo detallado con gauge visual contextual
 *   3. Predicción ML  — predicción de dirección + explicación del modelo
 *   4. Patrones       — detección de patrones chartistas con fiabilidad
 *   5. Backtesting    — simulación de estrategia con comparativa vs buy&hold
 */

import { useState } from 'react'
import { useTranslation } from 'react-i18next'
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
  type MtfConfluence,
  type PriceStructure,
} from '@/services/analysisService'
import { NumField, TextField } from '@/components/analysis/analysisShared'
import SignalsTab from '@/components/analysis/tabs/SignalsTab'
import IndicatorTab from '@/components/analysis/tabs/IndicatorTab'
import PredictTab from '@/components/analysis/tabs/PredictTab'
import PatternsTab from '@/components/analysis/tabs/PatternsTab'
import BacktestTab from '@/components/analysis/tabs/BacktestTab'
import MtfTab from '@/components/analysis/tabs/MtfTab'
import LevelsTab from '@/components/analysis/tabs/LevelsTab'

// ── Configuración de pestañas / controles ────────────────────────

type Tab = 'signals' | 'mtf' | 'levels' | 'indicator' | 'predict' | 'patterns' | 'backtest'

const TABS: { key: Tab; labelKey: string }[] = [
  { key: 'signals',   labelKey: 'analysis.tabSignals' },
  { key: 'mtf',       labelKey: 'analysis.tabMtf' },
  { key: 'levels',    labelKey: 'analysis.tabLevels' },
  { key: 'indicator', labelKey: 'analysis.tabIndicators' },
  { key: 'predict',   labelKey: 'analysis.tabPredict' },
  { key: 'patterns',  labelKey: 'analysis.tabPatterns' },
  { key: 'backtest',  labelKey: 'analysis.tabBacktest' },
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

// ── Iconos SVG de pestañas ───────────────────────────────────────

function IcoSignals() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
    </svg>
  )
}
function IcoMtf() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
    </svg>
  )
}
function IcoLevels() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
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
  mtf:       <IcoMtf />,
  levels:    <IcoLevels />,
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
  const { t } = useTranslation()
  const [tab, setTab]               = useState<Tab>('signals')
  const [interval, setInterval]     = useState<IntervalType>('1h')
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)

  // ── Signals state ──
  const [signals, setSignals]       = useState<SignalsResult | null>(null)

  // ── MTF state ──
  const [mtf, setMtf]               = useState<MtfConfluence | null>(null)

  // ── Levels state ──
  const [structure, setStructure]   = useState<PriceStructure | null>(null)

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

  async function loadMtf() {
    setLoading(true); setError(null)
    try {
      const res = await analysisService.getMtfConfluence(symbol)
      if (res.error) { setError(res.error); setMtf(null) }
      else setMtf(res)
    } catch { setError('Error al calcular la confluencia multi-marco.') }
    finally { setLoading(false) }
  }

  async function loadLevels() {
    setLoading(true); setError(null)
    try {
      const res = await analysisService.getPriceStructure(symbol, interval)
      if (res.error) { setError(res.error); setStructure(null) }
      else setStructure(res)
    } catch { setError('Error al calcular los niveles.') }
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
      case 'mtf':       return loadMtf()
      case 'levels':    return loadLevels()
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
        <h2 className="text-lg font-semibold text-white">{t('analysis.panelTitle')}</h2>
        <p className="text-xs text-slate-500">
          {t('analysis.panelSubtitle')}
        </p>
      </div>

      {/* ── Pestañas ─────────────────────────────────────────── */}
      <div className="flex items-center gap-1 px-4 pt-3 pb-2 border-b border-slate-700 overflow-x-auto">
        {TABS.map((tabDef) => (
          <button
            key={tabDef.key}
            onClick={() => { setTab(tabDef.key); setError(null) }}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap ${
              tab === tabDef.key
                ? 'bg-blue-600 text-white'
                : 'text-slate-400 hover:text-white hover:bg-slate-700'
            }`}
          >
            {TAB_ICONS[tabDef.key]}
            {t(tabDef.labelKey)}
          </button>
        ))}
      </div>

      {/* ── Controles ────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 px-4 py-3 border-b border-slate-700/50">
        {/* Intervalo */}
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-slate-500 uppercase">{t('analysis.interval')}</span>
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
        {!loading && tab === 'mtf' && <MtfTab data={mtf} />}
        {!loading && tab === 'levels' && <LevelsTab data={structure} />}
        {!loading && tab === 'indicator' && <IndicatorTab data={indResult} indType={indType} />}
        {!loading && tab === 'predict' && <PredictTab data={prediction} />}
        {!loading && tab === 'patterns' && <PatternsTab data={patterns} />}
        {!loading && tab === 'backtest' && <BacktestTab data={btResult} strategies={strategies} selected={selStrategy} />}
      </div>
    </div>
  )
}
