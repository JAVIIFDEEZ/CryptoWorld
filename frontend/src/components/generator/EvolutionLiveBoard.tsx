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
const H = 180
const PAD = { top: 12, right: 74, bottom: 22, left: 44 }

function ConvergenceChart({ history }: Readonly<{ history: GenerationHistoryPoint[] }>) {
  const [hover, setHover] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement>(null)

  const { pts, yMin, yMax } = useMemo(() => {
    const values = history.flatMap((h) => [h.best, h.mean])
    const lo = Math.min(...values)
    const hi = Math.max(...values)
    const span = hi - lo || 1
    const x = (g: number) => PAD.left + (history.length < 2 ? 0 : (g / (history.length - 1)) * (W - PAD.left - PAD.right))
    const y = (v: number) => H - PAD.bottom - ((v - lo) / span) * (H - PAD.top - PAD.bottom)
    return {
      pts: history.map((h, i) => ({ x: x(i), yBest: y(h.best), yMean: y(h.mean), h })),
      yMin: lo, yMax: hi,
    }
  }, [history])

  if (history.length < 2) {
    return (
      <div className="h-[180px] flex items-center justify-center text-xs text-slate-500">
        Esperando las primeras generaciones…
      </div>
    )
  }

  const line = (key: 'yBest' | 'yMean') => pts.map((p) => `${p.x.toFixed(1)},${p[key].toFixed(1)}`).join(' ')
  const hovered = hover != null ? pts[hover] : null

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
        {/* Rejilla recesiva: mín / máx */}
        {[yMin, yMax].map((v, i) => {
          const y = i === 0 ? H - PAD.bottom : PAD.top
          return (
            <g key={i}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke="#334155" strokeWidth={0.6} strokeDasharray="2 4" />
              <text x={PAD.left - 6} y={y + 3} textAnchor="end" fontSize={9} className="fill-slate-500 font-mono">
                {v.toFixed(2)}
              </text>
            </g>
          )
        })}
        {/* Eje X: generaciones */}
        <text x={PAD.left} y={H - 6} fontSize={9} className="fill-slate-500 font-mono">gen 0</text>
        <text x={W - PAD.right} y={H - 6} textAnchor="end" fontSize={9} className="fill-slate-500 font-mono">
          gen {history.length - 1}
        </text>

        {/* Media de la población: línea de referencia discontinua */}
        <polyline points={line('yMean')} fill="none" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="5 4" strokeOpacity={0.8} />
        {/* Mejor de la generación: serie principal */}
        <polyline points={line('yBest')} fill="none" stroke="#60a5fa" strokeWidth={2} strokeLinejoin="round" />

        {/* Etiquetas directas al final de cada serie */}
        <text x={pts[pts.length - 1].x + 6} y={pts[pts.length - 1].yBest + 3} fontSize={9} className="fill-slate-200 font-medium">
          mejor {history[history.length - 1].best.toFixed(2)}
        </text>
        <text x={pts[pts.length - 1].x + 6} y={pts[pts.length - 1].yMean + 3} fontSize={9} className="fill-slate-400">
          media {history[history.length - 1].mean.toFixed(2)}
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
      <div className="flex items-center gap-4 mt-1 text-[10px] text-slate-400">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-4 h-0.5 bg-blue-400 rounded" /> mejor de la generación
        </span>
        <span className="flex items-center gap-1.5">
          <svg width="16" height="2"><line x1="0" x2="16" y1="1" y2="1" stroke="#94a3b8" strokeWidth="2" strokeDasharray="4 3" /></svg>
          media de la población
        </span>
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
        return (
          <div
            key={c.hash}
            className="bg-slate-900/50 border border-slate-700/60 rounded-lg p-2.5 transition-all duration-300"
            title={c.description}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[9px] uppercase tracking-wide text-slate-500">#{i + 1} · fitness</span>
              <span className="text-[11px] font-mono font-bold text-blue-300">{c.fitness.toFixed(3)}</span>
            </div>
            <Sparkline data={c.equity} width={180} height={36} className="w-full mt-1" color={up ? '#34d399' : '#f87171'} />
            <div className="flex items-center justify-between mt-1 text-[9px] font-mono">
              <span className={up ? 'text-emerald-400' : 'text-red-400'}>
                {up ? '+' : ''}{c.total_return_pct?.toFixed(1)}%
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
  const gen = progress.generation ?? Math.max(0, progress.history.length - 1)
  const total = progress.generations_total ?? progress.history.length
  const islands = progress.island_best?.length ?? 0
  const phaseLabel = isGating ? 'Gating de robustez'
    : isRefining ? 'Refinando finalistas'
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

      {/* Curvas de equity de las mejores candidatas de la generación */}
      {!isGating && !isRefining && progress.top && progress.top.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wide text-slate-500 mb-1.5">
            Mejores candidatas de la generación · equity sobre la zona de evolución (el holdout queda intacto)
          </p>
          <CandidateGrid top={progress.top} />
        </div>
      )}
    </div>
  )
}
