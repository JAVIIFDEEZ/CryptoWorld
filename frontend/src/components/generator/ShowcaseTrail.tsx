/**
 * ShowcaseTrail — Qué fue de cada estrategia que viste durante la evolución.
 *
 * Cierra el salto entre las dos pantallas del generador. Mientras evoluciona se
 * ven curvas de equity con retornos llamativos; al terminar, el informe solo
 * habla de las que llegaron al gating. Entre medias hay un silencio que nadie
 * explica: una candidata que hizo un +33 % puede no volver a aparecer, y desde
 * fuera es imposible distinguir «la descartaron por sobreajuste» de «se perdió
 * por el camino». Lo primero es el motor funcionando; lo segundo sería un fallo.
 * Presentar los dos como silencio es lo que hace desconfiar de la herramienta.
 *
 * Aquí cada una acaba en uno de cuatro sitios, y ninguno es silencio.
 */

import type { Disposition, ShowcaseRow, Showcase } from '@/services/strategyGeneratorService'

const DISPOSITIONS: Record<Disposition, { label: string; className: string; title: string }> = {
  in_book: {
    label: 'en el libro',
    className: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300',
    title: 'Pasó el gating y encabeza el libro decorrelacionado.',
  },
  variant: {
    label: 'variante',
    className: 'bg-sky-500/15 border-sky-500/30 text-sky-300',
    title: 'Pasó exactamente los mismos controles, pero correlaciona con una '
         + 'cabeza de libro: cinco formas del mismo edge no diversifican. Viaja '
         + 'como variante suya, con sus métricas completas.',
  },
  rejected: {
    label: 'descartada',
    className: 'bg-red-500/15 border-red-500/30 text-red-300',
    title: 'Se examinó con el gating completo y no lo pasó.',
  },
  not_gated: {
    label: 'sin examinar',
    className: 'bg-slate-700/50 border-slate-600/50 text-slate-400',
    title: 'Nunca llegó a examinarse. No es un veredicto sobre la estrategia: el '
         + 'gating tiene presupuesto limitado y se gasta por orden de fitness.',
  },
}

const ORDER: Disposition[] = ['in_book', 'variant', 'rejected', 'not_gated']

function Row({ row }: Readonly<{ row: ShowcaseRow }>) {
  const d = DISPOSITIONS[row.disposition]
  const up = row.total_return_pct >= 0
  const failed = row.detail?.failed_checks ?? []
  const grazing = row.detail?.near_miss?.gap_ratio

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] py-1.5 border-t border-slate-700/40">
      <span className={`text-[9px] uppercase px-1.5 py-0.5 rounded border shrink-0 ${d.className}`} title={d.title}>
        {d.label}
      </span>
      <span className={`font-mono shrink-0 ${up ? 'text-emerald-400/80' : 'text-red-400/80'}`}>
        {up ? '+' : ''}{row.total_return_pct.toFixed(1)}%
        <span className="text-slate-600"> is</span>
      </span>
      <span className="font-mono text-slate-500 shrink-0">{row.n_trades} ops</span>
      <span className="font-mono text-blue-300/80 shrink-0" title="Fitness: Sharpe fuera de muestra penalizado.">
        {row.fitness.toFixed(2)}
      </span>
      <span className="text-slate-400 font-mono truncate flex-1 min-w-[8rem]" title={row.description}>
        {row.description}
      </span>
      {failed.length > 0 && (
        <span className="text-[9px] text-red-300/70 shrink-0">
          falló: {failed.join(' · ')}
          {grazing != null && grazing < 0.05 && (
            <span className="text-amber-300/80"> (a {(grazing * 100).toFixed(1)}%)</span>
          )}
        </span>
      )}
    </div>
  )
}

export default function ShowcaseTrail({ showcase }: Readonly<{ showcase?: Showcase }>) {
  if (!showcase?.rows?.length) return null
  const { counts, shown, rows } = showcase

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex flex-wrap items-baseline gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-400" />
        <h3 className="text-sm font-semibold text-white">Qué fue de lo que viste</h3>
        <span className="text-[11px] text-slate-500">
          {shown} estrategia{shown === 1 ? '' : 's'} mostrada{shown === 1 ? '' : 's'} durante la evolución
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5 mb-2">
        {ORDER.filter((k) => counts[k]).map((k) => (
          <span
            key={k}
            className={`text-[10px] px-2 py-0.5 rounded-full border ${DISPOSITIONS[k].className}`}
            title={DISPOSITIONS[k].title}
          >
            {counts[k]} {DISPOSITIONS[k].label}
          </span>
        ))}
      </div>

      <p className="text-[11px] text-slate-400 mb-1 leading-relaxed">
        El retorno marcado <span className="font-mono text-slate-500">is</span> es{' '}
        <strong className="font-medium text-slate-300">dentro de muestra</strong>: sale de los mismos
        datos con los que se seleccionó la estrategia, así que está inflado por construcción. Es el
        número que el gating existe para no creerse — por eso una candidata puede enseñar un +70 % y
        quedarse fuera.
      </p>

      <div>
        {rows.map((r) => <Row key={r.hash} row={r} />)}
      </div>

      {shown > rows.length && (
        <p className="text-[10px] text-slate-600 mt-2">
          Se detallan las {rows.length} de mayor fitness; el recuento de arriba cubre las {shown}.
        </p>
      )}
    </div>
  )
}
