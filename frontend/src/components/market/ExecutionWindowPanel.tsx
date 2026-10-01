/**
 * ExecutionWindowPanel.tsx — ¿Ejecuto ahora o espero?
 *
 * La otra mitad del problema. Todo lo demás que muestra esta plataforma trabaja
 * sobre QUÉ comprar; esto decide cuánto de ese edge llega a la cuenta, porque una
 * ventaja de 30 puntos básicos se la come un diferencial abierto y un libro fino.
 * Las mesas institucionales tienen herramientas de pre-trade para esto y el retail
 * no tiene ninguna.
 *
 * Cuatro decisiones de presentación, todas deliberadas:
 *
 *  · **El veredicto va primero y con sus razones debajo.** Un semáforo sin motivos
 *    es un oráculo, y un oráculo no se puede contradecir. Las razones son el
 *    producto; el color es el índice.
 *  · **Si no hay base horaria, NO se pinta semáforo horario.** Cuando el estudio de
 *    estacionalidad no encuentra estructura de hora de la semana, la rejilla sale
 *    en gris y el panel lo dice. Pintar un degradado sobre un número sin
 *    significado es el fallo que este panel existe para no cometer.
 *  · **Las casillas que no sobreviven a la corrección por multiplicidad se pintan
 *    distinto** —sin borde— porque son pistas y no hechos. Son 168 contrastes y al
 *    5 % ocho saldrían por azar.
 *  · **Nunca se habla de dirección.** Una hora tranquila no es una hora en la que
 *    suba: es una en la que cuesta menos entrar. El texto no contiene «comprar» ni
 *    «subirá» en ninguna rama, y hay un test que lo fija.
 */

import { useEffect, useMemo, useState } from 'react'
import {
  marketService,
  type ExecutionWindow,
  type ExecutionWindowVerdict,
} from '@/services/marketService'

const DIAS = ['lun', 'mar', 'mié', 'jue', 'vie', 'sáb', 'dom'] as const

/**
 * Estilo de cada veredicto.
 *
 * `EL_TAMANO_MANDA` es ámbar y no rojo a propósito: no dice que el momento sea
 * malo, dice que la pregunta es otra —el tamaño— y que esperar no arregla nada.
 */
export function verdictStyle(v: ExecutionWindowVerdict): {
  label: string
  cls: string
  dot: string
} {
  switch (v) {
    case 'FAVORABLE':
      return { label: 'Momento favorable', cls: 'text-emerald-300 border-emerald-500/40', dot: 'bg-emerald-400' }
    case 'NEUTRAL':
      return { label: 'Sin nada destacable', cls: 'text-slate-300 border-slate-600/50', dot: 'bg-slate-400' }
    case 'DESFAVORABLE':
      return { label: 'Momento caro', cls: 'text-amber-300 border-amber-500/40', dot: 'bg-amber-400' }
    case 'ESPERAR':
      return { label: 'Esperar', cls: 'text-red-300 border-red-500/40', dot: 'bg-red-400' }
    case 'EL_TAMANO_MANDA':
      return { label: 'El tamaño manda', cls: 'text-amber-300 border-amber-500/40', dot: 'bg-amber-400' }
    case 'SIN_BASE_HORARIA':
      return { label: 'Sin base horaria', cls: 'text-slate-400 border-slate-600/50', dot: 'bg-slate-500' }
    default:
      return { label: 'Sin datos', cls: 'text-slate-400 border-slate-600/50', dot: 'bg-slate-600' }
  }
}

/**
 * Color de una casilla por su actividad relativa.
 *
 * `null` —sin base— tiene que verse distinto de 1,0 —actividad media—: lo primero
 * es «no se sabe» y lo segundo es «es normal», y confundirlos es exactamente el
 * error que este panel evita.
 */
export function activityColor(relative: number | null): string {
  if (relative == null || !Number.isFinite(relative)) return 'bg-slate-800/60'
  if (relative >= 1.6) return 'bg-red-600/80'
  if (relative >= 1.25) return 'bg-orange-500/70'
  if (relative >= 1.05) return 'bg-amber-500/45'
  if (relative >= 0.85) return 'bg-slate-600/50'
  if (relative >= 0.65) return 'bg-sky-600/45'
  return 'bg-blue-600/60'
}

/** Texto de la cuenta atrás hasta la ventana propuesta. */
export function countdown(hours: number): string {
  if (!Number.isFinite(hours) || hours <= 0) return 'ahora'
  if (hours < 1) return `${Math.round(hours * 60)} min`
  if (hours < 24) return `${Math.round(hours)} h`
  const d = Math.floor(hours / 24)
  const h = Math.round(hours % 24)
  return h ? `${d} d ${h} h` : `${d} d`
}

