/**
 * EmptyBookExplanation — Por qué esta búsqueda no devolvió nada.
 *
 * Es la superficie donde más fácil es mentir sin querer. Un libro vacío tiene
 * tres causas que llevan a acciones OPUESTAS, y presentarlas todas como «el
 * mercado no ofrece un edge robusto» es una atribución falsa que además manda
 * al usuario en la dirección equivocada.
 */

import type { GenerationPower, GenerationReport } from '@/services/strategyGeneratorService'

/**
 * Por qué el libro salió vacío.
 *
 * Tres motivos distintos que no se pueden confundir, porque llevan a acciones
 * opuestas: **faltan datos** (repetir con más histórico), **el mercado no
 * ofrece edge** (probar otro activo o marco), o **un lado sangraba** (repetir
 * en una sola dirección). Presentar el tercero como el segundo sería una
 * atribución falsa: había edge, y estaba en un lado concreto.
 */
export default function EmptyBookExplanation({ power, report }: Readonly<{
  power?: GenerationPower; report?: GenerationReport
}>) {
  const insufficient = power?.reliability === 'insufficient'
  const rejected = report?.rejected ?? []
  // Rechazadas ÚNICAMENTE por el control por lado: pasaron el nº de
  // operaciones, el PBO, el Monte Carlo, la eficiencia y el detector de
  // lookahead, y solo cayeron porque un lado no se sostiene solo.
  const onlySides = rejected.filter(
    (r) => r.failed_checks.length === 1 && r.failed_checks[0] === 'sides_stand_alone').length
  const sideBlocked = !insufficient && onlySides > 0 && onlySides >= rejected.length / 2

  const tone = insufficient
    ? 'bg-sky-500/5 border-sky-500/20'
    : sideBlocked
      ? 'bg-rose-500/5 border-rose-500/20'
      : 'bg-amber-500/5 border-amber-500/20'
  const headTone = insufficient ? 'text-sky-300' : sideBlocked ? 'text-rose-300' : 'text-amber-300'

  let headline: string
  let body: string
  if (insufficient) {
    headline = 'Sin estrategias — pero no por el mercado: por falta de datos.'
    body = 'El histórico disponible no da para que las propias pruebas estadísticas '
         + 'emitan un veredicto. Esto NO dice nada sobre si el activo es operable: '
         + 'dice que hacen falta más velas o un marco temporal más amplio.'
  } else if (sideBlocked) {
    headline = 'Había edge, pero solo en un lado.'
    body = `${onlySides} de ${rejected.length} candidatas pasaron TODO el gating `
         + '—operaciones, PBO, Monte Carlo, eficiencia walk-forward, lookahead— y cayeron '
         + 'únicamente porque uno de sus dos lados pierde dinero cuando se mide en '
         + 'aislamiento. No es que el mercado no ofrezca nada: es que la mitad de estas '
         + 'estrategias sangraba escondida detrás de la otra mitad.'
  } else {
    headline = 'Ninguna estrategia superó el gating de robustez.'
    body = 'El generador prefiere no devolver nada antes que entregar una estrategia '
         + 'sobreajustada. Con este histórico sí había potencia para juzgar, así que '
         + 'el resultado sí habla del mercado.'
  }

  return (
    <div className={`${tone} border rounded-xl p-6`}>
      <p className={`text-sm font-medium ${headTone}`}>{headline}</p>

      <p className="text-slate-400 text-xs mt-2 leading-relaxed">{body}</p>

      {sideBlocked && (
        <p className="text-[11px] text-rose-200/70 mt-2 leading-relaxed">
          Repite la búsqueda en una sola dirección —Largos o Cortos— y esas mismas
          estrategias no tendrán que arrastrar el lado que las hundía.
        </p>
      )}

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
