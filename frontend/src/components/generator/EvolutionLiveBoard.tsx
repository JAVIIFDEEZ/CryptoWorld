/**
 * components/generator/EvolutionLiveBoard.tsx — Evolución genética en vivo.
 *
 * Cuadro de mando que se pinta MIENTRAS el generador evoluciona: convergencia
 * del fitness por generación (mejor vs. media), curvas de equity de los mejores
 * candidatos de la generación actual (solo zona de evolución: el holdout jamás
 * se muestra), estado de las islas/hipermutación y avance del gating de
 * robustez. Se alimenta del snapshot `progress` que publica la tarea.
 */

import { useMemo, useRef, useState } from 'react'
import Sparkline from '@/components/ui/Sparkline'
import type { EvolutionProgress, GenerationHistoryPoint } from '@/services/strategyGeneratorService'

// ── Gráfica de convergencia (mejor sólido / media discontinua) ──────

const W = 640
const H = 200
const PAD = { top: 16, right: 78, bottom: 24, left: 46 }

/** Separación mínima entre dos etiquetas directas para que no se pisen (px SVG). */
const LABEL_GAP = 11

/**
 * Dominio vertical ROBUSTO para la convergencia.
 *
 * El problema se ve en cuanto arranca una ejecución: en la generación 0 la
 * población está llena de genomas degenerados que el fitness penaliza a −65,
 * mientras que todo lo interesante vive entre 0 y 2. Con un dominio ingenuo
 * [min, max], ese único punto se lleva el 97 % del alto y las dos series quedan
 * pegadas al borde superior como líneas planas — que es justo lo que no se
 * puede leer.
 *
 * La regla tiene que distinguir dos cosas que se parecen: una media BAJA (la
 * población todavía no ha alcanzado al mejor — información útil) y una media
 * CATASTRÓFICA (genomas degenerados con la penalización máxima — ruido de
 * arranque). Recortar la primera perdería la mitad del gráfico.
 *
 * Se usa la **valla de Tukey** (Q1 − 1,5·IQR), que es el criterio estándar de
 * atípicos y decide con la dispersión de los propios datos. La alternativa
 * evidente —un múltiplo del recorrido de la serie del mejor— falla justo cuando
 * la búsqueda converge pronto: ahí el mejor apenas se mueve, el recorrido tiende
 * a cero y el suelo acaba pegado a la línea, recortando medias perfectamente
 * normales.
 *
 * Lo que cae fuera de la valla se marca, no se esconde.
 */
function quantile(sorted: number[], q: number): number {
  if (sorted.length === 1) return sorted[0]
  const pos = (sorted.length - 1) * q
  const lo = Math.floor(pos)
  const hi = Math.ceil(pos)
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo)
}

export function domainOf(history: GenerationHistoryPoint[]) {
  const all = history.flatMap((h) => [h.best, h.mean])
  const sorted = [...all].sort((a, b) => a - b)
  const hi = sorted[sorted.length - 1]
  const trueLo = sorted[0]

  const iqr = quantile(sorted, 0.75) - quantile(sorted, 0.25)
  const fence = quantile(sorted, 0.25) - 1.5 * iqr

  const clipped = iqr > 1e-9 && trueLo < fence
  const lo = clipped ? fence : trueLo - 0.05 * Math.abs(hi - trueLo)
  return { lo, hi: hi > lo ? hi : lo + 1, clipped, trueLo }
}

