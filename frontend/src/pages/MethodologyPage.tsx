/**
 * MethodologyPage.tsx — Qué significa cada cifra y dónde deja de valer.
 *
 * Es la página que una due diligence lee primero y la que ningún competidor
 * publica. Su valor no está en explicar las métricas: está en el campo
 * «límites», que dice cuándo NO valen. Por eso el diseño le da el mismo peso
 * visual que a la definición en lugar de esconderlo en letra pequeña.
 *
 * La curva del azar es el centro. Un Sharpe sin el número de configuraciones
 * que costó encontrarlo no es interpretable, y verlo por encima o por debajo de
 * la línea explica eso más rápido que cualquier párrafo.
 */

import { useEffect, useState } from 'react'
import apiClient from '@/services/api'

interface Note {
  key: string
  title: string
  what: string
  assumptions: string
  limits: string
}

interface CurvePoint {
  trials: number
  expected_max_sharpe: number
}

interface Methodology {
  version: string
  golden_rule: string
  notes: Note[]
  disclaimers: string[]
  evidence_available?: boolean
  runs_recorded?: number
  evaluations_total?: number
  effective_trials_total?: number
  champion_name?: string | null
  champion_sharpe?: number | null
  variance_source?: string
  evidence_note?: string
  expected_max_sharpe?: {
    curve: CurvePoint[]
    crossover?: number | null
    variance?: number
  }
}

/**
 * Puntos de la curva en coordenadas de un SVG de 100×100, con el eje X en
 * escala logarítmica.
 *
 * Logarítmica no por estética: la curva del azar crece con la raíz del logaritmo
 * del número de pruebas, así que en escala lineal el 99 % del gráfico sería una
 * línea plana y el detalle interesante —las primeras decenas de pruebas— se
 * aplastaría contra el eje.
 */
export function curveToPoints(curve: CurvePoint[], maxSharpe: number): string {
  if (curve.length === 0 || maxSharpe <= 0) return ''
  const maxLog = Math.log10(Math.max(curve[curve.length - 1].trials, 10))
  return curve
    .map((p) => {
      const x = (Math.log10(Math.max(p.trials, 1)) / maxLog) * 100
      const y = 100 - (p.expected_max_sharpe / maxSharpe) * 100
      return `${x.toFixed(2)},${Math.max(0, Math.min(100, y)).toFixed(2)}`
    })
    .join(' ')
}

/** Escala superior del gráfico: deja aire sobre la mayor de las dos series. */
export function chartCeiling(curve: CurvePoint[], champion: number | null | undefined): number {
  const maxCurve = curve.reduce((m, p) => Math.max(m, p.expected_max_sharpe), 0)
  return Math.max(maxCurve, champion ?? 0, 0.1) * 1.15
}

function NoteCard({ note }: Readonly<{ note: Note }>) {
  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4 space-y-3">
      <h3 className="text-sm font-semibold text-white">{note.title}</h3>
      <div>
        <p className="text-[10px] text-slate-500 uppercase mb-1">Qué mide</p>
        <p className="text-xs text-slate-300 leading-relaxed">{note.what}</p>
      </div>
      <div>
        <p className="text-[10px] text-slate-500 uppercase mb-1">Supuestos</p>
        <p className="text-xs text-slate-400 leading-relaxed">{note.assumptions}</p>
      </div>
      {/* Mismo peso visual que la definición, a propósito: es el campo que casi
          nadie publica y el único que convierte esto en una nota metodológica. */}
      <div className="border-l-2 border-amber-500/50 pl-3">
        <p className="text-[10px] text-amber-400/80 uppercase mb-1">Dónde deja de valer</p>
        <p className="text-xs text-slate-300 leading-relaxed">{note.limits}</p>
      </div>
    </div>
  )
}

