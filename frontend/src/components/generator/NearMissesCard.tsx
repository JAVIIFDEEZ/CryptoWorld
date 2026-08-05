/**
 * NearMissesCard — Las que se quedaron a un solo control, y por cuánto.
 *
 * Existe porque «rechazada por Monte Carlo» tapa la diferencia entre quedarse a
 * dos centésimas del umbral y quedarse a diez puntos, y son situaciones
 * distintas: la primera dice que ahí hay algo que merece otra ejecución con más
 * histórico o con otra semilla, la segunda dice que no.
 *
 * Lo que esta tarjeta NO puede insinuar es que el umbral debería bajar. Elegir
 * el listón después de ver el salto es exactamente el sesgo que el gating
 * existe para frenar, y por eso el aviso del pie no es decorativo.
 */

import type { NearMiss } from '@/services/strategyGeneratorService'

/** Bajo este margen relativo, la candidata está rozando la línea. */
const GRAZING = 0.05

function formatValue(check: string, value: number): string {
  if (check === 'min_trades') return `${Math.round(value)}`
  if (check === 'mc_p5_positive') return `${value.toFixed(2)}%`
  return value.toFixed(3)
}

function Margin({ miss }: Readonly<{ miss: NearMiss }>) {
  if (miss.gap_ratio == null) {
    return <span className="text-slate-500 text-[10px]">sin escala comparable</span>
  }
  const grazing = miss.gap_ratio < GRAZING
  return (
    <span
      className={`font-mono text-[10px] px-1.5 py-0.5 rounded border ${
        grazing
          ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
          : 'bg-slate-700/40 text-slate-400 border-slate-600/40'
      }`}
      title={`Se quedó a ${(miss.gap_ratio * 100).toFixed(1)}% del umbral, medido en la escala del propio control.`}
    >
      {grazing ? 'rozando' : 'a'} {(miss.gap_ratio * 100).toFixed(1)}%
    </span>
  )
}

export default function NearMissesCard({ misses }: Readonly<{ misses: NearMiss[] }>) {
  if (!misses.length) return null

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center gap-2 mb-1">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
        <h3 className="text-sm font-semibold text-white">
          A un solo control del libro
        </h3>
        <span className="text-[11px] text-slate-500">
          {misses.length} candidata{misses.length === 1 ? '' : 's'}
        </span>
      </div>
      <p className="text-[11px] text-slate-400 mb-3 leading-relaxed">
        Pasaron todo el gating menos un control. Siguen fuera del libro — esto no
        cambia ningún veredicto, solo enseña la distancia.
      </p>

      <div className="space-y-1.5">
        {misses.map((m) => (
          <div key={m.spec_hash} className="flex items-center gap-2 text-[11px] py-1.5 border-t border-slate-700/40">
            <span className="text-slate-300 font-mono truncate flex-1" title={m.description}>
              {m.description}
            </span>
            <span className="text-slate-500 shrink-0">{m.label}</span>
            {m.observed != null && m.required != null && (
              <span className="font-mono text-slate-400 shrink-0">
                {formatValue(m.check, m.observed)} / {formatValue(m.check, m.required)}
              </span>
            )}
            <Margin miss={m} />
          </div>
        ))}
      </div>

      <p className="text-[10px] text-slate-500 mt-3 leading-relaxed">
        Los umbrales no se mueven por esto. Bajarlos porque una candidata se quedó
        cerca sería elegir el listón después de ver el salto — el sesgo que este
        gating existe para frenar. Si crees que una merece otra oportunidad, dale
        más histórico o cambia la semilla y que lo vuelva a intentar contra el
        mismo listón.
      </p>
    </div>
  )
}