function ConvergenceChart({ history }: Readonly<{ history: GenerationHistoryPoint[] }>) {
  const [hover, setHover] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const { pts, yMin, yMax, clipped, trueLo, yOf } = useMemo(() => {
    const { lo, hi, clipped: wasClipped, trueLo: worst } = domainOf(history)
    const span = hi - lo || 1
    const x = (g: number) => PAD.left + (history.length < 2 ? 0 : (g / (history.length - 1)) * (W - PAD.left - PAD.right))
    const y = (v: number) => {
      const c = Math.min(hi, Math.max(lo, v))
      return H - PAD.bottom - ((c - lo) / span) * (H - PAD.top - PAD.bottom)
    }
    return {
      pts: history.map((h, i) => ({
        x: x(i), yBest: y(h.best), yMean: y(h.mean), h,
        meanClipped: h.mean < lo - 1e-9,
      })),
      yMin: lo, yMax: hi, clipped: wasClipped, trueLo: worst, yOf: y,
    }
  }, [history])

  if (history.length < 2) {
    return (
      <div className="h-[200px] flex items-center justify-center text-xs text-slate-500">
        Esperando las primeras generaciones…
      </div>
    )
  }

  const line = (key: 'yBest' | 'yMean') => pts.map((p) => `${p.x.toFixed(1)},${p[key].toFixed(1)}`).join(' ')
  const hovered = hover != null ? pts[hover] : null
  const last = pts[pts.length - 1]
  const tail = history[history.length - 1]

  // Etiquetas directas que NO se pisan. Cuando la media alcanza al mejor —que es
  // el final feliz de una convergencia— las dos caían en la misma altura y se
  // superponían hasta quedar ilegibles. Aquí se separan lo justo, con la del
  // mejor arriba porque es la serie principal.
  const labelBest = Math.max(PAD.top + 4, Math.min(last.yBest, H - PAD.bottom - LABEL_GAP))
  const labelMean = Math.max(labelBest + LABEL_GAP, Math.min(last.yMean, H - PAD.bottom))

  // Línea del cero: en un fitness construido sobre el Sharpe fuera de muestra,
  // cruzarla es la diferencia entre buscar algo y buscar nada.
  const showZero = yMin < 0 && yMax > 0

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const px = ((e.clientX - rect.left) / rect.width) * W
    const idx = Math.round(((px - PAD.left) / (W - PAD.left - PAD.right)) * (pts.length - 1))
    setHover(Math.max(0, Math.min(pts.length - 1, idx)))
  }

  return (
    <div className="relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label="Convergencia del fitness por generación"
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {/* Rejilla: mín / medio / máx */}
        {[yMax, (yMax + yMin) / 2, yMin].map((v) => (
          <g key={v}>
            <line
              x1={PAD.left} x2={W - PAD.right} y1={yOf(v)} y2={yOf(v)}
              stroke="#334155" strokeWidth={0.6} strokeDasharray="2 4"
            />
            <text x={PAD.left - 6} y={yOf(v) + 3} textAnchor="end" fontSize={9} className="fill-slate-500 font-mono">
              {v.toFixed(2)}
            </text>
          </g>
        ))}

        {showZero && (
          <line
            x1={PAD.left} x2={W - PAD.right} y1={yOf(0)} y2={yOf(0)}
            stroke="#f59e0b" strokeWidth={0.8} strokeOpacity={0.45}
          />
        )}

        {/* Eje X: generaciones */}
        <text x={PAD.left} y={H - 7} fontSize={9} className="fill-slate-500 font-mono">gen 0</text>
        <text x={W - PAD.right} y={H - 7} textAnchor="end" fontSize={9} className="fill-slate-500 font-mono">
          gen {history.length - 1}
        </text>

        {/* Media de la población: línea de referencia discontinua */}
        <polyline points={line('yMean')} fill="none" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="5 4" strokeOpacity={0.8} />
        {/* Mejor de la generación: serie principal */}
        <polyline points={line('yBest')} fill="none" stroke="#60a5fa" strokeWidth={2} strokeLinejoin="round" />

        {/* Marcas de lo que quedó fuera de escala: se señala, no se esconde. */}
        {pts.filter((p) => p.meanClipped).map((p) => (
          <path
            key={p.x}
            d={`M ${p.x - 3} ${H - PAD.bottom - 3} L ${p.x + 3} ${H - PAD.bottom - 3} L ${p.x} ${H - PAD.bottom + 1} Z`}
            fill="#94a3b8" fillOpacity={0.7}
          />
        ))}

        {/* Etiquetas directas al final de cada serie */}
        <text x={last.x + 6} y={labelBest + 3} fontSize={9} className="fill-slate-200 font-medium">
          mejor {tail.best.toFixed(2)}
        </text>
        <text x={last.x + 6} y={labelMean + 3} fontSize={9} className="fill-slate-400">
          media {tail.mean.toFixed(2)}
        </text>

        {/* Capa de hover: crosshair + puntos */}
        {hovered && (
          <g>
            <line x1={hovered.x} x2={hovered.x} y1={PAD.top} y2={H - PAD.bottom} stroke="#64748b" strokeWidth={0.8} />
            <circle cx={hovered.x} cy={hovered.yBest} r={3.5} fill="#60a5fa" stroke="#0f172a" strokeWidth={1.5} />
            <circle cx={hovered.x} cy={hovered.yMean} r={3} fill="#94a3b8" stroke="#0f172a" strokeWidth={1.5} />
          </g>
        )}
      </svg>

      {/* Tooltip */}
      {hovered && (
        <div
          className="absolute top-0 pointer-events-none bg-slate-900/95 border border-slate-600 rounded-lg px-2.5 py-1.5 text-[10px] leading-4 shadow-xl"
          style={{ left: `${Math.min(82, (hovered.x / W) * 100)}%` }}
        >
          <p className="text-slate-400 font-medium">Generación {hovered.h.generation}</p>
          <p className="text-slate-200 font-mono">mejor {hovered.h.best.toFixed(3)}</p>
          <p className="text-slate-400 font-mono">media {hovered.h.mean.toFixed(3)}</p>
          <p className="text-slate-500 font-mono">{hovered.h.diversity} genomas únicos</p>
        </div>
      )}

      {/* Leyenda */}
      <div className="flex flex-wrap items-center gap-4 mt-1 text-[10px] text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-4 h-0.5 bg-blue-400 rounded" /> mejor de la generación
        </span>
        <span className="flex items-center gap-1.5">
          <svg width="16" height="2"><line x1="0" x2="16" y1="1" y2="1" stroke="#94a3b8" strokeWidth="2" strokeDasharray="4 3" /></svg>
          media de la población
        </span>
        {clipped && (
          <span
            className="text-slate-500"
            title={'La escala la fija la serie del mejor de cada generación. Los genomas '
                 + 'degenerados de las primeras generaciones caen mucho más abajo y, si '
                 + 'marcaran el suelo, aplastarían todo lo demás contra el borde superior.'}
          >
            ▾ fuera de escala (mín. real {trueLo.toFixed(1)})
          </span>
        )}
      </div>
    </div>
  )
}