export default function MethodologyPage() {
  const [data, setData] = useState<Methodology | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    apiClient.get<Methodology>('/methodology/')
      .then(({ data: d }) => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setData(null) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  if (loading) {
    return <div className="p-6 text-sm text-slate-500">Cargando nota metodológica…</div>
  }
  if (!data) {
    return <div className="p-6 text-sm text-slate-500">No se pudo cargar la nota metodológica.</div>
  }

  const curve = data.expected_max_sharpe?.curve ?? []
  const techo = chartCeiling(curve, data.champion_sharpe)
  const puntos = curveToPoints(curve, techo)
  const yCampeona = data.champion_sharpe != null
    ? 100 - (data.champion_sharpe / techo) * 100
    : null

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-5xl mx-auto">
      <header className="space-y-2">
        <div className="flex items-baseline gap-3 flex-wrap">
          <h1 className="text-xl font-bold text-white">Metodología</h1>
          <span className="text-[11px] font-mono text-slate-500">v{data.version}</span>
        </div>
        <p className="text-sm text-slate-300 leading-relaxed">{data.golden_rule}</p>
      </header>

      {/* ── La curva del azar ─────────────────────────────────────── */}
      {curve.length > 1 && (
        <section className="bg-slate-800/60 border border-slate-700 rounded-xl p-4 space-y-3">
          <div>
            <h2 className="text-sm font-semibold text-white">
              El Sharpe que produce el azar según cuánto busques
            </h2>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed">
              Probar muchas configuraciones garantiza encontrar una buena aunque
              ninguna tenga ventaja real. La línea es el mejor Sharpe esperable
              por puro azar frente al número de pruebas; una campeona por debajo
              de ella no ha demostrado nada salvo que se buscó mucho.
            </p>
          </div>

          <svg viewBox="0 0 100 100" preserveAspectRatio="none"
               className="w-full h-40 bg-slate-900/50 rounded" role="img"
               aria-label="Curva del Sharpe esperable por azar frente al número de pruebas">
            <polyline points={puntos} fill="none" stroke="#f59e0b"
                      strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
            {yCampeona != null && (
              <line x1="0" x2="100" y1={yCampeona} y2={yCampeona}
                    stroke="#22c55e" strokeWidth="1" strokeDasharray="3 2"
                    vectorEffect="non-scaling-stroke" />
            )}
          </svg>

          <div className="flex flex-wrap gap-4 text-[11px]">
            <span className="text-amber-400">— Sharpe del azar</span>
            {data.champion_sharpe != null && (
              <span className="text-emerald-400">
                -- Campeona: {data.champion_sharpe.toFixed(2)}
                {data.champion_name ? ` (${data.champion_name})` : ''}
              </span>
            )}
            {data.expected_max_sharpe?.crossover != null && (
              <span className="text-slate-400">
                El azar la alcanza con {data.expected_max_sharpe.crossover.toLocaleString('es-ES')} pruebas
              </span>
            )}
          </div>

          {data.evidence_available && (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-700">
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Configuraciones evaluadas</p>
                <p className="text-sm font-mono text-white">
                  {(data.evaluations_total ?? 0).toLocaleString('es-ES')}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Pruebas independientes</p>
                <p className="text-sm font-mono text-white">
                  {(data.effective_trials_total ?? 0).toLocaleString('es-ES')}
                </p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Ejecuciones registradas</p>
                <p className="text-sm font-mono text-white">
                  {(data.runs_recorded ?? 0).toLocaleString('es-ES')}
                </p>
              </div>
            </div>
          )}

          {/* La curva usa una varianza supuesta mientras no se persista la
              observada. Presentarla como exacta sería el tipo de cifra que esta
              misma página critica. */}
          {data.evidence_note && (
            <p className="text-[10px] text-slate-500 leading-relaxed">{data.evidence_note}</p>
          )}
        </section>
      )}

      {/* ── Lo que esta plataforma NO afirma ──────────────────────── */}
      <section className="bg-slate-800/40 border border-slate-700 rounded-xl p-4">
        <h2 className="text-sm font-semibold text-white mb-2">Lo que no afirmamos</h2>
        <ul className="space-y-2">
          {data.disclaimers.map((d) => (
            <li key={d} className="text-xs text-slate-300 leading-relaxed flex gap-2">
              <span className="text-slate-600 shrink-0">·</span>
              <span>{d}</span>
            </li>
          ))}
        </ul>
      </section>

      {/* ── Nota por métrica ──────────────────────────────────────── */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-white">Métrica por métrica</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {data.notes.map((n) => <NoteCard key={n.key} note={n} />)}
        </div>
      </section>
    </div>
  )
}
