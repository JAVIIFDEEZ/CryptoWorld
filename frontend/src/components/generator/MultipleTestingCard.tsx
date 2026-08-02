/**
 * components/generator/MultipleTestingCard.tsx — Control de multiplicidad.
 *
 * «La curva más importante de las finanzas cuantitativas»: el Sharpe máximo que
 * produce el puro azar crece con el número de configuraciones probadas. Por eso
 * un Sharpe sin decir cuántas pruebas se hicieron no significa nada — y por eso
 * esta tarjeta sitúa a la campeona frente a esa curva.
 *
 * Si el punto de la campeona queda POR DEBAJO de la curva en su propio número de
 * pruebas, el resultado es indistinguible de haber buscado mucho.
 */

import type { GenerationReport } from '@/services/strategyGeneratorService'

type Control = NonNullable<GenerationReport['overfitting_control']>
type Run = NonNullable<GenerationReport['experiment_run']>

const W = 520
const H = 150
const PAD = { left: 40, right: 12, top: 12, bottom: 26 }

export default function MultipleTestingCard({ control, run }: Readonly<{
  control: Control
  run?: Run
}>) {
  const { curve, expected_max_at_n: threshold, observed_sharpe: observed, n_trials: nTrials } =
    control.expected_max_sharpe_curve
  const points = curve ?? []

  if (points.length < 2) {
    return null
  }

  const beatsChance = observed !== null && observed > threshold
  const maxY = Math.max(threshold, observed ?? 0, ...points.map((p) => p.expected_max_sharpe)) * 1.15 || 1
  const minTrials = Math.log10(Math.max(points[0].trials, 1) || 1)
  const maxTrials = Math.log10(Math.max(points[points.length - 1].trials, 10))
  const span = Math.max(maxTrials - minTrials, 1e-9)

  // Eje X logarítmico: el crecimiento del máximo esperado es logarítmico en N,
  // así que en escala lineal la curva sería una pared indistinguible.
  const x = (trials: number) =>
    PAD.left + ((Math.log10(Math.max(trials, 1)) - minTrials) / span) * (W - PAD.left - PAD.right)
  const y = (value: number) => H - PAD.bottom - (value / maxY) * (H - PAD.top - PAD.bottom)

  const path = points
    .map((p, i) => `${i === 0 ? 'M' : 'L'} ${x(p.trials).toFixed(1)} ${y(p.expected_max_sharpe).toFixed(1)}`)
    .join(' ')

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
        <h3 className="text-sm font-semibold text-white">
          Control de multiplicidad
          <span className="ml-2 text-[10px] font-normal text-slate-500">
            el Sharpe que produce el azar con {nTrials.toLocaleString('es-ES')} pruebas
          </span>
        </h3>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${
            beatsChance
              ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
              : 'bg-amber-500/15 border-amber-500/30 text-amber-300'
          }`}
        >
          {beatsChance ? 'supera al azar' : 'no se distingue del azar'}
        </span>
      </div>

      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 my-3 text-[10px]">
        <div>
          <dt className="text-slate-500">Configuraciones probadas</dt>
          <dd className="text-white font-mono text-xs">{control.evaluated.toLocaleString('es-ES')}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Independientes</dt>
          <dd className="text-white font-mono text-xs">
            {control.effective_trials?.toLocaleString('es-ES') ?? '—'}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Umbral del azar</dt>
          <dd className="text-amber-300 font-mono text-xs">{threshold.toFixed(3)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Sharpe de la campeona</dt>
          <dd className={`font-mono text-xs ${beatsChance ? 'text-emerald-300' : 'text-red-300'}`}>
            {observed !== null ? observed.toFixed(3) : '—'}
          </dd>
        </div>
      </dl>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full h-auto min-w-[420px]"
          role="img"
          aria-label={
            `Curva del Sharpe máximo esperado por azar frente al número de pruebas. ` +
            `Con ${nTrials} pruebas el azar alcanza ${threshold.toFixed(3)}; ` +
            `la campeona obtiene ${observed !== null ? observed.toFixed(3) : 'un valor no disponible'}.`
          }
        >
          <line x1={PAD.left} y1={H - PAD.bottom} x2={W - PAD.right} y2={H - PAD.bottom}
                stroke="currentColor" className="text-slate-700" strokeWidth={1} />
          <line x1={PAD.left} y1={PAD.top} x2={PAD.left} y2={H - PAD.bottom}
                stroke="currentColor" className="text-slate-700" strokeWidth={1} />

          {/* Sharpe observado: línea horizontal de referencia */}
          {observed !== null && (
            <>
              <line
                x1={PAD.left} y1={y(observed)} x2={W - PAD.right} y2={y(observed)}
                stroke="currentColor" strokeDasharray="4 3" strokeWidth={1}
                className={beatsChance ? 'text-emerald-400' : 'text-red-400'}
              />
              <text x={W - PAD.right} y={y(observed) - 4} textAnchor="end"
                    className={`text-[9px] fill-current ${beatsChance ? 'text-emerald-300' : 'text-red-300'}`}>
                campeona {observed.toFixed(3)}
              </text>
            </>
          )}

          {/* E[max Sharpe] por azar */}
          <path d={path} fill="none" stroke="currentColor" strokeWidth={2} className="text-amber-400" />

          {/* Posición de esta ejecución sobre la curva */}
          <circle cx={x(nTrials)} cy={y(threshold)} r={4}
                  className="fill-current text-amber-300" />
          <text x={x(nTrials)} y={y(threshold) - 8} textAnchor="middle"
                className="text-[9px] fill-current text-amber-200">
            N={nTrials.toLocaleString('es-ES')}
          </text>

          <text x={PAD.left - 6} y={y(maxY * 0.87)} textAnchor="end"
                className="text-[9px] fill-current text-slate-500">
            {(maxY * 0.87).toFixed(2)}
          </text>
          <text x={PAD.left - 6} y={H - PAD.bottom} textAnchor="end"
                className="text-[9px] fill-current text-slate-500">0</text>
          <text x={(W + PAD.left) / 2} y={H - 6} textAnchor="middle"
                className="text-[9px] fill-current text-slate-500">
            nº de configuraciones probadas (escala logarítmica)
          </text>
        </svg>
      </div>

      <p className="text-[10px] text-slate-500 mt-2 leading-relaxed">{control.note}</p>

      {/* Contexto histórico del activo. El Sharpe deflactado usa el N de ESTA
          ejecución (reproducible); el acumulado es gobernanza, no deflación. */}
      {run?.registered && (run.cumulative_evaluations ?? 0) > 0 && (
        <p className="text-[10px] text-slate-500 mt-2 pt-2 border-t border-slate-700/60 leading-relaxed">
          Histórico del activo:{' '}
          <span className="text-slate-300 font-mono">
            {run.cumulative_evaluations?.toLocaleString('es-ES')}
          </span>{' '}
          configuraciones probadas en{' '}
          <span className="text-slate-300 font-mono">{run.cumulative_runs}</span>{' '}
          {run.cumulative_runs === 1 ? 'ejecución' : 'ejecuciones'} registradas.
          {run.catalog_version && (
            <> · catálogo <span className="font-mono">{run.catalog_version}</span></>
          )}
          {run.seed !== null && run.seed !== undefined && (
            <> · semilla <span className="font-mono">{run.seed}</span></>
          )}
        </p>
      )}
    </div>
  )
}