// ── Tarjetas de candidatas con su curva de equity ────────────────────

function CandidateGrid({ top }: Readonly<{ top: EvolutionProgress['top'] }>) {
  if (!top?.length) return null
  return (
    <div className="grid grid-cols-2 lg:grid-cols-3 gap-2">
      {top.map((c, i) => {
        const up = (c.total_return_pct ?? 0) >= 0
        const badge = c.direction === 'short' || c.direction === 'both' ? c.direction : null
        return (
          <div
            key={c.hash}
            className="bg-slate-900/50 border border-slate-700/60 rounded-lg p-2.5 transition-all duration-300"
            title={c.description}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[9px] uppercase tracking-wide text-slate-500">#{i + 1} · fitness</span>
              <div className="flex items-center gap-1.5">
                {badge && (
                  <span
                    className={`text-[8px] uppercase px-1 py-px rounded border ${
                      badge === 'short'
                        ? 'bg-rose-500/15 border-rose-500/30 text-rose-300'
                        : 'bg-amber-500/15 border-amber-500/30 text-amber-300'
                    }`}
                    title={badge === 'short' ? 'Opera en corto' : 'Opera los dos lados'}
                  >
                    {badge === 'short' ? 'corto' : 'L+C'}
                  </span>
                )}
                <span
                  className="text-[11px] font-mono font-bold text-blue-300"
                  title="Fitness: Sharpe fuera de muestra del walk-forward, penalizado por sobreajuste, rotación y bajo nº de operaciones. Es lo único que ordena la búsqueda."
                >
                  {c.fitness.toFixed(3)}
                </span>
              </div>
            </div>
            <Sparkline data={c.equity} width={180} height={36} className="w-full mt-1" color={up ? '#34d399' : '#f87171'} />
            <div className="flex items-center justify-between mt-1 text-[9px] font-mono">
              <span
                className={up ? 'text-emerald-400/80' : 'text-red-400/80'}
                title="Retorno DENTRO DE MUESTRA sobre la zona de evolución: los mismos datos con los que se seleccionó esta estrategia. No es una expectativa — es el número que el gating existe para no creerse."
              >
                {up ? '+' : ''}{c.total_return_pct?.toFixed(1)}% <span className="text-slate-600">is</span>
              </span>
              <span className="text-slate-500">{c.n_trades} ops</span>
              <span className="text-slate-600">DD {c.max_drawdown_pct?.toFixed(0)}%</span>
            </div>
            <p className="text-[9px] text-slate-500 truncate mt-1">{c.description}</p>
          </div>
        )
      })}
    </div>
  )
}

// ── Cuadro de mando principal ────────────────────────────────────────

