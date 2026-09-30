/**
 * CorrelationHeatmap.tsx — El mapa de correlaciones, sin invitar a leer lo que no hay.
 *
 * Un mapa de calor de correlaciones es la pieza más fácil de convertir en adorno
 * peligroso: un degradado bonito sobre una matriz cuyo error de estimación nadie
 * publica. Tres decisiones de presentación, las tres deliberadas y las tres
 * contra la costumbre del sector:
 *
 *  · **El error va arriba, no en una nota al pie.** Con ventana 90 el error
 *    típico de cada celda es de ~0,11 en el espacio de Fisher. Dos celdas que
 *    difieren en menos que eso son la misma celda pintada distinta, y quien mira
 *    el degradado no tiene forma de saberlo si no se le dice.
 *  · **El titular es el espectro, no la matriz.** «Un factor explica el 74 % de
 *    la varianza y hay 2,3 apuestas efectivas de 12» es una frase accionable;
 *    una cuadrícula de colores no lo es. La matriz está debajo, para mirar el
 *    detalle.
 *  · **El cambio se marca con un borde, no con color.** El color ya codifica el
 *    nivel, y meter dos variables en el mismo canal las hace ilegibles. Y la
 *    marca dice explícitamente que no lleva corrección por multiplicidad: con
 *    doce activos son 66 comparaciones y unas tres saldrán marcadas sin que nada
 *    haya cambiado.
 *
 * El orden de las filas lo decide el backend por conglomerados, no el abecedario:
 * es lo único que un mapa de calor sirve para mostrar y alfabético lo esconde.
 */

import { useEffect, useMemo, useState } from 'react'
import { marketService, type CorrelationMap } from '@/services/marketService'

/**
 * Color de una celda según su correlación.
 *
 * Divergente en torno a cero: azul para negativa, rojo para positiva. Los cortes
 * no son estéticos — por encima de 0,7 la diversificación entre esos dos activos
 * es casi nula y por debajo de 0,3 hay riesgo distinto de verdad, así que el salto
 * de color cae donde cambia la decisión.
 */
export function cellColor(rho: number): string {
  if (!Number.isFinite(rho)) return 'bg-slate-800'
  if (rho >= 0.9) return 'bg-red-600'
  if (rho >= 0.7) return 'bg-red-500/80'
  if (rho >= 0.5) return 'bg-orange-500/70'
  if (rho >= 0.3) return 'bg-amber-500/50'
  if (rho > -0.3) return 'bg-slate-700/60'
  if (rho > -0.5) return 'bg-sky-600/50'
  if (rho > -0.7) return 'bg-sky-500/70'
  return 'bg-blue-600'
}

/** Etiqueta y color del veredicto de concentración. */
export function verdictStyle(v: CorrelationMap['verdict']): {
  label: string
  cls: string
} {
  switch (v) {
    case 'CONCENTRADO':
      return { label: 'Concentrado', cls: 'text-red-300 border-red-500/40' }
    case 'REPARTIDO':
      return { label: 'Repartido', cls: 'text-emerald-300 border-emerald-500/40' }
    case 'INTERMEDIO':
      return { label: 'Intermedio', cls: 'text-amber-300 border-amber-500/40' }
    default:
      return { label: 'Sin datos', cls: 'text-slate-400 border-slate-600/40' }
  }
}

/**
 * Cuántas celdas se esperan marcadas por puro azar.
 *
 * Se calcula y se muestra porque es la única forma de que el usuario sepa
 * interpretar el número de marcas que está viendo. Con un umbral de dos errores
 * típicos, la tasa nominal es de ~5 % por celda.
 */
export function expectedFalseMarks(n: number): number {
  const pares = (n * (n - 1)) / 2
  return Math.round(pares * 0.05)
}

