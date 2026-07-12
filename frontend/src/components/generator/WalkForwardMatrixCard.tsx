/**
 * components/generator/WalkForwardMatrixCard.tsx — Matriz walk-forward del campeón.
 *
 * Radiografía de estabilidad temporal (estilo StrategyQuant): cada fila re-ejecuta
 * el walk-forward con un troceo distinto y cada celda es el Sharpe OOS de un
 * tramo. Estable = mayoría de celdas positivas con cualquier partición; una fila
 * "bonita" aislada delata ajuste a un periodo concreto.
 */

import type { GenerationReport } from '@/services/strategyGeneratorService'

type Matrix = NonNullable<GenerationReport['walk_forward_matrix']>

function cellColor(sharpe: number): string {
  // Estado (ganancia/pérdida) con intensidad por magnitud — no es identidad
  if (sharpe >= 1) return 'bg-emerald-500/50 text-emerald-100'
  if (sharpe > 0) return 'bg-emerald-500/25 text-emerald-200'
  if (sharpe > -1) return 'bg-red-500/25 text-red-200'
  return 'bg-red-500/50 text-red-100'
}

export default function WalkForwardMatrixCard({ matrix, championDesc }: Readonly<{
  matrix: Matrix
  championDesc: string
}>) {
  const stable = matrix.stability_score >= 0.7
  const maxFolds = Math.max(...matrix.rows.map((r) => r.folds.length), 1)

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
        <h3 className="text-sm font-semibold text-white">
          Matriz walk-forward del campeón
          <span className="ml-2 text-[10px] font-normal text-slate-500">estabilidad temporal bajo distintos troceos</span>
        </h3>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${
            stable
              ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
              : 'bg-amber-500/15 border-amber-500/30 text-amber-300'
          }`}
        >
          {matrix.positive_folds}/{matrix.total_folds} tramos positivos · {Math.round(matrix.stability_score * 100)}%
        </span>
      </div>
      <p className="text-[10px] text-slate-500 mb-3 truncate" title={championDesc}>{championDesc}</p>

      <div className="overflow-x-auto">
        <table className="w-full text-[10px] border-separate" style={{ borderSpacing: 2 }}>
          <thead>
            <tr className="text-slate-500">
              <th className="text-left font-normal pr-2 whitespace-nowrap">Troceo</th>
              {Array.from({ length: maxFolds }, (_, i) => (
                <th key={i} className="font-normal font-mono">t{i + 1}</th>
              ))}
              <th className="font-normal pl-2 whitespace-nowrap">media OOS</th>
            </tr>
          </thead>
          <tbody>
            {matrix.rows.map((r) => (
              <tr key={r.n_splits}>
                <td className="pr-2 text-slate-400 whitespace-nowrap">{r.n_splits} tramos</td>
                {Array.from({ length: maxFolds }, (_, i) => {
                  const v = r.folds[i]
                  if (v == null) return <td key={i} />
                  return (
                    <td
                      key={i}
                      className={`text-center font-mono rounded px-1.5 py-1 ${cellColor(v)}`}
                      title={`Sharpe OOS del tramo ${i + 1} con ${r.n_splits} particiones: ${v.toFixed(3)}`}
                    >
                      {v.toFixed(1)}
                    </td>
                  )
                })}
                <td className={`pl-2 text-center font-mono ${r.mean_oos_sharpe >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {r.mean_oos_sharpe.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[9px] text-slate-600 mt-2">{matrix.note}</p>
    </div>
  )
}
