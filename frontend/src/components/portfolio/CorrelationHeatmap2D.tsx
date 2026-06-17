/**
 * components/portfolio/CorrelationHeatmap2D.tsx — Mapa de calor de correlación 2D.
 *
 * Cuadrícula de celdas coloreadas por la correlación 7d entre holdings.
 * Alternativa 2D / fallback sin WebGL de la matriz 3D.
 */

import { correlationColor, type CorrelationData } from './portfolioViz'

export default function CorrelationHeatmap2D({ data }: Readonly<{ data: CorrelationData }>) {
  const { symbols, matrix } = data
  if (symbols.length < 2) {
    return <div className="text-slate-500 text-sm text-center py-16">Necesitas al menos 2 posiciones con histórico.</div>
  }
  return (
    <div className="rounded-xl border border-slate-700/70 bg-slate-900/40 p-4 overflow-auto">
      <table className="border-separate" style={{ borderSpacing: 2 }}>
        <thead>
          <tr>
            <th />
            {symbols.map((s) => (
              <th key={s} className="text-[10px] text-slate-400 font-medium px-1 pb-1">{s}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {symbols.map((row, i) => (
            <tr key={row}>
              <td className="text-[10px] text-slate-400 font-medium pr-2 text-right">{row}</td>
              {symbols.map((col, j) => {
                const c = matrix[i][j]
                return (
                  <td key={col}
                    className="w-10 h-10 text-center text-[10px] font-mono rounded"
                    style={{ background: correlationColor(c), color: 'rgba(255,255,255,0.9)' }}
                    title={`${row} / ${col}: ${c.toFixed(2)}`}
                  >
                    {c.toFixed(1)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[10px] text-slate-500 mt-3">
        <span className="text-blue-300">Azul</span> = baja correlación (diversifica) ·
        <span className="text-red-300"> rojo</span> = alta (riesgo concentrado).
      </p>
    </div>
  )
}
