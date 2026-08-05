/**
 * SideBreakdownCard — De qué lado salió el resultado, y si ese lado aguanta solo.
 *
 * Solo aparece en estrategias bidireccionales, y existe porque el agregado de
 * una estrategia que opera los dos lados esconde de dónde viene: un retorno
 * total del +40 % puede ser +55 % en largo y −15 % en corto. Con capital real
 * esa diferencia decide si se despliega la estrategia entera o solo la mitad
 * que funciona.
 *
 * Las dos columnas responden preguntas distintas:
 *   · APORTÓ — operaciones y P&L del lado dentro de la ejecución conjunta.
 *   · AISLADO — Sharpe fuera de muestra del lado operando SOLO. Es el que
 *     bloquea el gating, y no coincide con el anterior porque los dos lados
 *     compiten por la misma posición (el motor mantiene una a la vez), así que
 *     un lado puede aportar poco simplemente porque el otro le quitó turnos.
 */

import type { SideBreakdown, SidePerformance } from '@/services/strategyGeneratorService'

const SIDES: { key: keyof SideBreakdown; label: string; accent: string }[] = [
  { key: 'long', label: 'Largo', accent: 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10' },
  { key: 'short', label: 'Corto', accent: 'text-rose-300 border-rose-500/30 bg-rose-500/10' },
]

function signed(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function SideColumn({ label, accent, stats, minOosSharpe }: Readonly<{
  label: string; accent: string; stats: SidePerformance; minOosSharpe: number
}>) {
  const standsAlone = stats.standalone_oos_sharpe >= minOosSharpe
  const rows: [string, string, string][] = [
    ['Operaciones', `${stats.n_trades}`, 'text-slate-200'],
    ['% del total', `${stats.share_of_trades_pct}%`, 'text-slate-400'],
    ['P&L acumulado', signed(stats.sum_pnl_pct),
      stats.sum_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'],
    ['P&L medio', signed(stats.mean_pnl_pct),
      stats.mean_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'],
    ['Acierto', `${stats.win_rate_pct}%`, 'text-slate-200'],
    // `null` no es infinito: es que este lado aún no ha perdido, que con pocas
    // operaciones no significa que no pierda.
    ['Factor beneficio', stats.profit_factor != null ? stats.profit_factor.toFixed(2) : 'sin pérdidas',
      'text-slate-200'],
  ]
  return (
    <div className="bg-slate-800/60 rounded-lg p-3">
      <div className="flex items-center justify-between mb-2">
        <span className={`text-[10px] uppercase px-2 py-0.5 rounded-full border ${accent}`}>{label}</span>
        <span
          className={`text-[10px] font-mono ${standsAlone ? 'text-emerald-400' : 'text-red-400'}`}
          title={`Sharpe fuera de muestra de este lado operando solo, sobre ${stats.standalone_folds} tramos. `
               + `Por debajo de ${minOosSharpe} el gating bloquea la estrategia entera: un lado que `
               + 'pierde en aislamiento no es cobertura, es una fuga que el otro lado tapa.'}
        >
          {standsAlone ? '✓' : '✗'} aislado {stats.standalone_oos_sharpe.toFixed(2)}
        </span>
      </div>
      <dl className="space-y-1">
        {rows.map(([k, v, tone]) => (
          <div key={k} className="flex justify-between text-[11px]">
            <dt className="text-slate-500">{k}</dt>
            <dd className={`font-mono ${tone}`}>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

export default function SideBreakdownCard({ sides, failures, minOosSharpe = 0 }: Readonly<{
  sides: SideBreakdown
  /** Motivos del gating si algún lado no se sostiene solo. */
  failures?: string[]
  minOosSharpe?: number
}>) {
  return (
    <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-3">
      <p className="text-[10px] uppercase text-slate-400 mb-2 flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
        Reparto por lado
      </p>
      <div className="grid grid-cols-2 gap-3">
        {SIDES.map(({ key, label, accent }) => (
          <SideColumn key={key} label={label} accent={accent}
                      stats={sides[key]} minOosSharpe={minOosSharpe} />
        ))}
      </div>
      {failures && failures.length > 0 && (
        <ul className="mt-2 space-y-0.5">
          {failures.map((reason) => (
            <li key={reason} className="text-[11px] text-red-300 flex gap-1.5">
              <span aria-hidden>✗</span>{reason}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-[10px] text-slate-500 leading-relaxed">
        Los dos lados comparten una sola posición, así que sus operaciones no suman las
        que tendría cada uno por separado: se las disputan. Por eso «aislado» se mide
        aparte —es el lado operando solo— y es lo que decide el gating.
      </p>
    </div>
  )
}