export default function CorrelationHeatmap({
  symbols,
  interval = '1h',
  window: ventana = 90,
}: Readonly<{ symbols?: string[]; interval?: string; window?: number }>) {
  const [data, setData] = useState<CorrelationMap | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)
  const [mostrarCambio, setMostrarCambio] = useState(false)

  useEffect(() => {
    let vivo = true
    setCargando(true)
    setError(null)
    marketService
      .getCorrelationMap({ symbols, interval, window: ventana, referenceWindow: ventana })
      .then((d) => {
        if (vivo) setData(d)
      })
      .catch(() => {
        if (vivo) setError('No se pudo cargar el mapa de correlaciones.')
      })
      .finally(() => {
        if (vivo) setCargando(false)
      })
    return () => {
      vivo = false
    }
  }, [symbols, interval, ventana])

  const falsasEsperadas = useMemo(
    () => (data?.labels?.length ? expectedFalseMarks(data.labels.length) : 0),
    [data?.labels?.length],
  )

  if (cargando) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-900/50 p-4">
        <p className="text-sm text-slate-400">Calculando correlaciones…</p>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-900/50 p-4">
        <p className="text-sm text-slate-400">{error ?? 'Sin datos.'}</p>
      </div>
    )
  }

  if (data.verdict === 'SIN_DATOS' || !data.labels.length) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-900/50 p-4">
        <h3 className="text-sm font-semibold text-slate-200">Correlaciones</h3>
        <p className="mt-2 text-sm text-slate-400">{data.note}</p>
      </div>
    )
  }

  const v = verdictStyle(data.verdict)
  const eigen = data.eigen
  const cambio = mostrarCambio && data.delta ? data.delta : null
  const marcas = data.delta_beyond_noise

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">
            Correlaciones · {data.labels.length} activos · ventana {data.window}
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            {data.interval} · {data.candles_aligned ?? '—'} velas comunes
            {data.missing?.length ? ` · sin histórico: ${data.missing.join(', ')}` : ''}
          </p>
        </div>
        <span className={`rounded border px-2 py-0.5 text-xs font-medium ${v.cls}`}>
          {v.label}
        </span>
      </div>

      {/* El titular: el espectro. Es lo accionable; la cuadrícula es el detalle. */}
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Cifra
          etiqueta="Un solo factor explica"
          valor={eigen.top_share != null ? `${(eigen.top_share * 100).toFixed(0)} %` : '—'}
          nota="de la varianza total"
        />
        <Cifra
          etiqueta="Apuestas efectivas"
          valor={
            eigen.effective_bets != null
              ? `${eigen.effective_bets.toFixed(1)} / ${eigen.n}`
              : '—'
          }
          nota="riesgos independientes"
        />
        <Cifra
          etiqueta="Correlación media"
          valor={
            data.average_correlation != null ? data.average_correlation.toFixed(2) : '—'
          }
          nota={
            data.reference_average_correlation != null
              ? `antes ${data.reference_average_correlation.toFixed(2)}`
              : 'fuera de la diagonal'
          }
        />
        <Cifra
          etiqueta="Error de cada celda"
          valor={`±${data.cell_se_z.toFixed(2)}`}
          nota="en z de Fisher"
        />
      </div>

      <p className="mt-3 text-xs leading-relaxed text-slate-400">{data.note}</p>

      {data.delta && (
        <button
          type="button"
          onClick={() => setMostrarCambio((x) => !x)}
          className="mt-3 rounded border border-slate-600 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
        >
          {mostrarCambio ? 'Ver nivel' : 'Ver cambio vs referencia'}
        </button>
      )}

      {/* La matriz. El color codifica el nivel (o el cambio); el borde, que el
          cambio supera el ruido. Nunca las dos cosas en el mismo canal. */}
      <div className="mt-3 overflow-x-auto">
        <table className="border-separate border-spacing-0.5 text-[10px]">
          <thead>
            <tr>
              <th aria-label="activo" className="w-14" />
              {data.labels.map((l) => (
                <th key={l} className="px-1 pb-1 font-mono text-slate-400">
                  {l.slice(0, 4)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.labels.map((fila, i) => (
              <tr key={fila}>
                <th className="pr-1 text-right font-mono font-normal text-slate-400">
                  {fila.slice(0, 5)}
                </th>
                {data.labels.map((col, j) => {
                  const nivel = data.matrix[i][j]
                  const mostrado = cambio ? cambio[i][j] : nivel
                  const notable = i !== j && !!marcas?.[i]?.[j]
                  return (
                    <td key={col} className="p-0">
                      <div
                        title={
                          i === j
                            ? fila
                            : `${fila} / ${col}: ${nivel.toFixed(2)}` +
                              (cambio ? ` (cambio ${mostrado >= 0 ? '+' : ''}${mostrado.toFixed(2)})` : '') +
                              (notable ? ' · cambio mayor que el ruido' : '')
                        }
                        className={[
                          'flex h-6 w-8 items-center justify-center font-mono tabular-nums',
                          cambio ? cellColor(mostrado * 2) : cellColor(nivel),
                          notable ? 'ring-1 ring-fuchsia-300' : '',
                          i === j ? 'opacity-40' : '',
                        ].join(' ')}
                      >
                        {i === j ? '—' : mostrado.toFixed(2)}
                      </div>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Lo que impide sobreleer: cuántas marcas se esperan por azar. */}
      {data.pairs_beyond_noise != null && (
        <p className="mt-2 text-xs text-slate-500">
          <span className="text-fuchsia-300">◻</span>{' '}
          {data.pairs_beyond_noise} parejas cambiaron más que el ruido de estimación, y{' '}
          <strong>por azar se esperan {falsasEsperadas}</strong> de las{' '}
          {(data.labels.length * (data.labels.length - 1)) / 2} comparaciones. La marca
          dirige la mirada; para afirmar que una correlación se ha roto está el detector
          de rupturas, que calibra su umbral.
        </p>
      )}

      <p className="mt-2 text-xs text-slate-600">{data.ordering}</p>
    </div>
  )
}

function Cifra({
  etiqueta,
  valor,
  nota,
}: Readonly<{ etiqueta: string; valor: string; nota: string }>) {
  return (
    <div className="rounded border border-slate-700/60 bg-slate-800/40 p-2">
      <p className="text-[10px] uppercase tracking-wide text-slate-500">{etiqueta}</p>
      <p className="mt-0.5 font-mono text-lg text-slate-100">{valor}</p>
      <p className="text-[10px] text-slate-500">{nota}</p>
    </div>
  )
}
