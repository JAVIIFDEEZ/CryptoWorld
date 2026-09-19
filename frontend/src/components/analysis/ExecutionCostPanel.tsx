/**
 * ExecutionCostPanel.tsx — Qué cuesta ejecutar aquí, a cada tamaño.
 *
 * La pieza que convierte una señal en una decisión. Todo lo demás que muestra
 * esta pantalla —veredictos, estrategias, alertas— es inaccionable mientras no
 * se sepa qué cuesta actuar: un edge de 30 puntos básicos es un negocio a
 * 10.000 USD y una pérdida a 1.000.000 en un activo estrecho, y es el mismo edge.
 *
 * Dos decisiones de presentación, ambas deliberadas:
 *
 *  · **El método se muestra, no se esconde.** El número sale de un modelo de
 *    raíz cuadrada calibrado con volumen y volatilidad, no de leer el libro de
 *    órdenes. Presentarlo sin esa etiqueta lo convertiría en un dato aparente, y
 *    una estimación disfrazada de medición es peor que no tenerla.
 *  · **El techo va arriba del todo.** «Hasta dónde puedo» es más accionable que
 *    «cuánto me cuesta», y es lo primero que alguien necesita saber.
 */

import { useEffect, useState } from 'react'
import { analysisService, type ExecutionCost } from '@/services/analysisService'

export function compactUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(1)}M`
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(0)}K`
  return `$${n.toFixed(0)}`
}

/**
 * Color del coste según su magnitud en puntos básicos.
 *
 * Los cortes no son estéticos: 10 bps es el entorno de una comisión normal y no
 * cambia ninguna decisión; a partir de 50 bps el coste empieza a comerse
 * cualquier edge realista de esta plataforma, y ahí es donde el usuario tiene
 * que mirar dos veces.
 */
export function costClass(bps: number): string {
  if (bps < 10) return 'text-emerald-300'
  if (bps < 50) return 'text-amber-300'
  return 'text-red-300'
}

export default function ExecutionCostPanel({ symbol }: Readonly<{ symbol: string }>) {
  const [data, setData] = useState<ExecutionCost | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    analysisService.getExecutionCost(symbol)
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setData({ available: false, steps: [] }) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol])

  if (loading) {
    return (
      <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
        <div className="text-xs text-slate-500">Calculando coste de ejecución…</div>
      </div>
    )
  }
  if (!data?.available) {
    return (
      <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
        <div className="text-xs text-slate-500">
          Sin histórico diario suficiente de {symbol}: el coste de ejecución no se
          puede estimar. No se muestra un cero porque un cero se leería como
          «ejecutar aquí es gratis».
        </div>
      </div>
    )
  }

  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4 space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-white">
          Coste de ejecución ·{' '}
          <span className="font-mono text-slate-400">{data.symbol ?? symbol}</span>
        </h3>
        <p className="text-[11px] text-slate-400">
          Hasta{' '}
          <span className="font-mono text-slate-200">
            {compactUsd(data.max_executable_usd)}
          </span>{' '}
          por orden
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="text-slate-500 text-left">
              <th className="font-normal pb-1">Tamaño</th>
              <th className="font-normal pb-1 text-right">% del día</th>
              <th className="font-normal pb-1 text-right">Coste</th>
              <th className="font-normal pb-1 text-right">En dinero</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {data.steps.map((s) => (
              <tr
                key={s.notional_usd}
                className={s.feasible ? '' : 'opacity-45'}
                title={s.feasible ? undefined
                  : 'A este tamaño la orden no entra en un día sin mover el mercado'}
              >
                <td className="py-0.5 text-slate-300">{compactUsd(s.notional_usd)}</td>
                <td className="py-0.5 text-right text-slate-400">
                  {s.participation_pct < 0.01 ? '<0,01' : s.participation_pct.toFixed(2)}%
                </td>
                <td className={`py-0.5 text-right ${costClass(s.impact_bps)}`}>
                  {s.impact_bps.toFixed(1)} bps
                </td>
                <td className="py-0.5 text-right text-slate-400">
                  {compactUsd(s.impact_usd)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Sin esta línea el número parece una lectura de profundidad. Lo es de un
          modelo, y el usuario tiene derecho a saber cuál y con qué se calibró. */}
      <p className="text-[10px] text-slate-500 leading-relaxed">
        Modelo de raíz cuadrada calibrado con {data.window_days ?? 30} días de
        volumen ({compactUsd(data.adv_usd)}/día) y volatilidad diaria
        {' '}({((data.daily_volatility ?? 0) * 100).toFixed(1)}%).{' '}
        <strong>No es una lectura del libro de órdenes</strong>: es el coste
        esperado de una orden típica en condiciones típicas, y en un momento de
        estrés será mayor. Las filas atenuadas superan el
        {' '}{data.max_participation_pct ?? 10}% del volumen diario.
      </p>
    </div>
  )
}
