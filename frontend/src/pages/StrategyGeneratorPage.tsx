/**
 * pages/StrategyGeneratorPage.tsx — Generador genético de estrategias (Módulo 2).
 *
 * Lanza el generador (tarea Celery: evolución del GA + gating de robustez),
 * hace polling del job y presenta el ranking de estrategias robustas con sus
 * métricas, la partición temporal anti data-snooping, tres visualizaciones 3D
 * y el historial de estrategias guardadas.
 */

import { lazy, useEffect, useRef, useState } from 'react'
import { analysisService, type CryptoAsset } from '@/services/analysisService'
import {
  strategyGeneratorService,
  isGenerationReport,
  type GenerationReport,
  type GenPreset,
  type Finalist,
  type GatingChecks,
  type LaunchResponse,
  type SavedStrategy,
  type SignalEvent,
} from '@/services/strategyGeneratorService'
import Generator3DPanel from '@/components/generator/Generator3DPanel'
import SpecRobustnessPanel from '@/components/generator/SpecRobustnessPanel'
import PaperTradingPanel from '@/components/generator/PaperTradingPanel'
import BestStrategiesPanel from '@/components/generator/BestStrategiesPanel'
import StrategyPortfolioPanel from '@/components/generator/StrategyPortfolioPanel'
import Viz3DSwitch from '@/components/viz3d/Viz3DSwitch'
import ParetoFrontier2D from '@/components/generator/ParetoFrontier2D'
const ParetoFrontier3D = lazy(() => import('@/components/generator/ParetoFrontier3D'))
import Skeleton from '@/components/ui/Skeleton'

const INTERVALS = ['1d', '4h', '1h', '1w']
const PRESETS: { value: GenPreset; label: string; hint: string }[] = [
  { value: 'fast', label: 'Rápido', hint: 'Población 24 · 8 generaciones' },
  { value: 'balanced', label: 'Equilibrado', hint: 'Población 40 · 15 generaciones' },
  { value: 'thorough', label: 'Exhaustivo', hint: 'Población 60 · 25 generaciones' },
]

const POLL_MS = 3000
const MAX_POLLS = 140 // ~7 min de techo

type Phase = 'idle' | 'running' | 'done' | 'error'

const RUN_MESSAGES = [
  'Sembrando la población inicial…',
  'Evolucionando: selección, cruce y mutación…',
  'Evaluando fitness fuera de muestra (walk-forward)…',
  'Filtrando por robustez: PBO, Monte Carlo, lookahead…',
  'Validando finalistas en el tramo intacto…',
]

