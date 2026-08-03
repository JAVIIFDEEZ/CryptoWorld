/**
 * components/generator/CpcvDistributionCard.tsx — Distribución CPCV del campeón.
 *
 * El walk-forward recorre UN camino histórico y devuelve un punto. Esta tarjeta
 * muestra la nube de la que ese punto era una sola muestra: el Sharpe de cada
 * combinación de bloques del histórico.
 *
 * La lectura importante es la distancia entre la mediana y el percentil 5. Si
 * el suelo se hunde mientras el máximo brilla, la estrategia depende de que el
 * troceo del histórico la favorezca — el fallo que un walk-forward simple no
 * llega a ver porque nunca prueba los tramos que deja en el train.
 */

import type { CpcvDistribution } from '@/services/strategyGeneratorService'

const W = 520
const H = 92
const PAD = { left: 34, right: 14, top: 20, bottom: 24 }

export default function CpcvDistributionCard({ cpcv, walkForwardSharpe }: Readonly<{
  cpcv: CpcvDistribution
  walkForwardSharpe?: number | null
}>) {
  if (!cpcv || cpcv.n_paths < 2) return null

  const lo = cpcv.sharpe_min ?? 0
  const hi = cpcv.sharpe_max ?? 1
  const p5 = cpcv.sharpe_p5 ?? lo
  const p25 = cpcv.sharpe_p25 ?? lo
  const median = cpcv.sharpe_median ?? 0
  const p75 = cpcv.sharpe_p75 ?? hi
  const positive = cpcv.pct_paths_positive ?? 0

  // Escala que abarca la nube y, si procede, el punto del walk-forward: la
  // comparación entre ambos es lo que hace útil el gráfico.
  const values = [lo, hi, ...(walkForwardSharpe != null ? [walkForwardSharpe] : [])]
  const min = Math.min(...values, 0)
  const max = Math.max(...values, 0)
  const span = Math.max(max - min, 1e-9)
  const x = (v: number) => PAD.left + ((v - min) / span) * (W - PAD.left - PAD.right)

  const solid = p5 > 0
  const midY = PAD.top + (H - PAD.top - PAD.bottom) / 2

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
        <h3 className="text-sm font-semibold text-white">
          Validación cruzada combinatoria
          <span className="ml-2 text-[10px] font-normal text-slate-500">
            {cpcv.n_paths} caminos de {cpcv.blocks_per_path} bloques
          </span>
        </h3>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${
            solid
              ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
              : 'bg-amber-500/15 border-amber-500/30 text-amber-300'
          }`}
        >
          {positive.toFixed(0)}% de caminos en positivo
        </span>
      </div>

      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 my-3 text-[10px]">
        <div>
          <dt className="text-slate-500">Escenario adverso (p5)</dt>
          <dd className={`font-mono text-xs ${solid ? 'text-emerald-300' : 'text-red-300'}`}>
            {p5.toFixed(2)}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Mediana</dt>
          <dd className="text-white font-mono text-xs">{median.toFixed(2)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Rango</dt>
          <dd className="text-slate-300 font-mono text-xs">
            {lo.toFixed(2)} … {hi.toFixed(2)}
          </dd>
        </div>
        <div>
          <dt className="text-slate-500">Walk-forward (1 camino)</dt>
          <dd className="text-sky-300 font-mono text-xs">
            {walkForwardSharpe != null ? walkForwardSharpe.toFixed(2) : '—'}
          </dd>
        </div>
      </dl>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full h-auto min-w-[420px]"
          role="img"
          aria-label={
            `Distribución del Sharpe sobre ${cpcv.n_paths} caminos: mínimo ${lo.toFixed(2)}, ` +
            `percentil 5 ${p5.toFixed(2)}, mediana ${median.toFixed(2)}, máximo ${hi.toFixed(2)}.` +
            (walkForwardSharpe != null
              ? ` El walk-forward de un solo camino da ${walkForwardSharpe.toFixed(2)}.`
              : '')
          }
        >
          {/* Cero de referencia */}
          {min < 0 && max > 0 && (
            <line x1={x(0)} y1={PAD.top - 6} x2={x(0)} y2={H - PAD.bottom}
                  stroke="currentColor" strokeDasharray="3 3" className="text-slate-600" />
          )}

          {/* Bigote min–max */}
          <line x1={x(lo)} y1={midY} x2={x(hi)} y2={midY}
                stroke="currentColor" strokeWidth={1.5} className="text-slate-600" />

          {/* Caja intercuartílica */}
          <rect x={x(p25)} y={midY - 11} width={Math.max(x(p75) - x(p25), 1)} height={22} rx={3}
                className={solid ? 'fill-emerald-500/25' : 'fill-amber-500/25'} />

          {/* Mediana */}
          <line x1={x(median)} y1={midY - 13} x2={x(median)} y2={midY + 13}
                stroke="currentColor" strokeWidth={2} className="text-white" />

          {/* Percentil 5: la cifra honesta */}
          <line x1={x(p5)} y1={midY - 13} x2={x(p5)} y2={midY + 13}
                stroke="currentColor" strokeWidth={2}
                className={solid ? 'text-emerald-400' : 'text-red-400'} />
          <text x={x(p5)} y={midY - 17} textAnchor="middle"
                className={`text-[9px] fill-current ${solid ? 'text-emerald-300' : 'text-red-300'}`}>
            p5
          </text>

          {/* Punto del walk-forward, para ver dónde caía la estimación anterior */}
          {walkForwardSharpe != null && (
            <>
              <circle cx={x(walkForwardSharpe)} cy={midY} r={4} className="fill-current text-sky-400" />
              <text x={x(walkForwardSharpe)} y={H - PAD.bottom + 12} textAnchor="middle"
                    className="text-[9px] fill-current text-sky-300">
                walk-forward
              </text>
            </>
          )}

          <text x={PAD.left} y={PAD.top - 8} className="text-[9px] fill-current text-slate-500">
            Sharpe por camino
          </text>
        </svg>
      </div>

      <p className="text-[10px] text-slate-500 mt-2 leading-relaxed">{cpcv.note}</p>
      {cpcv.purge_note && (
        <p className="text-[10px] text-slate-600 mt-1 leading-relaxed">{cpcv.purge_note}</p>
      )}
    </div>
  )
}