/** Importancia → color del punto del evento. */
export function importanceDot(importance: string): string {
  if (importance === 'alta') return 'bg-red-400'
  if (importance === 'media') return 'bg-amber-400'
  return 'bg-slate-500'
}

export default function ExecutionWindowPanel({
  symbol,
  notional = 10_000,
}: Readonly<{ symbol: string; notional?: number }>) {
  const [data, setData] = useState<ExecutionWindow | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cargando, setCargando] = useState(true)

  useEffect(() => {
    let vivo = true
    setCargando(true)
    setError(null)
    marketService
      .getExecutionWindow(symbol, { notional })
      .then((d) => {
        if (vivo) setData(d)
      })
      .catch(() => {
        if (vivo) setError('No se pudo calcular la ventana de ejecución.')
      })
      .finally(() => {
        if (vivo) setCargando(false)
      })
    return () => {
      vivo = false
    }
  }, [symbol, notional])

  /** Actividad relativa por casilla, derivada del bloque de estacionalidad. */
  const relativa = useMemo(() => {
    const medias = data?.seasonality?.mean_abs_return
    if (!medias || medias.length !== 168 || !data?.seasonality_usable) return null
    const validas = medias.filter((m): m is number => m != null)
    if (!validas.length) return null
    const centro = validas.reduce((a, b) => a + b, 0) / validas.length
    if (centro <= 0) return null
    return medias.map((m) => (m == null ? null : m / centro))
  }, [data])

  const establecidas = useMemo(() => {
    const s = new Set<number>()
    data?.hours.forEach((h) => {
      if (h.established) s.add(h.cell)
    })
    return s
  }, [data])

  if (cargando) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-900/50 p-4">
        <p className="text-sm text-slate-400">Calculando la ventana de ejecución…</p>
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

  const v = verdictStyle(data.verdict)
  const ahora = data.now
  const ventana = data.best_window

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/50 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-200">
            Ventana de ejecución · {data.symbol}
          </h3>
          <p className="mt-0.5 text-xs text-slate-500">
            a {data.notional_usd.toLocaleString('es-ES')} USD · {data.interval} ·{' '}
            {data.candles?.toLocaleString('es-ES') ?? '—'} velas del almacén propio
          </p>
        </div>
        <span
          className={`inline-flex items-center gap-2 rounded border px-2 py-1 text-xs font-medium ${v.cls}`}
        >
          <span className={`h-2 w-2 rounded-full ${v.dot}`} aria-hidden />
          {v.label}
        </span>
      </div>

      {data.verdict === 'SIN_DATOS' ? (
        <p className="mt-3 text-sm text-slate-400">{data.note}</p>
      ) : (
        <>
          {/* Las razones son el producto. El color es solo el índice. */}
          <ul className="mt-3 space-y-1.5">
            {data.reasons.map((r) => (
              <li key={r} className="flex gap-2 text-xs leading-relaxed text-slate-300">
                <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-slate-500" aria-hidden />
                <span>{r}</span>
              </li>
            ))}
          </ul>

          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <Cifra
              etiqueta="Ahora"
              valor={
                ahora ? `${ahora.day} ${String(ahora.hour_utc).padStart(2, '0')}:00` : '—'
              }
              nota={
                ahora?.activity != null
                  ? `${ahora.activity.toFixed(2)}× el movimiento medio`
                  : 'sin base horaria'
              }
            />
            <Cifra
              etiqueta="Ventana más barata"
              valor={ventana ? `en ${countdown(ventana.in_hours)}` : '—'}
              nota={
                ventana
                  ? `${ventana.day} ${String(ventana.hour_utc).padStart(2, '0')}:00 UTC · ${ventana.length_hours} h`
                  : 'sin horizonte suficiente'
              }
            />
            <Cifra
              etiqueta="Impacto a tu tamaño"
              valor={
                data.cost_bps_first_step != null
                  ? `${data.cost_bps_first_step.toFixed(0)} bps`
                  : '—'
              }
              nota={
                data.cost_bps_first_step != null
                  ? 'modelo, no libro de órdenes'
                  : 'no estimable sin histórico diario'
              }
            />
          </div>

          {/* El reloj semanal. Es la pieza que se mira, y lo primero que hace es
              declarar si significa algo. */}
          <div className="mt-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Reloj de la semana · actividad por hora UTC
              </h4>
              {!data.seasonality_usable && (
                <span className="text-[10px] text-slate-500">
                  en gris: sin estructura horaria detectada
                </span>
              )}
            </div>
            <WeekClock
              relativa={relativa}
              establecidas={establecidas}
              ahoraCell={ahora?.cell ?? null}
              ventanaCells={
                ventana
                  ? data.hours
                      .filter(
                        (h) =>
                          h.hour_ms >= new Date(ventana.from).getTime() &&
                          h.hour_ms < new Date(ventana.to).getTime(),
                      )
                      .map((h) => h.cell)
                  : []
              }
            />
          </div>

          {/* Eventos. El calendario solo cubre lo derivable por regla, y eso se
              dice: la ausencia no es garantía de que no haya nada previsto. */}
          {data.upcoming_events.length > 0 && (
            <div className="mt-4">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Próximos eventos programados
              </h4>
              <ul className="mt-2 space-y-1">
                {data.upcoming_events.slice(0, 6).map((e) => (
                  <li
                    key={`${e.key}-${e.at_ms}`}
                    className="flex items-center gap-2 text-xs text-slate-300"
                  >
                    <span
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${importanceDot(e.importance)}`}
                      aria-hidden
                    />
                    <span className="font-mono tabular-nums text-slate-400">
                      {countdown(e.in_hours).padStart(6, ' ')}
                    </span>
                    <span className="font-medium">{e.key}</span>
                    <span className="text-slate-500">({e.importance})</span>
                  </li>
                ))}
              </ul>
              {data.calendar_underivable?.length ? (
                <p className="mt-2 text-[10px] text-slate-600">
                  No derivable por regla y por tanto ausente:{' '}
                  {data.calendar_underivable.join(', ')}. Que no haya eventos en la
                  lista no significa que no haya nada previsto.
                </p>
              ) : null}
            </div>
          )}

          {data.limits && (
            <details className="mt-4">
              <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-300">
                Qué NO dice esto
              </summary>
              <p className="mt-2 whitespace-pre-line text-[11px] leading-relaxed text-slate-500">
                {data.limits}
              </p>
            </details>
          )}
        </>
      )}
    </div>
  )
}

/** Rejilla 7×24. El borde marca las casillas que sobreviven a la corrección. */
function WeekClock({
  relativa,
  establecidas,
  ahoraCell,
  ventanaCells,
}: Readonly<{
  relativa: (number | null)[] | null
  establecidas: Set<number>
  ahoraCell: number | null
  ventanaCells: number[]
}>) {
  const enVentana = useMemo(() => new Set(ventanaCells), [ventanaCells])
  return (
    <div className="mt-2 overflow-x-auto">
      <table className="border-separate border-spacing-[2px] text-[9px]">
        <thead>
          <tr>
            <th aria-label="día" className="w-8" />
            {Array.from({ length: 24 }, (_, h) => (
              <th key={h} className="pb-0.5 font-mono font-normal text-slate-500">
                {h % 3 === 0 ? String(h).padStart(2, '0') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {DIAS.map((dia, d) => (
            <tr key={dia}>
              <th className="pr-1 text-right font-mono text-[9px] font-normal text-slate-500">
                {dia}
              </th>
              {Array.from({ length: 24 }, (_, h) => {
                const cell = d * 24 + h
                const rel = relativa ? relativa[cell] : null
                const esAhora = cell === ahoraCell
                const esVentana = enVentana.has(cell)
                const descripcion =
                  `${dia} ${String(h).padStart(2, '0')}:00 UTC` +
                  (rel != null
                    ? ` · ${rel.toFixed(2)}× el movimiento medio`
                    : ' · sin base') +
                  (establecidas.has(cell) ? ' · establecida' : '') +
                  (esAhora ? ' · AHORA' : '') +
                  (esVentana ? ' · ventana propuesta' : '')
                return (
                  <td key={h} className="p-0">
                    {/* La casilla no lleva texto, así que sin `aria-label` un lector
                        de pantalla no obtendría nada: 168 celdas mudas. El `title`
                        solo cubre el ratón. */}
                    <div
                      role="img"
                      aria-label={descripcion}
                      title={descripcion}
                      className={[
                        'h-4 w-4 rounded-sm',
                        activityColor(rel),
                        establecidas.has(cell) ? 'ring-1 ring-fuchsia-300/70' : '',
                        esVentana ? 'outline outline-1 outline-emerald-300' : '',
                        esAhora ? 'ring-2 ring-white' : '',
                      ].join(' ')}
                    />
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1.5 text-[10px] text-slate-500">
        <span className="text-white">▢</span> ahora ·{' '}
        <span className="text-emerald-300">▢</span> ventana propuesta ·{' '}
        <span className="text-fuchsia-300">▢</span> casilla que sobrevive a la
        corrección por multiplicidad (las demás son pistas, no hechos)
      </p>
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
      <p className="mt-0.5 font-mono text-base text-slate-100">{valor}</p>
      <p className="text-[10px] text-slate-500">{nota}</p>
    </div>
  )
}
