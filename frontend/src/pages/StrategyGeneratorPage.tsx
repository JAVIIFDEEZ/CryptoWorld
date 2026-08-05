/**
 * pages/StrategyGeneratorPage.tsx — Generador genético de estrategias (Módulo 2).
 *
 * Lanza el generador (tarea Celery: evolución del GA + gating de robustez),
 * hace polling del job y presenta el ranking de estrategias robustas con sus
 * métricas, la partición temporal anti data-snooping, tres visualizaciones 3D
 * y el historial de estrategias guardadas.
 */

import { lazy, useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAssets } from '@/hooks/queries/useMarketData'
import { type CryptoAsset } from '@/services/analysisService'
import {
  strategyGeneratorService,
  isGenerationReport,
  hasSideBreakdown,
  SIGNAL_BADGES,
  SIGNAL_LABELS,
  SIGNAL_STYLES,
  type LiveSignal,
  type GenerationReport,
  type GenPreset,
  type GenDirection,
  type Finalist,
  type GatingChecks,
  type LaunchResponse,
  type SavedStrategy,
  type SignalEvent,
  type EvolutionProgress,
  type GenerationPower,
} from '@/services/strategyGeneratorService'
import EvolutionLiveBoard from '@/components/generator/EvolutionLiveBoard'
import WalkForwardMatrixCard from '@/components/generator/WalkForwardMatrixCard'
import MultipleTestingCard from '@/components/generator/MultipleTestingCard'
import CpcvDistributionCard from '@/components/generator/CpcvDistributionCard'
import RetestCascadeCard from '@/components/generator/RetestCascadeCard'
import CapacityCard from '@/components/generator/CapacityCard'
import MetaSizingCard from '@/components/generator/MetaSizingCard'
import VariantsCard from '@/components/generator/VariantsCard'
import SideBreakdownCard from '@/components/generator/SideBreakdownCard'
import StrategyComparePanel from '@/components/generator/StrategyComparePanel'
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
const PRESETS: { value: GenPreset; labelKey: string; hint: string }[] = [
  { value: 'fast', labelKey: 'generator.presetFast', hint: 'Población 24 · 8 generaciones' },
  { value: 'balanced', labelKey: 'generator.presetBalanced', hint: 'Población 40 · 15 generaciones' },
  { value: 'thorough', labelKey: 'generator.presetThorough', hint: 'Población 60 · 25 generaciones' },
]

/**
 * Lado del mercado que la ejecución explora.
 *
 * «Ambos» y «Auto» no son la misma opción con distinto nombre: con «Ambos»
 * cada estrategia del libro opera los dos lados —con reglas propias para cada
 * uno, y con la exigencia de que cada lado se sostenga por separado—, mientras
 * que «Auto» deja la dirección a la evolución y devuelve un libro mezclado.
 */
const DIRECTIONS: { value: GenDirection; label: string; hint: string }[] = [
  { value: 'long', label: 'Largos', hint: 'Solo compras. Es lo que el motor ha buscado siempre.' },
  { value: 'short', label: 'Cortos', hint: 'Solo ventas en corto, con las clásicas sembradas en espejo.' },
  { value: 'both', label: 'Ambos', hint: 'Una estrategia que opera los dos lados; cada lado debe aprobar por su cuenta.' },
  { value: 'auto', label: 'Auto', hint: 'La dirección evoluciona como un gen más: el libro sale mezclado.' },
]

const POLL_MS = 2000   // más rápido: la telemetría en vivo se refresca cada poll

/**
 * Techo de espera POR PRESET, no uno único.
 *
 * Un tope plano de 7 minutos servía para «rápido» y mentía en «exhaustivo»:
 * ese preset evoluciona 60 individuos × 25 generaciones × 3 islas y luego pasa
 * a las supervivientes por CPCV, cascada de retests y Monte Carlo. Sobre un
 * histórico largo tarda legítimamente más, y el usuario veía «tiempo agotado»
 * en una ejecución que seguía viva y acabaría bien en el servidor.
 *
 * Rendirse antes de tiempo no es un fallo cosmético: descarta trabajo que ya
 * se ha pagado en cómputo.
 */
const MAX_POLLS: Record<GenPreset, number> = {
  fast: 300,        // 10 min
  balanced: 600,    // 20 min
  thorough: 1200,   // 40 min
}

