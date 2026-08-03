/**
 * components/generator/RetestCascadeCard.tsx — Cascada de retests del campeón.
 *
 * Cinco perturbaciones, cada una atacando una forma distinta de sobreajuste.
 * La pregunta que responden juntas es: ¿el resultado venía de un edge, o de que
 * el histórico fuera exactamente el que fue?
 *
 * Una prueba que no pudo ejecutarse se muestra como «sin datos», no como
 * aprobada: ausencia de evidencia no es evidencia de solidez, y pintarla en
 * verde sería justo el tipo de adorno que este panel existe para evitar.
 */

import type { RetestCascade } from '@/services/strategyGeneratorService'

type Row = {
  key: keyof RetestCascade['checks']
  label: string
  question: string
  detail: string
  ran: boolean
}

function buildRows(r: RetestCascade): Row[] {
  const noise = r.noise ?? { n_runs: 0 }
  const start = r.starting_bar ?? { n_offsets: 0 }
  const skip = r.skip_trades ?? { n_runs: 0 }
  const sens = r.parameter_sensitivity ?? { n_neighbors: 0 }
  const stab = r.temporal_stability ?? { n_buckets: 0 }

  return [
    {
      key: 'noise',
      label: 'Ruido en los precios',
      question: '¿Dependía de las velas exactas que ocurrieron?',
      ran: noise.n_runs > 0,
      detail: noise.n_runs > 0
        ? `${noise.pct_runs_positive?.toFixed(0)}% de ${noise.n_runs} series perturbadas en positivo · degrada ${noise.degradation_pct?.toFixed(0)}%`
        : 'Serie insuficiente para perturbar',
    },
    {
      key: 'starting_bar',
      label: 'Arranque desplazado',
      question: '¿Dependía de dónde se cortó el histórico?',
      ran: start.n_offsets > 0,
      detail: start.n_offsets > 0
        ? `${start.pct_offsets_positive?.toFixed(0)}% de ${start.n_offsets} arranques en positivo · σ ${start.sharpe_std?.toFixed(2)}`
        : 'Histórico insuficiente para variar el arranque',
    },
    {
      key: 'skip_trades',
      label: 'Operaciones omitidas',
      question: '¿Dependía de capturarlas todas?',
      ran: skip.n_runs > 0,
      detail: skip.n_runs > 0
        ? `${skip.pct_runs_profitable?.toFixed(0)}% rentable perdiendo ejecuciones · p5 ${skip.pnl_p5_pct?.toFixed(1)}%`
        : 'Muy pocas operaciones para la prueba',
    },
    {
      key: 'parameter_sensitivity',
      label: 'Parámetros perturbados',
      question: '¿Dependía del parámetro exacto?',
      ran: sens.n_neighbors > 0,
      detail: sens.n_neighbors > 0
        ? `${sens.pct_neighbors_positive?.toFixed(0)}% de ${sens.n_neighbors} vecinos en positivo · degrada ${sens.median_degradation_pct?.toFixed(0)}%`
        : 'Sin vecinos evaluables',
    },
    {
      key: 'temporal_stability',
      label: 'Reparto en el tiempo',
      question: '¿El beneficio estaba repartido, o fue una racha?',
      ran: stab.n_buckets > 0,
      detail: stab.n_buckets > 0
        ? `el mejor de ${stab.n_buckets} periodos aporta el ${((stab.concentration ?? 0) * 100).toFixed(0)}% del beneficio · ${stab.positive_buckets}/${stab.n_buckets} positivos`
        : 'Serie insuficiente para partir en periodos',
    },
  ]
}

export default function RetestCascadeCard({ retests, championDesc }: Readonly<{
  retests: RetestCascade
  championDesc?: string
}>) {
  if (!retests?.checks) return null
  const rows = buildRows(retests)

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
        <h3 className="text-sm font-semibold text-white">
          Cascada de retests
          <span className="ml-2 text-[10px] font-normal text-slate-500">
            ¿edge real o histórico afortunado?
          </span>
        </h3>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${
            retests.survived
              ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
              : 'bg-amber-500/15 border-amber-500/30 text-amber-300'
          }`}
        >
          {retests.survived
            ? 'sobrevive a todas'
            : `falla ${retests.failed.length} de ${rows.length}`}
        </span>
      </div>
      {championDesc && (
        <p className="text-[10px] text-slate-500 mb-3 truncate" title={championDesc}>
          {championDesc}
        </p>
      )}

      <ul className="space-y-2">
        {rows.map((row) => {
          const ok = retests.checks[row.key]
          return (
            <li key={row.key} className="flex items-start gap-2">
              <span
                aria-hidden="true"
                className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold ${
                  !row.ran
                    ? 'bg-slate-700 text-slate-400'
                    : ok
                      ? 'bg-emerald-500/25 text-emerald-300'
                      : 'bg-red-500/25 text-red-300'
                }`}
              >
                {!row.ran ? '–' : ok ? '✓' : '✕'}
              </span>
              <div className="min-w-0">
                <p className="text-[11px] text-white leading-tight">
                  {row.label}
                  <span className="ml-1.5 text-slate-500 font-normal">{row.question}</span>
                  {!row.ran && (
                    <span className="ml-1.5 text-[9px] text-slate-500 italic">sin datos</span>
                  )}
                </p>
                <p className="text-[10px] text-slate-400 leading-tight">{row.detail}</p>
              </div>
            </li>
          )
        })}
      </ul>

      <p className="text-[10px] text-slate-500 mt-3 leading-relaxed">{retests.note}</p>
    </div>
  )
}
