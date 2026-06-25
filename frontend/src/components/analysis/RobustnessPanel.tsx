/**
 * components/RobustnessPanel.tsx — Suite de robustez de backtest.
 *
 * Lanza la suite (tarea Celery) para la estrategia elegida, hace polling del
 * job y muestra el informe: Robustness Score, veredicto, métricas, los
 * diagnósticos (PBO, DSR, walk-forward, Monte Carlo, permutación, sesgos) y
 * los gráficos (equity OOS, histograma Monte Carlo, ranking de trials).
 *
 * Es la capa premium que avisa si una estrategia está sobreajustada.
 */

import { useEffect, useRef, useState } from 'react'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, Tooltip, Cell,
} from 'recharts'
import {
  robustnessService,
  isReport,
  isComparison,
  type RobustStrategy,
  type RobustObjective,
  type RobustPreset,
  type RobustnessReport,
  type ComparisonReport,
  type LaunchResponse,
} from '@/services/robustnessService'
import { analysisService, type StrategyInfo } from '@/services/analysisService'
import Gauge from '@/components/ui/Gauge'

const INTERVALS = ['1d', '4h', '1h', '1w']
const OBJECTIVES: { value: RobustObjective; label: string }[] = [
  { value: 'sharpe', label: 'Sharpe' },
  { value: 'sortino', label: 'Sortino' },
  { value: 'calmar', label: 'Calmar' },
  { value: 'total_return', label: 'Retorno total' },
]
const PRESETS: { value: RobustPreset; label: string }[] = [
  { value: 'fast', label: 'Rápido' },
  { value: 'balanced', label: 'Equilibrado' },
  { value: 'thorough', label: 'Exhaustivo' },
]

const POLL_MS = 2500
const MAX_POLLS = 90  // ~3.75 min de techo

type Phase = 'idle' | 'running' | 'done' | 'error'

