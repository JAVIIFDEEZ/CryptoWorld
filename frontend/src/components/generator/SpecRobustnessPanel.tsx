/**
 * components/generator/SpecRobustnessPanel.tsx — Análisis profundo de un spec.
 *
 * Lanza la suite de robustez completa de una estrategia generada (PBO, Deflated
 * Sharpe, Monte Carlo, permutación, lookahead) más la validación multi-activo,
 * hace polling del job y muestra el informe con score, veredicto, diagnósticos
 * y consistencia cruzada. Reutiliza la capa visual de la suite de robustez.
 */

import { useEffect, useRef, useState } from 'react'
import {
  strategyGeneratorService, isSpecRobustnessReport,
  type StrategySpec, type SpecRobustnessReport,
} from '@/services/strategyGeneratorService'
import Gauge from '@/components/ui/Gauge'

const POLL_MS = 2500
const MAX_POLLS = 100

type Phase = 'idle' | 'running' | 'done' | 'error'

const VERDICT_CHIP: Record<string, string> = {
  ROBUSTA: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  'FRÁGIL': 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  SOBREAJUSTADA: 'bg-red-500/15 text-red-400 border-red-500/30',
}

interface Props {
  spec: StrategySpec
  assetSymbol: string
  interval: string
}

export default function SpecRobustnessPanel({ spec, assetSymbol, interval }: Readonly<Props>) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [report, setReport] = useState<SpecRobustnessReport | null>(null)
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const pollRef = useRef<number>(0)
  const tickRef = useRef<number>(0)

  useEffect(() => () => { window.clearInterval(pollRef.current); window.clearInterval(tickRef.current) }, [])

  function stop() { window.clearInterval(pollRef.current); window.clearInterval(tickRef.current) }

  async function run() {
    stop(); setPhase('running'); setReport(null); setError(''); setElapsed(0)
    tickRef.current = window.setInterval(() => setElapsed((s) => s + 1), 1000)
    try {
      const { job_id } = await strategyGeneratorService.launchRobustness({ spec, asset_symbol: assetSymbol, interval, preset: 'fast' })
      let attempts = 0
      pollRef.current = window.setInterval(async () => {
        attempts += 1
        try {
          const s = await strategyGeneratorService.getRobustnessStatus(job_id)
          if (s.status === 'SUCCESS') {
            stop()
            if (isSpecRobustnessReport(s.result)) { setReport(s.result); setPhase('done') }
            else { setError(s.result && 'error' in s.result ? s.result.error : 'Sin datos suficientes.'); setPhase('error') }
          } else if (s.status === 'FAILURE') { stop(); setError('El análisis falló.'); setPhase('error') }
          else if (attempts >= MAX_POLLS) { stop(); setError('Tiempo agotado.'); setPhase('error') }
        } catch { stop(); setError('Error consultando el análisis.'); setPhase('error') }
      }, POLL_MS)
    } catch { stop(); setError('No se pudo lanzar el análisis.'); setPhase('error') }
  }

  if (phase === 'idle') {
    return (
      <button onClick={run} className="w-full text-xs text-purple-300 hover:text-purple-200 border border-purple-500/30 hover:border-purple-500/60 rounded-lg py-2 transition-colors flex items-center justify-center gap-2">
        <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
        Análisis profundo de robustez (suite + multi-activo)
      </button>
    )
  }

  if (phase === 'running') {
    return (
      <div className="flex items-center justify-center gap-3 py-6 text-sm text-slate-400">
        <div className="w-5 h-5 border-2 border-slate-600 border-t-purple-400 rounded-full animate-spin" />
        Analizando robustez en {assetSymbol} y otros activos… {elapsed}s
      </div>
    )
  }

  if (phase === 'error') {
    return <div className="bg-red-900/30 border border-red-700 rounded-lg p-3 text-red-300 text-xs">{error}</div>
  }

  if (!report) return null
  const d = report.diagnostics
  return (
    <div className="space-y-4 bg-slate-900/40 rounded-lg border border-slate-700/60 p-4">
      <div className="flex flex-col sm:flex-row items-center gap-4">
        <Gauge value={report.robustness_score} label="Robustness Score" width={150} />
        <div className="flex-1 text-center sm:text-left">
          <span className={`inline-block px-3 py-1 rounded-lg text-xs font-bold border ${VERDICT_CHIP[report.verdict]} mb-2`}>{report.verdict}</span>
          <p className="text-xs text-slate-300 leading-relaxed">{report.explanation}</p>
        </div>
      </div>

      {/* Diagnósticos */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        <Diag label="PBO" value={pct(d.pbo.pbo)} good={d.pbo.pbo != null && d.pbo.pbo <= 0.3} bad={d.pbo.pbo != null && d.pbo.pbo > 0.5} />
        <Diag label="Deflated Sharpe" value={d.deflated_sharpe.dsr != null ? d.deflated_sharpe.dsr.toFixed(2) : '—'} good={(d.deflated_sharpe.dsr ?? 0) >= 0.7} bad={d.deflated_sharpe.dsr != null && d.deflated_sharpe.dsr < 0.5} />
        <Diag label="Walk-forward" value={d.walk_forward_anchored.efficiency != null ? d.walk_forward_anchored.efficiency.toFixed(2) : '—'} good={(d.walk_forward_anchored.efficiency ?? 0) >= 0.7} bad={(d.walk_forward_anchored.efficiency ?? 1) < 0.5} />
        <Diag label="Permutación p" value={d.permutation.p_value != null ? d.permutation.p_value.toFixed(3) : '—'} good={d.permutation.significant} bad={d.permutation.p_value != null && d.permutation.p_value >= 0.1} />
        <Diag label="MC beneficio" value={pct(d.monte_carlo.prob_profit_pct != null ? d.monte_carlo.prob_profit_pct / 100 : null)} good={(d.monte_carlo.prob_profit_pct ?? 0) >= 60} bad={(d.monte_carlo.prob_profit_pct ?? 100) < 50} />
        <Diag label="Lookahead" value={d.lookahead.is_leaky ? 'FUGA' : 'OK'} good={!d.lookahead.is_leaky} bad={d.lookahead.is_leaky} />
      </div>

      {/* Validación multi-activo */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h5 className="text-xs font-semibold text-white">Consistencia multi-activo</h5>
          <span className="text-[11px] text-slate-400">
            {report.cross_asset.n_positive_oos}/{report.cross_asset.n_assets} con Sharpe OOS+ ·
            <span className={report.cross_asset.consistency_score >= 0.6 ? 'text-emerald-400' : 'text-amber-400'}>
              {' '}{Math.round(report.cross_asset.consistency_score * 100)}%
            </span>
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-slate-500 border-b border-slate-700">
                <th className="text-left py-1 px-2">Activo</th>
                <th className="text-right py-1 px-2">Sharpe OOS</th>
                <th className="text-right py-1 px-2">Retorno</th>
                <th className="text-right py-1 px-2">Max DD</th>
                <th className="text-right py-1 px-2">Trades</th>
              </tr>
            </thead>
            <tbody>
              {report.cross_asset.results.map((r) => (
                <tr key={r.symbol} className="border-b border-slate-700/40">
                  <td className="py-1 px-2 text-slate-200 font-medium">{r.symbol}</td>
                  {r.ok ? (
                    <>
                      <td className={`py-1 px-2 text-right font-mono ${(r.oos_sharpe ?? 0) > 0 ? 'text-emerald-400' : 'text-red-400'}`}>{r.oos_sharpe?.toFixed(2)}</td>
                      <td className="py-1 px-2 text-right font-mono text-slate-300">{r.total_return_pct}%</td>
                      <td className="py-1 px-2 text-right font-mono text-red-400">-{r.max_drawdown_pct}%</td>
                      <td className="py-1 px-2 text-right font-mono text-slate-400">{r.n_trades}</td>
                    </>
                  ) : (
                    <td colSpan={4} className="py-1 px-2 text-right text-slate-600 italic">{r.note ?? 'sin datos'}</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-[10px] text-slate-600 mt-1">
          Un edge robusto generaliza a otros activos; si solo funciona en {report.asset_symbol}, sospecha de sobreajuste.
        </p>
      </div>
    </div>
  )
}

function Diag({ label, value, good, bad }: Readonly<{ label: string; value: string; good?: boolean; bad?: boolean }>) {
  const tone = good ? 'text-emerald-400' : bad ? 'text-red-400' : 'text-slate-200'
  return (
    <div className="bg-slate-800/60 rounded-lg p-2.5">
      <p className="text-[10px] text-slate-500 uppercase truncate">{label}</p>
      <p className={`text-base font-bold font-mono ${tone}`}>{value}</p>
    </div>
  )
}

function pct(v: number | null | undefined): string {
  return v == null ? '—' : `${Math.round(v * 100)}%`
}