type Phase = 'idle' | 'running' | 'done' | 'error'

const RUN_MESSAGES = [
  'Sembrando la población inicial…',
  'Evolucionando: selección, cruce y mutación…',
  'Evaluando fitness fuera de muestra (walk-forward)…',
  'Filtrando por robustez: PBO, Monte Carlo, lookahead…',
  'Validando finalistas en el tramo intacto…',
]

export default function StrategyGeneratorPage() {
  const { t } = useTranslation()
  // Catálogo desde la caché compartida (TanStack Query).
  const { data: assetsData, isLoading: loadingAssets } = useAssets()
  // useMemo: estabiliza la identidad del array entre renders (ver efecto abajo).
  const assets = useMemo(() => assetsData ?? [], [assetsData])
  const [symbol, setSymbol] = useState('BTC')
  const [interval, setIntervalTf] = useState('1d')
  const [preset, setPreset] = useState<GenPreset>('balanced')
  const [optimizer, setOptimizer] = useState<'single' | 'nsga'>('single')
  // Largos por defecto: es lo que este motor ha validado siempre. Buscar en el
  // otro lado es una decisión explícita de quien lanza la ejecución.
  const [direction, setDirection] = useState<GenDirection>('long')

  const [phase, setPhase] = useState<Phase>('idle')
  const [report, setReport] = useState<GenerationReport | null>(null)
  const [progress, setProgress] = useState<EvolutionProgress | null>(null)
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
    if (assets.length > 0) {
      setSymbol((cur) => (assets.some((a) => a.symbol === cur) ? cur : assets[0].symbol))
    }
  }, [assets])

  useEffect(() => {
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
    setProgress(null)
    setErrorMsg('')
    setElapsed(0)
    tickRef.current = window.setInterval(() => setElapsed((s) => s + 1), 1000)

    try {
      const { job_id }: LaunchResponse = await strategyGeneratorService.launch({
        asset_symbol: symbol, interval, preset, optimizer, direction,
      })
      let attempts = 0
      pollRef.current = window.setInterval(async () => {
        attempts += 1
        try {
          const s = await strategyGeneratorService.getStatus(job_id)
          if (s.progress) setProgress(s.progress)
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
          } else if (attempts >= MAX_POLLS[preset]) {
            stopTimers()
            // El trabajo NO se pierde: la tarea sigue en el servidor y el
            // informe queda guardado. Decir «inténtalo de nuevo» invitaba a
            // repetir un cómputo de decenas de minutos ya pagado.
            setErrorMsg(
              'La generación está tardando más de lo previsto y se ha dejado de ' +
              'consultar. Sigue ejecutándose en el servidor: revisa el Historial ' +
              'en unos minutos, el resultado aparecerá ahí.',
            )
            setPhase('error')
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
            <h1 className="text-2xl font-bold text-white">{t('generator.title')}</h1>
            <span className="text-[10px] font-semibold uppercase tracking-wider bg-gradient-to-r from-blue-500/20 to-purple-500/20 text-blue-300 border border-blue-500/30 rounded-full px-2 py-0.5">
              {t('generator.badge')}
            </span>
          </div>
          <p className="text-slate-400 text-sm mt-1 max-w-2xl">
            {t('generator.subtitle')}
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
          { key: 'generate', labelKey: 'generator.tabGenerate' },
          { key: 'live', labelKey: 'generator.tabLive' },
        ] as const).map((tabDef) => (
          <button
            key={tabDef.key}
            onClick={() => setGenView(tabDef.key)}
            className={`px-4 py-2 text-sm font-medium -mb-px border-b-2 transition-colors ${
              genView === tabDef.key ? 'border-blue-500 text-white' : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            {t(tabDef.labelKey)}
          </button>
        ))}
      </div>

      {genView === 'generate' && (
      <>
      {/* Panel de lanzamiento */}
      <div className="bg-slate-800 rounded-xl border border-slate-700">
        <div className="flex flex-wrap items-end gap-3 px-4 py-4">
          <label className="text-[11px] text-slate-400">
            <span className="block mb-1 uppercase">{t('generator.asset')}</span>
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
            <span className="block mb-1 uppercase">{t('generator.timeframe')}</span>
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
            <span className="block mb-1 uppercase">{t('generator.depth')}</span>
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
                  {t(p.labelKey)}
                </button>
              ))}
            </div>
          </label>

          <label
            className="text-[11px] text-slate-400"
            title={'Lado del mercado que se busca. «Ambos» genera estrategias que operan los dos '
                 + 'lados con reglas propias para cada uno, y cada lado tiene que sostenerse solo '
                 + 'para aprobar. «Auto» deja que la evolución elija por estrategia.'}
          >
            <span className="block mb-1 uppercase">Dirección</span>
            <div className="flex gap-0.5 bg-slate-900 rounded-md p-0.5">
              {DIRECTIONS.map(({ value, label, hint }) => (
                <button
                  key={value}
                  onClick={() => setDirection(value)}
                  disabled={phase === 'running'}
                  title={hint}
                  className={`px-2.5 py-1.5 rounded text-xs font-medium transition-colors ${
                    direction === value ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </label>

          <label className="text-[11px] text-slate-400" title="Único: un fitness escalar. Pareto: multi-objetivo (NSGA-II), compromiso retorno/riesgo">
            <span className="block mb-1 uppercase">{t('generator.optimizer')}</span>
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
            {phase === 'running' ? t('generator.generating') : t('generator.generate')}
          </button>
        </div>

        {showHistory && <HistoryStrip items={history} onStartPaper={() => setPaperKey((k) => k + 1)} />}
      </div>

      {/* Estados */}
      {phase === 'idle' && <IdleHint symbol={symbol} />}
      {phase === 'running' && (
        <RunningState elapsed={elapsed} message={runMsg} preset={preset} progress={progress} />
      )}
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

function RunningState({ elapsed, message, preset, progress }: Readonly<{
  elapsed: number; message: string; preset: GenPreset; progress: EvolutionProgress | null
}>) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-6">
      {/* Cabecera compacta con el spinner */}
      <div className="flex items-center gap-4 mb-2">
        <div className="relative w-10 h-10 shrink-0">
          <div className="absolute inset-0 border-2 border-slate-700 rounded-full" />
          <div className="absolute inset-0 border-2 border-transparent border-t-blue-400 border-r-purple-400 rounded-full animate-spin" />
          <div className="absolute inset-0 flex items-center justify-center text-sm">🧬</div>
        </div>
        <div className="min-w-0">
          <p className="text-slate-200 text-sm font-medium truncate">{message}</p>
          <p className="text-slate-500 text-xs mt-0.5">Modo {preset} · {elapsed}s transcurridos</p>
        </div>
      </div>

      {/* Evolución en vivo: convergencia + curvas de equity de las candidatas */}
      {progress ? (
        <EvolutionLiveBoard progress={progress} />
      ) : (
        <div className="w-full max-w-md mx-auto h-1 bg-slate-700 rounded-full overflow-hidden mt-4">
          <div className="h-full bg-gradient-to-r from-blue-500 to-purple-500 animate-pulse" style={{ width: `${Math.min(95, elapsed * 3)}%` }} />
        </div>
      )}
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

      {/* Radiografía de estabilidad temporal del campeón */}
      {winner && report.walk_forward_matrix && (
        <WalkForwardMatrixCard matrix={report.walk_forward_matrix} championDesc={winner.description} />
      )}

      {/* Cuántas configuraciones se probaron y qué Sharpe da el azar con ese número.
          Sin ese contexto, el Sharpe de la campeona no es interpretable. */}
      {report.overfitting_control && (
        <MultipleTestingCard control={report.overfitting_control} run={report.experiment_run} />
      )}

      {/* La nube de la que el Sharpe del walk-forward era una sola muestra. */}
      {winner?.gating.metrics.cpcv && (
        <CpcvDistributionCard
          cpcv={winner.gating.metrics.cpcv}
          walkForwardSharpe={winner.gating.metrics.mean_oos_sharpe}
        />
      )}

      {/* Cinco perturbaciones: ¿el edge era real o el histórico afortunado? */}
      {winner?.retests && (
        <RetestCascadeCard retests={winner.retests} championDesc={winner.description} />
      )}

      {/* Cuánto dinero admite el edge, y si su Sharpe es concluyente. */}
      {(winner?.gating.metrics.capacity || winner?.gating.metrics.significance) && (
        <CapacityCard
          capacity={winner.gating.metrics.capacity}
          significance={winner.gating.metrics.significance}
        />
      )}

      {/* Validadas igual que la campeona, apartadas del libro por correlacionar. */}
      {winner?.variants && winner.variants.length > 0 && (
        <VariantsCard variants={winner.variants} championDesc={winner.description} />
      )}

      {/* ¿Todas las señales valen lo mismo? El meta-modelo responde que no. */}
      {winner?.gating.metrics.meta_sizing && (
        <MetaSizingCard meta={winner.gating.metrics.meta_sizing} />
      )}

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
        <EmptyBookExplanation power={report.power} />
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
  const s = report.summary
  const cards = [
    { label: 'Libro robusto', value: s.passed_gating, accent: 'text-emerald-400' },
    { label: 'Candidatas evaluadas', value: report.ga_evolution.evaluations, accent: 'text-slate-200' },
    { label: 'Mejor fitness', value: report.ga_evolution.best_fitness.toFixed(2), accent: 'text-blue-300' },
    { label: 'Generaciones', value: report.ga_config.generations, accent: 'text-slate-200' },
  ]
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {cards.map((c) => (
          <div key={c.label} className="bg-slate-800 rounded-xl border border-slate-700 p-4">
            <p className="text-[10px] text-slate-500 uppercase">{c.label}</p>
            <p className={`text-2xl font-bold font-mono ${c.accent}`}>{c.value}</p>
          </div>
        ))}
      </div>
      {/* Rendimiento del generador: rondas, refinamiento y decorrelación */}
      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        {(s.restarts ?? 1) > 1 && (
          <span className="px-2 py-0.5 rounded-full bg-cyan-500/15 border border-cyan-500/30 text-cyan-300">
            {s.restarts} rondas de búsqueda (semillas frescas)
          </span>
        )}
        {(s.refined ?? 0) > 0 && (
          <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-300">
            {s.refined} finalista{s.refined === 1 ? '' : 's'} refinada{s.refined === 1 ? '' : 's'} (hill-climb re-validado)
          </span>
        )}
        {(s.correlated_dropped ?? 0) > 0 && (
          <span
            className="px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/30 text-amber-300"
            title={report.correlation_filter?.note}
          >
            {s.correlated_dropped} clon{s.correlated_dropped === 1 ? '' : 'es'} descartado{s.correlated_dropped === 1 ? '' : 's'} por correlación (libro decorrelacionado)
          </span>
        )}
      </div>
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
  sides_stand_alone: 'Cada lado aguanta solo',
}

/** Etiqueta del lado que opera la estrategia (los largos no llevan distintivo). */
const DIRECTION_BADGES: Record<'short' | 'both', { label: string; className: string; title: string }> = {
  short: {
    label: 'corto',
    className: 'bg-rose-500/15 border-rose-500/30 text-rose-300',
    title: 'Opera vendiendo en corto: gana cuando el precio baja.',
  },
  both: {
    label: 'largo + corto',
    className: 'bg-amber-500/15 border-amber-500/30 text-amber-300',
    title: 'Opera los dos lados con reglas propias para cada uno. Cada lado ha tenido '
         + 'que sostenerse por separado para llegar hasta aquí.',
  },
}

function DirectionBadge({ direction }: Readonly<{ direction?: string }>) {
  const badge = direction === 'short' || direction === 'both' ? DIRECTION_BADGES[direction] : null
  if (!badge) return null
  return (
    <span
      title={badge.title}
      className={`ml-2 text-[9px] align-middle px-1.5 py-0.5 rounded-full border font-sans ${badge.className}`}
    >
      {badge.label}
    </span>
  )
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
          <p className="text-sm text-slate-200 font-mono truncate">
            {f.description}
            <DirectionBadge direction={m.direction ?? f.spec.direction} />
            {f.refined && (
              <span
                className="ml-2 text-[9px] align-middle px-1.5 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 font-sans"
                title={`Refinada por hill-climb re-validado (+${f.fitness_gain?.toFixed(3)} fitness)`}
              >
                refinada
              </span>
            )}
            {f.cross_asset && f.cross_asset.n_assets > 0 && (
              <span
                className={`ml-2 text-[9px] align-middle px-1.5 py-0.5 rounded-full border font-sans ${
                  f.cross_asset.consistency_score >= 0.67
                    ? 'bg-purple-500/15 border-purple-500/30 text-purple-300'
                    : f.cross_asset.consistency_score >= 0.34
                      ? 'bg-amber-500/15 border-amber-500/30 text-amber-300'
                      : 'bg-red-500/15 border-red-500/30 text-red-300'
                }`}
                title={`Validación cruzada: Sharpe OOS positivo en ${f.cross_asset.n_positive_oos}/${f.cross_asset.n_assets} mercados extra — ${f.cross_asset.results.filter((r) => r.ok).map((r) => `${r.symbol} ${r.oos_sharpe?.toFixed(2)}`).join(' · ')}`}
              >
                {f.cross_asset.n_positive_oos}/{f.cross_asset.n_assets} mercados
              </span>
            )}
          </p>
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
              // Aparte de la comisión a propósito: una escala con el nº de
              // operaciones y la otra con el tiempo en mercado. Solo se muestra
              // si hay histórico — un 0 % aquí diría «no costó nada», y lo que
              // pasaría en realidad es que no se sabe.
              ...(m.funding_drag_pct
                ? [['Financiación', `-${m.funding_drag_pct.toFixed(2)}%`] as [string, string]]
                : []),
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

          {/* De qué lado salió el resultado (solo en estrategias bidireccionales) */}
          {hasSideBreakdown(m.sides) && (
            <SideBreakdownCard sides={m.sides} failures={m.side_failures} />
          )}

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
  // Selección para el comparador cara a cara (máx. 4)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [comparing, setComparing] = useState(false)

  function toggleSelect(id: number) {
    setComparing(false)
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else if (next.size < 4) next.add(id)
      return next
    })
  }

  if (!items.length) {
    return <div className="px-4 pb-4 text-xs text-slate-500">Aún no hay estrategias guardadas para este activo.</div>
  }
  return (
    <div className="px-4 pb-4 border-t border-slate-700/50 pt-3">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <p className="text-[10px] uppercase text-slate-500">Estrategias robustas guardadas · actívalas para recibir su señal o síguelas en paper trading</p>
        {selected.size >= 2 && !comparing && (
          <button
            onClick={() => setComparing(true)}
            className="text-[11px] px-3 py-1 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium"
          >
            ⚖ Comparar seleccionadas ({selected.size})
          </button>
        )}
        {selected.size === 1 && (
          <span className="text-[10px] text-slate-500">Marca al menos 2 para comparar</span>
        )}
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {items.map((s) => (
          <HistoryCard
            key={s.id}
            s={s}
            onStartPaper={onStartPaper}
            selected={selected.has(s.id)}
            onToggleSelect={() => toggleSelect(s.id)}
          />
        ))}
      </div>
      {comparing && selected.size >= 2 && (
        <div className="mt-3">
          <StrategyComparePanel
            ids={[...selected]}
            onClose={() => setComparing(false)}
          />
        </div>
      )}
    </div>
  )
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
            <span
              title={SIGNAL_LABELS[e.signal]}
              className={`font-bold px-1.5 py-0.5 rounded border ${SIGNAL_STYLES[e.signal]}`}
            >
              {SIGNAL_BADGES[e.signal]}
            </span>
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

function HistoryCard({ s, onStartPaper, selected, onToggleSelect }: Readonly<{
  s: SavedStrategy
  onStartPaper: () => void
  selected?: boolean
  onToggleSelect?: () => void
}>) {
  const [monitored, setMonitored] = useState(s.is_monitored)
  const [signal, setSignal] = useState<LiveSignal>(s.last_signal || 'HOLD')
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
    <div className={`shrink-0 w-64 bg-slate-900/60 rounded-lg border p-3 transition-colors ${
      selected ? 'border-blue-500/60 ring-1 ring-blue-500/30' : 'border-slate-700/60'
    }`}>
      <div className="flex items-center justify-between mb-1">
        <label className="flex items-center gap-1.5 cursor-pointer" title="Seleccionar para comparar (máx. 4)">
          {onToggleSelect && (
            <input
              type="checkbox"
              checked={!!selected}
              onChange={onToggleSelect}
              className="w-3 h-3 accent-blue-500"
              aria-label={`Comparar ${s.asset_symbol} #${s.rank}`}
            />
          )}
          <span className="text-[10px] text-emerald-300 font-semibold">#{s.rank} · {s.asset_symbol}</span>
        </label>
        <button
          onClick={refreshSignal} disabled={busy}
          title={`${SIGNAL_LABELS[signal] ?? SIGNAL_LABELS.HOLD} · pulsa para recalcular`}
          className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${SIGNAL_STYLES[signal] ?? SIGNAL_STYLES.HOLD}`}
        >
          {SIGNAL_BADGES[signal] ?? SIGNAL_BADGES.HOLD}
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
      <a
        href={`/strategies/${s.id}/dossier`}
        target="_blank"
        rel="noopener noreferrer"
        title="Documento de auditoría imprimible: ADN, robustez, estado actual y track record"
        className="mt-1.5 w-full text-[11px] font-medium rounded-md py-1.5 border border-slate-600 bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors flex items-center justify-center gap-1.5"
      >
        📄 Dossier de auditoría
      </a>
    </div>
  )
}

/**
 * Por qué el libro salió vacío — y de QUÉ es culpa.
 *
 * Un libro vacío tiene dos causas que no se parecen en nada: que no haya edge
 * (un resultado sobre el mercado) o que no haya muestra (un resultado sobre los
 * datos). Antes se presentaban igual, con un texto que culpaba al mercado —«el
 * mercado/marco no ofrece un edge robusto»—, y eso es una atribución falsa
 * cuando lo que pasó es que se pidieron 30 días de velas.
 *
 * Informar mal es peor que no informar: lleva a descartar un activo por una
 * conclusión que el motor no estaba en condiciones de sacar.
 */
function EmptyBookExplanation({ power }: Readonly<{ power?: GenerationPower }>) {
  const insufficient = power?.reliability === 'insufficient'
  const tone = insufficient
    ? 'bg-sky-500/5 border-sky-500/20'
    : 'bg-amber-500/5 border-amber-500/20'

  return (
    <div className={`${tone} border rounded-xl p-6`}>
      <p className={`text-sm font-medium ${insufficient ? 'text-sky-300' : 'text-amber-300'}`}>
        {insufficient
          ? 'Sin estrategias — pero no por el mercado: por falta de datos.'
          : 'Ninguna estrategia superó el gating de robustez.'}
      </p>

      <p className="text-slate-400 text-xs mt-2 leading-relaxed">
        {insufficient
          ? 'El histórico disponible no da para que las propias pruebas estadísticas ' +
            'emitan un veredicto. Esto NO dice nada sobre si el activo es operable: ' +
            'dice que hacen falta más velas o un marco temporal más amplio.'
          : 'El generador prefiere no devolver nada antes que entregar una estrategia ' +
            'sobreajustada. Con este histórico sí había potencia para juzgar, así que ' +
            'el resultado sí habla del mercado.'}
      </p>

      {power && (
        <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] text-left">
          <PowerStat label="Histórico" value={`${power.span_days} días`} />
          <PowerStat label="Velas por tramo" value={`${power.bars_per_fold}`}
            sub={`${power.days_per_fold} días`} />
          <PowerStat label="Operaciones" value={power.trades_observed != null ? `${power.trades_observed}` : '—'} />
          <PowerStat label="Por tramo"
            value={power.trades_per_fold != null ? `${power.trades_per_fold}` : '—'}
            warn={(power.trades_per_fold ?? 99) < 10} />
        </div>
      )}

      {power?.limits && power.limits.length > 0 && (
        <ul className="mt-3 space-y-1 text-left">
          {power.limits.map((l) => (
            <li key={l} className="text-[10px] text-slate-500 leading-relaxed">· {l}</li>
          ))}
        </ul>
      )}

      {insufficient && (
        <p className="text-[10px] text-sky-200/70 mt-3 leading-relaxed">
          Prueba con un marco mayor (4h o 1d): con el mismo número de velas cubren
          mucho más calendario y dan bastantes más operaciones por tramo, que es lo
          que las pruebas necesitan para discriminar.
        </p>
      )}
    </div>
  )
}

function PowerStat({ label, value, sub, warn }: Readonly<{
  label: string; value: string; sub?: string; warn?: boolean
}>) {
  return (
    <div className="bg-slate-900/40 rounded-lg px-2 py-1.5">
      <p className="text-slate-500">{label}</p>
      <p className={`font-mono text-xs ${warn ? 'text-amber-300' : 'text-slate-200'}`}>{value}</p>
      {sub && <p className="text-slate-600">{sub}</p>}
    </div>
  )
}