export default function EvolutionLiveBoard({ progress }: Readonly<{ progress: EvolutionProgress }>) {
  const isGating = progress.phase === 'gating'
  const isRefining = progress.phase === 'refining'
  const isCross = progress.phase === 'cross_validating'
  const gen = progress.generation ?? Math.max(0, progress.history.length - 1)
  const total = progress.generations_total ?? progress.history.length
  const islands = progress.island_best?.length ?? 0
  const phaseLabel = isGating ? 'Gating de robustez'
    : isRefining ? 'Refinando finalistas'
    : isCross ? 'Validación multi-activo'
    : `Generación ${gen + 1}/${total}`

  return (
    <div className="space-y-4">
      {/* Chips de estado del motor */}
      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <span className="px-2 py-0.5 rounded-full bg-blue-500/15 border border-blue-500/30 text-blue-300 font-medium">
          {phaseLabel}
        </span>
        {(progress.restarts_total ?? 1) > 1 && (
          <span className="px-2 py-0.5 rounded-full bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 font-medium">
            Ronda {progress.restart}/{progress.restarts_total} · búsqueda hasta objetivo
          </span>
        )}
        {progress.evaluations != null && (
          <span className="px-2 py-0.5 rounded-full bg-slate-700/60 text-slate-300 font-mono">
            {progress.evaluations} genomas evaluados
          </span>
        )}
        {progress.diversity != null && !isGating && (
          <span className="px-2 py-0.5 rounded-full bg-slate-700/60 text-slate-400 font-mono">
            diversidad {progress.diversity}
          </span>
        )}
        {islands > 1 && (
          <span className="px-2 py-0.5 rounded-full bg-purple-500/15 border border-purple-500/30 text-purple-300">
            {islands} islas · mejor {progress.island_best!.map((b) => b.toFixed(2)).join(' / ')}
          </span>
        )}
        {progress.hypermutation && (
          <span className="px-2 py-0.5 rounded-full bg-amber-500/15 border border-amber-500/40 text-amber-300 font-medium animate-pulse">
            ⚡ Hipermutación (escape de estancamiento)
          </span>
        )}
      </div>

      {/* Convergencia del fitness */}
      <div>
        <p className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">
          Convergencia · fitness robustez-aware (Sharpe OOS walk-forward)
        </p>
        <ConvergenceChart history={progress.history} />
      </div>

      {/* Avance del gating */}
      {isGating && progress.gating && (
        <div>
          <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
            <span>Gating de robustez: PBO · lookahead · Monte Carlo · eficiencia WF</span>
            <span className="font-mono">
              {progress.gating.current}/{progress.gating.total} · {progress.gating.passed} aprobadas
            </span>
          </div>
          <div className="h-1.5 bg-slate-700/60 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-emerald-500 rounded-full transition-all duration-500"
              style={{ width: `${(progress.gating.current / Math.max(1, progress.gating.total)) * 100}%` }}
            />
          </div>
          {progress.gating.candidate && (
            <p className="text-[9px] text-slate-500 truncate mt-1">Examinando: {progress.gating.candidate}</p>
          )}
        </div>
      )}

      {/* Avance del refinamiento local (hill-climb re-validado) */}
      {isRefining && progress.refining && (
        <div>
          <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
            <span>Refinando finalistas: vecinos jitter re-validados con el gating completo</span>
            <span className="font-mono">{progress.refining.current}/{progress.refining.total}</span>
          </div>
          <div className="h-1.5 bg-slate-700/60 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full transition-all duration-500"
              style={{ width: `${(progress.refining.current / Math.max(1, progress.refining.total)) * 100}%` }}
            />
          </div>
          {progress.refining.candidate && (
            <p className="text-[9px] text-slate-500 truncate mt-1">Afinando: {progress.refining.candidate}</p>
          )}
        </div>
      )}

      {/* Avance de la validación cruzada multi-activo */}
      {isCross && progress.cross && (
        <div>
          <div className="flex items-center justify-between text-[10px] text-slate-400 mb-1">
            <span>
              Validando cada finalista en otros mercados: {progress.cross.basket.join(' · ')}
            </span>
            <span className="font-mono">{progress.cross.current}/{progress.cross.total}</span>
          </div>
          <div className="h-1.5 bg-slate-700/60 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-purple-500 to-blue-400 rounded-full transition-all duration-500"
              style={{ width: `${(progress.cross.current / Math.max(1, progress.cross.total)) * 100}%` }}
            />
          </div>
          {progress.cross.candidate && (
            <p className="text-[9px] text-slate-500 truncate mt-1">Examinando: {progress.cross.candidate}</p>
          )}
        </div>
      )}

      {/* Curvas de equity de las mejores candidatas de la generación */}
      {!isGating && !isRefining && !isCross && progress.top && progress.top.length > 0 && (
        <div>
          <div className="flex flex-wrap items-baseline gap-x-2 mb-1.5">
            <p className="text-[10px] uppercase tracking-wide text-slate-500">
              Mejores de la búsqueda hasta ahora
            </p>
            <p className="text-[10px] text-slate-600">
              equity dentro de muestra sobre la zona de evolución · el holdout queda intacto
            </p>
          </div>
          <p className="text-[10px] text-amber-400/70 mb-1.5 leading-relaxed">
            Estos retornos son <strong className="font-medium">dentro de muestra</strong>: salen de los
            mismos datos con los que se eligieron estas estrategias, así que están inflados por
            construcción. Ninguna entra en el libro hasta pasar el gating, y al terminar se te dice
            qué fue de cada una.
          </p>
          <CandidateGrid top={progress.top} />
        </div>
      )}
    </div>
  )
}