const VERDICT_STYLE: Record<string, { text: string; chip: string }> = {
  ROBUSTA: { text: 'text-emerald-400', chip: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' },
  'FRÁGIL': { text: 'text-amber-400', chip: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  SOBREAJUSTADA: { text: 'text-red-400', chip: 'bg-red-500/15 text-red-400 border-red-500/30' },
}

export default function RobustnessPanel({ symbol }: Readonly<{ symbol: string }>) {
  const [strategy, setStrategy] = useState<RobustStrategy>('rsi_reversal')
  const [timeframe, setTimeframe] = useState('1d')
  const [objective, setObjective] = useState<RobustObjective>('sharpe')
  const [preset, setPreset] = useState<RobustPreset>('balanced')
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])

  const [phase, setPhase] = useState<Phase>('idle')
  const [report, setReport] = useState<RobustnessReport | null>(null)
  const [comparison, setComparison] = useState<ComparisonReport | null>(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [elapsed, setElapsed] = useState(0)

  const pollRef = useRef<number>(0)
  const tickRef = useRef<number>(0)

  useEffect(() => {
    analysisService.getStrategies().then(setStrategies).catch(() => { /* lista vacía */ })
  }, [])

  // Limpieza de timers al desmontar
  useEffect(() => () => {
    window.clearInterval(pollRef.current)
    window.clearInterval(tickRef.current)
  }, [])

  function stopTimers() {
    window.clearInterval(pollRef.current)
    window.clearInterval(tickRef.current)
  }

  async function run(launch: () => Promise<LaunchResponse>) {
    stopTimers()
    setPhase('running')
    setReport(null)
    setComparison(null)
    setErrorMsg('')
    setElapsed(0)
    tickRef.current = window.setInterval(() => setElapsed((s) => s + 1), 1000)

    try {
      const { job_id } = await launch()
      let attempts = 0
      pollRef.current = window.setInterval(async () => {
        attempts += 1
        try {
          const s = await robustnessService.getStatus(job_id)
          if (s.status === 'SUCCESS') {
            stopTimers()
            if (isComparison(s.result)) {
              setComparison(s.result)
              setPhase('done')
            } else if (isReport(s.result)) {
              setReport(s.result)
              setPhase('done')
            } else {
              setErrorMsg(s.result?.error ?? 'No hay datos suficientes para la suite.')
              setPhase('error')
            }
          } else if (s.status === 'FAILURE') {
            stopTimers()
            setErrorMsg('La suite de robustez falló durante la ejecución.')
            setPhase('error')
          } else if (attempts >= MAX_POLLS) {
            stopTimers()
            setErrorMsg('Tiempo de espera agotado. Inténtalo de nuevo.')
            setPhase('error')
          }
        } catch {
          stopTimers()
          setErrorMsg('Error consultando el estado del análisis.')
          setPhase('error')
        }
      }, POLL_MS)
    } catch {
      stopTimers()
      setErrorMsg('No se pudo lanzar el análisis de robustez.')
      setPhase('error')
    }
  }

  const handleRun = () =>
    run(() => robustnessService.launch({ asset_symbol: symbol, strategy, interval: timeframe, objective, preset }))

  const handleCompare = () =>
    run(() => robustnessService.launchComparison({ asset_symbol: symbol, interval: timeframe, objective, preset }))

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 mb-6">
      {/* Cabecera */}
      <div className="px-4 pt-4 pb-3 border-b border-slate-700">
        <h2 className="text-lg font-semibold text-white">Suite de robustez de backtest</h2>
        <p className="text-xs text-slate-500">
          ¿Tu estrategia tiene un edge real o está sobreajustada? Walk-forward, Monte Carlo,
          Deflated Sharpe, PBO y detectores de sesgo.
        </p>
      </div>

      {/* Controles */}
      <div className="flex flex-wrap items-end gap-3 px-4 py-3 border-b border-slate-700/50">
        <label className="text-[11px] text-slate-400">
          <span className="block mb-1 uppercase">Estrategia</span>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value as RobustStrategy)}
            disabled={phase === 'running'}
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 min-w-[180px] focus:ring-1 focus:ring-blue-500 outline-none"
          >
            {(strategies.length ? strategies : [{ key: strategy, name: strategy, description: '' }]).map((s) => (
              <option key={s.key} value={s.key}>{s.name}</option>
            ))}
          </select>
        </label>

        <label className="text-[11px] text-slate-400">
          <span className="block mb-1 uppercase">Marco</span>
          <div className="flex gap-0.5 bg-slate-900 rounded-md p-0.5">
            {INTERVALS.map((iv) => (
              <button
                key={iv}
                onClick={() => setTimeframe(iv)}
                disabled={phase === 'running'}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  timeframe === iv ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                {iv}
              </button>
            ))}
          </div>
        </label>

        <label className="text-[11px] text-slate-400">
          <span className="block mb-1 uppercase">Objetivo</span>
          <select
            value={objective}
            onChange={(e) => setObjective(e.target.value as RobustObjective)}
            disabled={phase === 'running'}
            className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-sm text-slate-200 focus:ring-1 focus:ring-blue-500 outline-none"
          >
            {OBJECTIVES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
        </label>

        <label className="text-[11px] text-slate-400" title="Rapidez vs exhaustividad del análisis">
          <span className="block mb-1 uppercase">Profundidad</span>
          <div className="flex gap-0.5 bg-slate-900 rounded-md p-0.5">
            {PRESETS.map((p) => (
              <button
                key={p.value}
                onClick={() => setPreset(p.value)}
                disabled={phase === 'running'}
                className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                  preset === p.value ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </label>

        <div className="flex-1" />
        <button
          onClick={handleCompare}
          disabled={phase === 'running'}
          className="bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:cursor-not-allowed text-slate-100 text-sm font-medium px-4 py-2 rounded-lg transition-colors border border-slate-600"
        >
          Comparar las 5
        </button>
        <button
          onClick={handleRun}
          disabled={phase === 'running'}
          className="bg-blue-600 hover:bg-blue-500 disabled:bg-blue-900 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          {phase === 'running' ? 'Analizando…' : 'Analizar estrategia'}
        </button>
      </div>

      {/* Contenido */}
      <div className="p-4 min-h-[160px]">
        {phase === 'idle' && (
          <p className="text-slate-500 text-sm text-center py-10">
            Lanza el análisis para evaluar la robustez de la estrategia sobre {symbol}.
            La suite ejecuta cientos de backtests, así que tarda unos segundos.
          </p>
        )}

        {phase === 'running' && (
          <div className="flex flex-col items-center justify-center py-12 gap-3">
            <div className="w-8 h-8 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
            <p className="text-slate-400 text-sm">Ejecutando la suite de robustez… {elapsed}s</p>
            <p className="text-slate-600 text-xs">Walk-forward + Optuna + Monte Carlo + permutaciones</p>
          </div>
        )}

        {phase === 'error' && (
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">{errorMsg}</div>
        )}

        {phase === 'done' && comparison && <ComparisonView data={comparison} />}
        {phase === 'done' && report && <RobustnessReportView report={report} />}
      </div>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// Comparación de estrategias
// ══════════════════════════════════════════════════════════════════

function ComparisonView({ data }: Readonly<{ data: ComparisonReport }>) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-slate-300">
        Ranking de robustez de las 5 estrategias sobre {data.asset_symbol} (marco {data.interval}).
        La mejor es <span className="font-semibold text-emerald-400">{data.best.strategy_name}</span>.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-500 border-b border-slate-700 text-xs uppercase">
              <th className="text-left py-2 px-2">#</th>
              <th className="text-left py-2 px-2">Estrategia</th>
              <th className="text-left py-2 px-2 w-40">Score</th>
              <th className="text-left py-2 px-2">Veredicto</th>
              <th className="text-right py-2 px-2">Sharpe</th>
              <th className="text-right py-2 px-2">Max DD</th>
              <th className="text-right py-2 px-2">PBO</th>
              <th className="text-right py-2 px-2">WF</th>
            </tr>
          </thead>
          <tbody>
            {data.ranking.map((row, i) => {
              if (row.error || row.robustness_score == null) {
                return (
                  <tr key={row.strategy} className="border-b border-slate-700/40">
                    <td className="py-2 px-2 text-slate-500">{i + 1}</td>
                    <td className="py-2 px-2 text-slate-300">{row.strategy_name}</td>
                    <td colSpan={6} className="py-2 px-2 text-slate-500 text-xs italic">Sin datos suficientes</td>
                  </tr>
                )
              }
              const sc = row.robustness_score
              const tone = VERDICT_STYLE[row.verdict ?? 'FRÁGIL']
              return (
                <tr key={row.strategy} className={`border-b border-slate-700/40 ${i === 0 ? 'bg-emerald-500/5' : ''}`}>
                  <td className="py-2 px-2 text-slate-500">{i + 1}</td>
                  <td className="py-2 px-2 text-slate-200 font-medium">{row.strategy_name}</td>
                  <td className="py-2 px-2">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 bg-slate-700 rounded-full h-2 min-w-[60px]">
                        <div
                          className={`h-2 rounded-full ${sc >= 70 ? 'bg-emerald-500' : sc >= 45 ? 'bg-amber-500' : 'bg-red-500'}`}
                          style={{ width: `${sc}%` }}
                        />
                      </div>
                      <span className="font-mono text-xs text-slate-300 w-6 text-right">{sc}</span>
                    </div>
                  </td>
                  <td className="py-2 px-2">
                    <span className={`text-[11px] font-semibold px-2 py-0.5 rounded border ${tone.chip}`}>{row.verdict}</span>
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-slate-300">{row.sharpe?.toFixed(2) ?? '—'}</td>
                  <td className="py-2 px-2 text-right font-mono text-red-400">-{row.max_drawdown_pct}%</td>
                  <td className="py-2 px-2 text-right font-mono text-slate-300">{row.pbo != null ? `${Math.round(row.pbo * 100)}%` : '—'}</td>
                  <td className="py-2 px-2 text-right font-mono text-slate-300">{row.oos_efficiency != null ? row.oos_efficiency.toFixed(2) : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-slate-600">
        Score = robustez global (0-100). PBO = probabilidad de sobreajuste (menor mejor).
        WF = eficiencia walk-forward (cercana a 1 mejor). Análisis con fines informativos.
      </p>
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════
// Informe
// ══════════════════════════════════════════════════════════════════

function RobustnessReportView({ report }: Readonly<{ report: RobustnessReport }>) {
  const v = VERDICT_STYLE[report.verdict] ?? VERDICT_STYLE['FRÁGIL']
  const d = report.diagnostics

  return (
    <div className="space-y-6">
      {/* Veredicto + score */}
      <div className="flex flex-col sm:flex-row items-center gap-5 bg-slate-900/40 rounded-xl border border-slate-700 p-5">
        <Gauge value={report.robustness_score} label="Robustness Score" width={180} />
        <div className="flex-1 text-center sm:text-left">
          <span className={`inline-block px-3 py-1 rounded-lg text-sm font-bold border ${v.chip} mb-2`}>
            {report.verdict}
          </span>
          <p className="text-sm text-slate-300 leading-relaxed">{report.explanation}</p>
          <div className="flex flex-wrap gap-1.5 mt-3 justify-center sm:justify-start">
            {Object.entries(report.best_params).map(([k, val]) => (
              <span key={k} className="text-[11px] bg-slate-800 border border-slate-700 rounded px-2 py-0.5 text-slate-400">
                {k}: <span className="text-slate-200 font-mono">{val}</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Razones y fortalezas */}
      {(report.reasons.length > 0 || report.strengths.length > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {report.strengths.length > 0 && (
            <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-lg p-4">
              <h3 className="text-xs font-semibold text-emerald-400 uppercase mb-2">Fortalezas</h3>
              <ul className="space-y-1 text-sm text-slate-300">
                {report.strengths.map((s) => <li key={s}>✓ {s}</li>)}
              </ul>
            </div>
          )}
          {report.reasons.length > 0 && (
            <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-4">
              <h3 className="text-xs font-semibold text-red-400 uppercase mb-2">Señales de alerta</h3>
              <ul className="space-y-1 text-sm text-slate-300">
                {report.reasons.map((r) => <li key={r}>• {r}</li>)}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Componentes del score */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3">Componentes del score</h3>
        <div className="space-y-2">
          {Object.entries(report.component_scores).map(([name, val]) => (
            <div key={name} className="flex items-center gap-3">
              <span className="text-xs text-slate-400 w-32 capitalize">{COMPONENT_LABELS[name] ?? name}</span>
              <div className="flex-1 bg-slate-700 rounded-full h-2.5">
                <div
                  className={`h-2.5 rounded-full ${val >= 70 ? 'bg-emerald-500' : val >= 45 ? 'bg-amber-500' : 'bg-red-500'}`}
                  style={{ width: `${val}%` }}
                />
              </div>
              <span className="text-xs font-mono text-slate-300 w-9 text-right">{val}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Diagnósticos clave */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3">Diagnósticos</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          <DiagCard
            label="PBO"
            help="Probabilidad de sobreajuste"
            value={fmtPct(d.pbo.pbo)}
            good={d.pbo.pbo != null && d.pbo.pbo <= 0.3}
            bad={d.pbo.pbo != null && d.pbo.pbo > 0.5}
          />
          <DiagCard
            label="Deflated Sharpe"
            help="Sharpe corregido por nº de pruebas"
            value={d.deflated_sharpe.dsr != null ? d.deflated_sharpe.dsr.toFixed(2) : '—'}
            good={d.deflated_sharpe.dsr != null && d.deflated_sharpe.dsr >= 0.7}
            bad={d.deflated_sharpe.dsr != null && d.deflated_sharpe.dsr < 0.5}
          />
          <DiagCard
            label="Walk-forward"
            help="Eficiencia OOS/IS (anchored)"
            value={d.walk_forward_anchored.efficiency != null ? d.walk_forward_anchored.efficiency.toFixed(2) : '—'}
            good={(d.walk_forward_anchored.efficiency ?? 0) >= 0.7}
            bad={(d.walk_forward_anchored.efficiency ?? 1) < 0.5}
          />
          <DiagCard
            label="Permutación"
            help="p-valor del edge (significativo < 0.05)"
            value={d.permutation.p_value != null ? d.permutation.p_value.toFixed(3) : '—'}
            good={d.permutation.significant}
            bad={d.permutation.p_value != null && d.permutation.p_value >= 0.1}
          />
          <DiagCard
            label="MC beneficio"
            help="Probabilidad de beneficio (Monte Carlo)"
            value={fmtPct(d.monte_carlo.prob_profit_pct != null ? d.monte_carlo.prob_profit_pct / 100 : null)}
            good={(d.monte_carlo.prob_profit_pct ?? 0) >= 60}
            bad={(d.monte_carlo.prob_profit_pct ?? 100) < 50}
          />
          <DiagCard
            label="Lookahead"
            help="Fuga de información futura"
            value={d.lookahead.is_leaky ? 'FUGA' : 'OK'}
            good={!d.lookahead.is_leaky}
            bad={d.lookahead.is_leaky}
          />
          <DiagCard
            label="Inestabilidad"
            help="Deriva recursiva del indicador"
            value={d.recursive_instability.is_unstable ? 'Sí' : 'No'}
            good={!d.recursive_instability.is_unstable}
            bad={d.recursive_instability.is_unstable}
          />
          <DiagCard
            label="MC retorno p50"
            help="Mediana del retorno simulado"
            value={d.monte_carlo.return_pct.p50 != null ? `${d.monte_carlo.return_pct.p50}%` : '—'}
          />
        </div>
      </div>

      {/* Métricas */}
      <div>
        <h3 className="text-sm font-semibold text-white mb-3">Métricas de rendimiento y riesgo</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Metric label="Sharpe" value={report.metrics.sharpe.toFixed(2)} />
          <Metric label="Sortino" value={report.metrics.sortino.toFixed(2)} />
          <Metric label="Calmar" value={report.metrics.calmar.toFixed(2)} />
          <Metric label="Profit factor" value={report.metrics.profit_factor != null ? report.metrics.profit_factor.toFixed(2) : '∞'} />
          <Metric label="VaR 95%" value={`-${report.metrics.var_95_pct}%`} tone="negative" />
          <Metric label="CVaR 95%" value={`-${report.metrics.cvar_95_pct}%`} tone="negative" />
          <Metric label="Max drawdown" value={`-${report.metrics.max_drawdown_pct}%`} tone="negative" />
          <Metric label="Exposición" value={`${report.metrics.exposure_pct}%`} />
        </div>
      </div>

      {/* Gráficos */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <ChartCard title="Equity fuera de muestra (walk-forward)">
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={report.charts.oos_equity_curve.map((value, i) => ({ i, value }))}
              margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="oosEq" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.4} />
                  <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="i" tick={{ fill: '#64748b', fontSize: 10 }} hide />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} width={48} domain={['auto', 'auto']} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }} formatter={(val) => [`${Number(val).toFixed(0)}`, 'Equity']} />
              <Area type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} fill="url(#oosEq)" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Distribución Monte Carlo (retorno %)">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={histogram(report.charts.monte_carlo_distribution, 22)}
              margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="bin" tick={{ fill: '#64748b', fontSize: 10 }} />
              <YAxis tick={{ fill: '#64748b', fontSize: 10 }} width={32} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: '#94a3b8' }} formatter={(val) => [Number(val), 'Simulaciones']} />
              <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                {histogram(report.charts.monte_carlo_distribution, 22).map((b) => (
                  <Cell key={b.bin} fill={b.mid >= 0 ? '#22c55e' : '#ef4444'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Ranking de trials */}
      {report.charts.trial_ranking.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-white mb-3">Mejores configuraciones probadas</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-slate-700">
                  <th className="text-left py-1.5 px-2">#</th>
                  <th className="text-left py-1.5 px-2">Parámetros</th>
                  <th className="text-right py-1.5 px-2">{report.metrics ? 'Objetivo' : ''}</th>
                </tr>
              </thead>
              <tbody>
                {report.charts.trial_ranking.slice(0, 8).map((t, i) => (
                  <tr key={i} className="border-b border-slate-700/40">
                    <td className="py-1.5 px-2 text-slate-500">{i + 1}</td>
                    <td className="py-1.5 px-2 text-slate-300 font-mono">
                      {Object.entries(t.params).map(([k, val]) => `${k}=${val}`).join('  ')}
                    </td>
                    <td className="py-1.5 px-2 text-right font-mono text-slate-200">{t.value.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="text-[11px] text-slate-600">
        Datos: {report.data_source} · {report.candles_count} velas · marco {report.interval}.
        Análisis estadístico con fines informativos; no constituye asesoramiento financiero.
      </p>
    </div>
  )
}

// ── Subcomponentes ─────────────────────────────────────────────────

const COMPONENT_LABELS: Record<string, string> = {
  pbo: 'PBO', dsr: 'Deflated Sharpe', walk_forward: 'Walk-forward',
  monte_carlo: 'Monte Carlo', permutation: 'Permutación',
}

function DiagCard({ label, help, value, good, bad }: Readonly<{
  label: string; help: string; value: string; good?: boolean; bad?: boolean
}>) {
  const tone = good ? 'text-emerald-400' : bad ? 'text-red-400' : 'text-slate-200'
  return (
    <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-3" title={help}>
      <p className="text-[10px] text-slate-500 uppercase truncate">{label}</p>
      <p className={`text-lg font-bold font-mono ${tone}`}>{value}</p>
    </div>
  )
}

function Metric({ label, value, tone }: Readonly<{ label: string; value: string; tone?: 'negative' }>) {
  return (
    <div className="bg-slate-900/40 rounded-lg p-3">
      <p className="text-[10px] text-slate-500 uppercase">{label}</p>
      <p className={`text-sm font-bold font-mono ${tone === 'negative' ? 'text-red-400' : 'text-slate-200'}`}>{value}</p>
    </div>
  )
}

function ChartCard({ title, children }: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-4">
      <h4 className="text-xs font-semibold text-slate-300 mb-3">{title}</h4>
      {children}
    </div>
  )
}

// ── Helpers ────────────────────────────────────────────────────────

function fmtPct(value: number | null | undefined): string {
  if (value == null) return '—'
  return `${Math.round(value * 100)}%`
}

/** Agrupa una distribución de valores en `bins` barras para el histograma. */
function histogram(values: number[], bins: number): { bin: string; mid: number; count: number }[] {
  if (values.length === 0) return []
  const min = Math.min(...values)
  const max = Math.max(...values)
  if (min === max) return [{ bin: min.toFixed(0), mid: min, count: values.length }]
  const width = (max - min) / bins
  const buckets = Array.from({ length: bins }, (_, i) => ({
    bin: (min + width * (i + 0.5)).toFixed(0),
    mid: min + width * (i + 0.5),
    count: 0,
  }))
  for (const v of values) {
    const idx = Math.min(bins - 1, Math.floor((v - min) / width))
    buckets[idx].count += 1
  }
  return buckets
}