export default function StrategyGeneratorPage() {
  const [assets, setAssets] = useState<CryptoAsset[]>([])
  const [symbol, setSymbol] = useState('BTC')
  const [interval, setIntervalTf] = useState('1d')
  const [preset, setPreset] = useState<GenPreset>('balanced')
  const [optimizer, setOptimizer] = useState<'single' | 'nsga'>('single')
  const [loadingAssets, setLoadingAssets] = useState(true)

  const [phase, setPhase] = useState<Phase>('idle')
  const [report, setReport] = useState<GenerationReport | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [elapsed, setElapsed] = useState(0)

  const [history, setHistory] = useState<SavedStrategy[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [signalEvents, setSignalEvents] = useState<SignalEvent[]>([])
  const [paperKey, setPaperKey] = useState(0)
  const [genView, setGenView] = useState<'generate' | 'live'>('generate')

  const pollRef = useRef<number>(0)
  const tickRef = useRef<number>(0)

  useEffect(() => {
    analysisService.getAssets()
      .then((data) => { setAssets(data); if (data.length) setSymbol(data[0].symbol) })
      .catch(() => { /* lista vacía */ })
      .finally(() => setLoadingAssets(false))
    strategyGeneratorService.listSignalEvents(15).then(setSignalEvents).catch(() => { /* sin eventos */ })
  }, [])

  useEffect(() => () => { window.clearInterval(pollRef.current); window.clearInterval(tickRef.current) }, [])

  function stopTimers() {
    window.clearInterval(pollRef.current)
    window.clearInterval(tickRef.current)
  }

  async function loadHistory() {
    try {
      setHistory(await strategyGeneratorService.listSaved({ asset_symbol: symbol, limit: 30 }))
    } catch { /* vacío */ }
  }

  async function handleRun() {
    stopTimers()
    setPhase('running')
    setReport(null)
    setErrorMsg('')
    setElapsed(0)
    tickRef.current = window.setInterval(() => setElapsed((s) => s + 1), 1000)

    try {
      const { job_id }: LaunchResponse = await strategyGeneratorService.launch({
        asset_symbol: symbol, interval, preset, optimizer,
      })
      let attempts = 0
      pollRef.current = window.setInterval(async () => {
        attempts += 1
        try {
          const s = await strategyGeneratorService.getStatus(job_id)
          if (s.status === 'SUCCESS') {
            stopTimers()
            if (isGenerationReport(s.result)) {
              setReport(s.result)
              setPhase('done')
              loadHistory()
            } else {
              setErrorMsg(s.result && 'error' in s.result ? s.result.error : 'No hay datos suficientes para generar.')
              setPhase('error')
            }
          } else if (s.status === 'FAILURE') {
            stopTimers(); setErrorMsg('El generador falló durante la ejecución.'); setPhase('error')
          } else if (attempts >= MAX_POLLS) {
            stopTimers(); setErrorMsg('Tiempo de espera agotado. Inténtalo de nuevo.'); setPhase('error')
          }
        } catch {
          stopTimers(); setErrorMsg('Error consultando el estado del generador.'); setPhase('error')
        }
      }, POLL_MS)
    } catch {
      stopTimers(); setErrorMsg('No se pudo lanzar el generador.'); setPhase('error')
    }
  }

  const selectedAsset = assets.find((a) => a.symbol === symbol)
  const runMsg = RUN_MESSAGES[Math.min(RUN_MESSAGES.length - 1, Math.floor(elapsed / 8))]

  return (
    <section className="space-y-6">
      {/* Cabecera */}
      <header className="flex flex-col lg:flex-row lg:items-end gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-white">Generador de estrategias</h1>
            <span className="text-[10px] font-semibold uppercase tracking-wider bg-gradient-to-r from-blue-500/20 to-purple-500/20 text-blue-300 border border-blue-500/30 rounded-full px-2 py-0.5">
              Algoritmo genético
            </span>
          </div>
          <p className="text-slate-400 text-sm mt-1 max-w-2xl">
            Evoluciona estrategias nuevas combinando indicadores y las filtra por robustez
            (walk-forward, PBO, Monte Carlo). El fitness es fuera de muestra, no el retorno
            in-sample, y un tramo final de datos queda reservado como validación intacta.
          </p>
        </div>
        {selectedAsset && (
          <div className="flex items-center gap-3 bg-slate-800 rounded-lg px-4 py-2 border border-slate-700">
            {selectedAsset.logo_url && <img src={selectedAsset.logo_url} alt={symbol} className="w-6 h-6 rounded-full" />}
            <div>
              <p className="text-[10px] text-slate-500 leading-none">{selectedAsset.name}</p>
              <p className="text-sm font-bold font-mono text-white">
                ${Number.parseFloat(selectedAsset.current_price ?? '0').toLocaleString()}
              </p>
            </div>
          </div>
        )}
      </header>

      {/* Sub-navegación por submódulos: generar vs. seguimiento en vivo */}
      <div className="flex flex-wrap gap-1 border-b border-slate-700">
        {([
          { key: 'generate', label: '⚡ Generador' },
          { key: 'live', label: '📡 Seguimiento en vivo' },
        ] as const).map((tabDef) => (
          <button
            key={tabDef.key}
            onClick={() => setGenView(tabDef.key)}
            className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
              genView === tabDef.key ? 'border-blue-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {tabDef.label}
          </button>
        ))}
      </div>

      {genView === 'generate' && (
      <>
      {/* Panel de lanzamiento */}
      <div className="bg-slate-800 rounded-xl border border-slate-700">
        <div className="flex flex-wrap items-end gap-3 px-4 py-4">
          <label className="text-[11px] text-slate-400">
            <span className="block mb-1 uppercase">Activo</span>
            {loadingAssets ? (
              <Skeleton className="h-9 w-44 rounded-lg" />
            ) : (
              <select
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                disabled={phase === 'running'}
                className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 min-w-[180px] focus:ring-1 focus:ring-blue-500 outline-none"
              >
                {(assets.length ? assets : [{ id: 0, symbol, name: symbol } as CryptoAsset]).map((a) => (
                  <option key={a.id} value={a.symbol}>{a.symbol} — {a.name}</option>
                ))}
              </select>
            )}
          </label>

          <label className="text-[11px] text-slate-400">
            <span className="block mb-1 uppercase">Marco</span>
            <div className="flex gap-0.5 bg-slate-900 rounded-md p-0.5">
              {INTERVALS.map((iv) => (
                <button
                  key={iv}
                  onClick={() => setIntervalTf(iv)}
                  disabled={phase === 'running'}
                  className={`px-2.5 py-1.5 rounded text-xs font-medium transition-colors ${
                    interval === iv ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {iv}
                </button>
              ))}
            </div>
          </label>

          <label className="text-[11px] text-slate-400" title="Tamaño de población y nº de generaciones">
            <span className="block mb-1 uppercase">Profundidad</span>
            <div className="flex gap-0.5 bg-slate-900 rounded-md p-0.5">
              {PRESETS.map((p) => (
                <button
                  key={p.value}
                  onClick={() => setPreset(p.value)}
                  disabled={phase === 'running'}
                  title={p.hint}
                  className={`px-2.5 py-1.5 rounded text-xs font-medium transition-colors ${
                    preset === p.value ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </label>

          <label className="text-[11px] text-slate-400" title="Único: un fitness escalar. Pareto: multi-objetivo (NSGA-II), compromiso retorno/riesgo">
            <span className="block mb-1 uppercase">Optimizador</span>
            <div className="flex gap-0.5 bg-slate-900 rounded-md p-0.5">
              {([['single', 'Único'], ['nsga', 'Pareto']] as const).map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setOptimizer(value)}
                  disabled={phase === 'running'}
                  className={`px-2.5 py-1.5 rounded text-xs font-medium transition-colors ${
                    optimizer === value ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </label>

          <div className="flex-1" />

          <button
            onClick={() => { setShowHistory((v) => !v); if (!history.length) loadHistory() }}
            disabled={phase === 'running'}
            className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-100 text-sm font-medium px-4 py-2 rounded-lg transition-colors border border-slate-600"
          >
            Historial
          </button>
          <button
            onClick={handleRun}
            disabled={phase === 'running'}
            className="bg-gradient-to-r from-blue-600 to-purple-600 hover:from-blue-500 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold px-5 py-2 rounded-lg transition-all shadow-lg shadow-blue-900/30"
          >
            {phase === 'running' ? 'Generando…' : '⚡ Generar estrategias'}
          </button>
        </div>

        {showHistory && <HistoryStrip items={history} onStartPaper={() => setPaperKey((k) => k + 1)} />}
      </div>

      {/* Estados */}
      {phase === 'idle' && <IdleHint symbol={symbol} />}
      {phase === 'running' && <RunningState elapsed={elapsed} message={runMsg} preset={preset} />}
      {phase === 'error' && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">{errorMsg}</div>
      )}
      {phase === 'done' && report && <ResultsView report={report} />}
      </>
      )}

      {genView === 'live' && (
      <>
      {/* Mejor estrategia por activo (campeona) con su track record en vivo */}
      <BestStrategiesPanel refreshKey={paperKey} />

      {/* Cartera de estrategias: correlaciones y equity conjunta */}
      <StrategyPortfolioPanel refreshKey={paperKey} />

      {/* Carteras de paper trading (forward test en vivo de las estrategias) */}
      <PaperTradingPanel refreshKey={paperKey} />

      {/* Señales recientes de estrategias monitorizadas */}
      {signalEvents.length > 0 ? (
        <SignalFeed events={signalEvents} />
      ) : (
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 text-sm text-slate-500">
          Aún no hay señales de estrategias monitorizadas. Activa una estrategia guardada
          (pestaña «⚡ Generador» → Historial) para recibir sus señales aquí.
        </div>
      )}
      </>
      )}
    </section>
  )
}

// ══════════════════════════════════════════════════════════════════
// Estados de carga / vacío
// ══════════════════════════════════════════════════════════════════

function IdleHint({ symbol }: Readonly<{ symbol: string }>) {
  const steps = [
    { n: 1, t: 'Evoluciona', d: 'Combina indicadores (RSI, MACD, Bollinger…) en estrategias nuevas con un algoritmo genético.' },
    { n: 2, t: 'Filtra por robustez', d: 'Solo sobreviven las que pasan PBO, walk-forward, Monte Carlo y detección de lookahead.' },
    { n: 3, t: 'Valida en datos intactos', d: 'Reevalúa las finalistas en un tramo final jamás visto durante la evolución.' },
  ]
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-8">
      <p className="text-center text-slate-400 text-sm mb-6">
        Pulsa <span className="text-blue-300 font-medium">Generar estrategias</span> para descubrir
        estrategias robustas sobre <span className="text-white font-semibold">{symbol}</span>.
        El proceso ejecuta cientos de backtests, así que tarda entre 30 s y un par de minutos.
      </p>
      <div className="grid sm:grid-cols-3 gap-4">
        {steps.map((s) => (
          <div key={s.n} className="bg-slate-900/50 rounded-lg border border-slate-700/60 p-4">
            <div className="w-7 h-7 rounded-full bg-blue-600/20 border border-blue-500/40 text-blue-300 text-sm font-bold flex items-center justify-center mb-2">{s.n}</div>
            <p className="text-sm font-semibold text-slate-200">{s.t}</p>
            <p className="text-xs text-slate-500 mt-1 leading-relaxed">{s.d}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

function RunningState({ elapsed, message, preset }: Readonly<{ elapsed: number; message: string; preset: GenPreset }>) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-10">
      <div className="flex flex-col items-center gap-4">
        <div className="relative w-16 h-16">
          <div className="absolute inset-0 border-2 border-slate-700 rounded-full" />
          <div className="absolute inset-0 border-2 border-transparent border-t-blue-400 border-r-purple-400 rounded-full animate-spin" />
          <div className="absolute inset-0 flex items-center justify-center text-lg">🧬</div>
        </div>
        <div className="text-center">
          <p className="text-slate-200 text-sm font-medium">{message}</p>
          <p className="text-slate-500 text-xs mt-1">
            Modo {preset} · {elapsed}s transcurridos
          </p>
        </div>
        <div className="w-full max-w-md h-1 bg-slate-700 rounded-full overflow-hidden">
          <div className="h-full bg-gradient-to-r from-blue-500 to-purple-500 animate-pulse" style={{ width: `${Math.min(95, elapsed * 3)}%` }} />
        </div>
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// Resultados
// ══════════════════════════════════════════════════════════════════

function ResultsView({ report }: Readonly<{ report: GenerationReport }>) {
  const winner = report.ranking[0] ?? null
  return (
    <div className="space-y-6">
      <SummaryStrip report={report} />
      <PartitionBar report={report} />

      <Generator3DPanel
        candidates={report.candidates}
        history={report.ga_evolution.history}
        winnerSpec={winner?.spec ?? null}
      />

      {report.optimizer === 'nsga' && report.pareto_frontier && report.pareto_frontier.length > 0 && (
        <Viz3DSwitch
          title="Frontera de Pareto"
          hint={`${report.pareto_frontier.length} estrategias no dominadas · compromiso retorno / drawdown / sobreajuste`}
          threeD={<ParetoFrontier3D points={report.pareto_frontier} />}
          twoD={<ParetoFrontier2D points={report.pareto_frontier} />}
        />
      )}

      {report.ranking.length > 0 ? (
        <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
          <h3 className="text-sm font-semibold text-white mb-1">Ranking de estrategias robustas</h3>
          <p className="text-xs text-slate-500 mb-4">
            Ordenadas por fitness (Sharpe OOS penalizado). El holdout es rendimiento en datos jamás vistos.
          </p>
          <div className="space-y-3">
            {report.ranking.map((f) => (
              <FinalistCard key={f.spec_hash} f={f} assetSymbol={report.asset_symbol} interval={report.interval} />
            ))}
          </div>
        </div>
      ) : (
        <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl p-6 text-center">
          <p className="text-amber-300 text-sm font-medium">Ninguna estrategia superó el gating de robustez.</p>
          <p className="text-slate-400 text-xs mt-1">
            Es el resultado esperado cuando el mercado/marco no ofrece un edge robusto: el generador
            prefiere no devolver nada antes que entregar una estrategia sobreajustada.
          </p>
        </div>
      )}

      {report.rejected.length > 0 && <RejectedList report={report} />}

      <p className="text-[11px] text-slate-600">
        Datos: {report.data_source} · {report.candles_total} velas · marco {report.interval} ·
        {' '}{report.ga_evolution.evaluations} estrategias evaluadas. Análisis con fines informativos;
        no constituye asesoramiento financiero.
      </p>
    </div>
  )
}

function SummaryStrip({ report }: Readonly<{ report: GenerationReport }>) {
  const cards = [
    { label: 'Robustas', value: report.summary.passed_gating, accent: 'text-emerald-400' },
    { label: 'Candidatas evaluadas', value: report.ga_evolution.evaluations, accent: 'text-slate-200' },
    { label: 'Mejor fitness', value: report.ga_evolution.best_fitness.toFixed(2), accent: 'text-blue-300' },
    { label: 'Generaciones', value: report.ga_config.generations, accent: 'text-slate-200' },
  ]
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {cards.map((c) => (
        <div key={c.label} className="bg-slate-800 rounded-xl border border-slate-700 p-4">
          <p className="text-[10px] text-slate-500 uppercase">{c.label}</p>
          <p className={`text-2xl font-bold font-mono ${c.accent}`}>{c.value}</p>
        </div>
      ))}
    </div>
  )
}

function PartitionBar({ report }: Readonly<{ report: GenerationReport }>) {
  const { evolution_candles, holdout_candles } = report.data_partition
  const total = evolution_candles + holdout_candles || 1
  const evoPct = (evolution_candles / total) * 100
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-white">Partición temporal (anti data-snooping)</h3>
        <span className="text-[10px] text-slate-500">{total} velas</span>
      </div>
      <div className="flex h-9 rounded-lg overflow-hidden border border-slate-700">
        <div className="bg-blue-600/30 border-r border-slate-900 flex items-center justify-center" style={{ width: `${evoPct}%` }}>
          <span className="text-[10px] text-blue-200 font-medium px-2 truncate">Evolución · {evolution_candles}</span>
        </div>
        <div className="bg-purple-600/30 flex items-center justify-center" style={{ width: `${100 - evoPct}%` }}>
          <span className="text-[10px] text-purple-200 font-medium px-2 truncate">Validación · {holdout_candles}</span>
        </div>
      </div>
      <p className="text-[11px] text-slate-500 mt-2 leading-relaxed">{report.data_partition.note}</p>
    </div>
  )
}

/** Descarga un objeto como fichero JSON. */
function downloadJson(filename: string, data: unknown) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const CHECK_LABELS: Record<keyof GatingChecks, string> = {
  min_trades: 'Nº trades',
  no_lookahead: 'Sin lookahead',
  wf_efficiency: 'Eficiencia WF',
  pbo: 'PBO',
  mc_p5_positive: 'Monte Carlo p5',
}

function FinalistCard({ f, assetSymbol, interval }: Readonly<{ f: Finalist; assetSymbol: string; interval: string }>) {
  const [open, setOpen] = useState(false)
  const m = f.gating.metrics
  const h = f.holdout_validation
  return (
    <div className="bg-slate-900/50 rounded-lg border border-slate-700/60 overflow-hidden">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-center gap-3 p-3 text-left hover:bg-white/[0.03] transition-colors">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-emerald-500/20 to-blue-500/20 border border-emerald-500/30 text-emerald-300 font-bold flex items-center justify-center shrink-0">
          #{f.rank}
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm text-slate-200 font-mono truncate">{f.description}</p>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-0.5 text-[11px] text-slate-500">
            <span>fitness <span className="text-blue-300 font-medium">{f.fitness.toFixed(2)}</span></span>
            <span>Sharpe OOS <span className="text-slate-300">{m.mean_oos_sharpe.toFixed(2)}</span></span>
            <span>PBO <span className="text-slate-300">{m.pbo != null ? `${Math.round(m.pbo * 100)}%` : '—'}</span></span>
            <span>holdout <span className={h.return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>{h.return_pct >= 0 ? '+' : ''}{h.return_pct}%</span></span>
          </div>
        </div>
        <svg className={`w-4 h-4 text-slate-500 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-3 border-t border-slate-700/50 pt-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] text-slate-500 font-mono">spec #{f.spec_hash}</span>
            <button
              onClick={() => downloadJson(`estrategia-${f.spec_hash}.json`, {
                spec: f.spec, description: f.description, fitness: f.fitness,
                gating: f.gating, holdout_validation: f.holdout_validation,
              })}
              className="text-[10px] flex items-center gap-1 text-blue-300 hover:text-blue-200 border border-blue-500/30 hover:border-blue-500/60 rounded-md px-2 py-1 transition-colors"
            >
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Exportar JSON
            </button>
          </div>
          {/* Checks del gating */}
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(CHECK_LABELS) as (keyof GatingChecks)[]).map((k) => (
              <span key={k} className={`text-[10px] px-2 py-0.5 rounded-full border flex items-center gap-1 ${
                f.gating.checks[k] ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' : 'bg-red-500/10 text-red-300 border-red-500/30'
              }`}>
                {f.gating.checks[k] ? '✓' : '✗'} {CHECK_LABELS[k]}
              </span>
            ))}
          </div>

          {/* Métricas evolución vs holdout */}
          <div className="grid grid-cols-2 gap-3">
            <MetricBlock title="Zona de evolución" accent="blue" rows={[
              ['Sharpe', m.sharpe.toFixed(2)],
              ['Sharpe OOS', m.mean_oos_sharpe.toFixed(2)],
              ['Eficiencia WF', m.wf_efficiency.toFixed(2)],
              ['Retorno (neto)', `${m.total_return_pct}%`],
              ['Max DD', `-${m.max_drawdown_pct}%`],
              ['Trades', `${m.n_trades}`],
              ['Coste comisiones', `-${(m.cost_drag_pct ?? 0).toFixed(2)}%`],
              ['Rotación', `${(m.turnover ?? 0).toFixed(1)}×`],
            ]} />
            <MetricBlock title="Validación final (intacta)" accent="purple" rows={[
              ['Retorno', `${h.return_pct >= 0 ? '+' : ''}${h.return_pct}%`],
              ['Sharpe', h.sharpe.toFixed(2)],
              ['Max DD', `-${h.max_drawdown_pct}%`],
              ['Win rate', `${h.win_rate_pct}%`],
              ['Trades', `${h.n_trades}`],
              ['Velas', `${h.candles}`],
            ]} />
          </div>

          {/* Análisis profundo de robustez (suite completa + multi-activo) */}
          <SpecRobustnessPanel spec={f.spec} assetSymbol={assetSymbol} interval={interval} />
        </div>
      )}
    </div>
  )
}

function MetricBlock({ title, accent, rows }: Readonly<{ title: string; accent: 'blue' | 'purple'; rows: [string, string][] }>) {
  const dot = accent === 'blue' ? 'bg-blue-400' : 'bg-purple-400'
  return (
    <div className="bg-slate-800/60 rounded-lg p-3">
      <p className="text-[10px] uppercase text-slate-400 mb-2 flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />{title}
      </p>
      <dl className="space-y-1">
        {rows.map(([k, v]) => (
          <div key={k} className="flex justify-between text-[11px]">
            <dt className="text-slate-500">{k}</dt>
            <dd className="text-slate-200 font-mono">{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function RejectedList({ report }: Readonly<{ report: GenerationReport }>) {
  const [open, setOpen] = useState(false)
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700">
      <button onClick={() => setOpen((v) => !v)} className="w-full flex items-center justify-between p-4 text-left">
        <span className="text-sm font-semibold text-slate-300">
          Descartadas por el gating ({report.rejected.length})
        </span>
        <svg className={`w-4 h-4 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="px-4 pb-4 space-y-2">
          {report.rejected.map((r) => (
            <div key={r.spec_hash} className="flex items-center gap-3 text-[11px] py-1.5 border-t border-slate-700/40">
              <span className="text-slate-400 font-mono truncate flex-1">{r.description}</span>
              <div className="flex gap-1 shrink-0">
                {r.failed_checks.map((c) => (
                  <span key={c} className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/10 text-red-300 border border-red-500/20">
                    {CHECK_LABELS[c as keyof GatingChecks] ?? c}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function HistoryStrip({ items, onStartPaper }: Readonly<{ items: SavedStrategy[]; onStartPaper: () => void }>) {
  if (!items.length) {
    return <div className="px-4 pb-4 text-xs text-slate-500">Aún no hay estrategias guardadas para este activo.</div>
  }
  return (
    <div className="px-4 pb-4 border-t border-slate-700/50 pt-3">
      <p className="text-[10px] uppercase text-slate-500 mb-2">Estrategias robustas guardadas · actívalas para recibir su señal o síguelas en paper trading</p>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {items.map((s) => <HistoryCard key={s.id} s={s} onStartPaper={onStartPaper} />)}
      </div>
    </div>
  )
}

const SIGNAL_STYLE: Record<string, string> = {
  BUY: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  SELL: 'bg-red-500/15 text-red-400 border-red-500/30',
  HOLD: 'bg-slate-700/40 text-slate-400 border-slate-600/40',
}

function SignalFeed({ events }: Readonly<{ events: SignalEvent[] }>) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-60" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500" />
        </span>
        <h3 className="text-sm font-semibold text-white">Señales recientes</h3>
        <span className="text-[11px] text-slate-500">de tus estrategias monitorizadas</span>
      </div>
      <div className="space-y-1.5">
        {events.map((e) => (
          <div key={e.id} className="flex items-center gap-3 text-xs py-1.5 border-b border-slate-700/40 last:border-0">
            <span className={`font-bold px-1.5 py-0.5 rounded border ${SIGNAL_STYLE[e.signal]}`}>{e.signal}</span>
            <span className="text-slate-200 font-medium">{e.asset_symbol}</span>
            <span className="text-slate-400 font-mono truncate flex-1">{e.name}</span>
            {e.price != null && <span className="text-slate-300 font-mono shrink-0">${e.price.toLocaleString()}</span>}
            <span className="text-slate-500 shrink-0">{new Date(e.created_at).toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function HistoryCard({ s, onStartPaper }: Readonly<{ s: SavedStrategy; onStartPaper: () => void }>) {
  const [monitored, setMonitored] = useState(s.is_monitored)
  const [signal, setSignal] = useState<string>(s.last_signal || 'HOLD')
  const [busy, setBusy] = useState(false)
  const [paperStarted, setPaperStarted] = useState(false)

  async function toggle() {
    setBusy(true)
    try {
      const r = await strategyGeneratorService.setMonitor(s.id, !monitored)
      setMonitored(r.is_monitored)
      if (r.is_monitored) {
        const sig = await strategyGeneratorService.getSignal(s.id)
        if (!sig.error) setSignal(sig.signal)
      }
    } catch { /* ignora */ } finally { setBusy(false) }
  }

  async function startPaper() {
    setBusy(true)
    try {
      await strategyGeneratorService.startPaperAccount(s.id)
      setPaperStarted(true)
      onStartPaper()
    } catch { /* ignora */ } finally { setBusy(false) }
  }

  async function refreshSignal() {
    setBusy(true)
    try {
      const sig = await strategyGeneratorService.getSignal(s.id)
      if (!sig.error) setSignal(sig.signal)
    } catch { /* ignora */ } finally { setBusy(false) }
  }

  return (
    <div className="shrink-0 w-64 bg-slate-900/60 rounded-lg border border-slate-700/60 p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-emerald-300 font-semibold">#{s.rank} · {s.asset_symbol}</span>
        <button onClick={refreshSignal} disabled={busy} title="Recalcular señal actual"
          className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${SIGNAL_STYLE[signal] ?? SIGNAL_STYLE.HOLD}`}>
          {signal}
        </button>
      </div>
      <p className="text-[11px] text-slate-300 font-mono line-clamp-2 leading-snug h-8">{s.name}</p>
      <div className="flex justify-between text-[10px] text-slate-500 mt-2">
        <span>fitness <span className="text-blue-300">{s.fitness?.toFixed(2) ?? '—'}</span></span>
        <span>holdout <span className={(s.holdout_metrics?.return_pct ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}>
          {s.holdout_metrics?.return_pct ?? '—'}%
        </span></span>
      </div>
      <button
        onClick={toggle}
        disabled={busy}
        className={`mt-2 w-full text-[11px] font-medium rounded-md py-1.5 border transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5 ${
          monitored
            ? 'bg-blue-600/20 text-blue-300 border-blue-500/40 hover:bg-blue-600/30'
            : 'bg-slate-800 text-slate-400 border-slate-600 hover:text-slate-200'
        }`}
      >
        <span className={`w-1.5 h-1.5 rounded-full ${monitored ? 'bg-blue-400 animate-pulse' : 'bg-slate-600'}`} />
        {monitored ? 'Monitorizando' : 'Activar señal'}
      </button>
      <button
        onClick={startPaper}
        disabled={busy || paperStarted}
        title="Sigue esta estrategia con capital ficticio y mide su P&L en vivo"
        className={`mt-1.5 w-full text-[11px] font-medium rounded-md py-1.5 border transition-colors disabled:opacity-50 flex items-center justify-center gap-1.5 ${
          paperStarted
            ? 'bg-emerald-600/20 text-emerald-300 border-emerald-500/40'
            : 'bg-slate-800 text-slate-400 border-slate-600 hover:text-slate-200'
        }`}
      >
        {paperStarted ? '✓ Paper trading activo' : '▶ Seguir en paper trading'}
      </button>
    </div>
  )
}
