/**
 * components/generator/ParetoFrontier3D.tsx — Frontera de Pareto en 3D.
 *
 * Cada estrategia no dominada es una esfera situada por sus TRES objetivos:
 * X = robustez frente al drawdown (menos drawdown → derecha), Y = Sharpe OOS,
 * Z = robustez frente al sobreajuste (menos gap → al frente). El color refuerza
 * el sobreajuste. Ver los tres ejes a la vez deja claro el compromiso completo.
 */

import { useMemo, useState } from 'react'
import { Html } from '@react-three/drei'
import Viz3DFrame from '@/components/viz3d/Viz3DFrame'
import type { ParetoPoint } from '@/services/strategyGeneratorService'
import { gapColor } from './ParetoFrontier2D'

const SPAN = 4

function scaler(values: number[]): (v: number) => number {
  const vals = values.filter(Number.isFinite)
  const min = vals.length ? Math.min(...vals) : 0
  const max = vals.length ? Math.max(...vals) : 1
  const range = max - min || 1
  return (v) => ((v - min) / range) * (SPAN * 2) - SPAN
}

interface Node { p: ParetoPoint; pos: [number, number, number]; r: number }

function Points({ points }: Readonly<{ points: ParetoPoint[] }>) {
  const nodes = useMemo<Node[]>(() => {
    // Menos drawdown y menos gap = mejor → invertimos el signo para que "mejor" caiga a +.
    const sx = scaler(points.map((p) => -p.max_drawdown_pct))
    const sy = scaler(points.map((p) => p.oos_sharpe))
    const sz = scaler(points.map((p) => -p.overfit_gap))
    const sh = points.map((p) => p.oos_sharpe)
    const mn = Math.min(...sh), mx = Math.max(...sh), rg = mx - mn || 1
    return points.map((p) => ({
      p,
      pos: [sx(-p.max_drawdown_pct), sy(p.oos_sharpe), sz(-p.overfit_gap)] as [number, number, number],
      r: 0.22 + ((p.oos_sharpe - mn) / rg) * 0.45,
    }))
  }, [points])

  return (
    <group>
      {nodes.map((n, i) => <Bead key={n.p.spec_hash + i} node={n} />)}
      <Html position={[SPAN, -SPAN - 0.8, -SPAN]} center>
        <span className="text-[10px] text-blue-300/80 whitespace-nowrap">Menos drawdown →</span>
      </Html>
      <Html position={[-SPAN - 0.9, SPAN, -SPAN]} center>
        <span className="text-[10px] text-emerald-300/80 whitespace-nowrap">↑ Sharpe OOS</span>
      </Html>
      <Html position={[-SPAN - 0.4, -SPAN - 0.8, SPAN]} center>
        <span className="text-[10px] text-purple-300/80 whitespace-nowrap">Menos sobreajuste ↗</span>
      </Html>
    </group>
  )
}

function Bead({ node }: Readonly<{ node: Node }>) {
  const [hover, setHover] = useState(false)
  const col = gapColor(node.p.overfit_gap)
  return (
    <group position={node.pos}>
      <mesh scale={hover ? 1.3 : 1} onPointerOver={(e) => { e.stopPropagation(); setHover(true) }} onPointerOut={() => setHover(false)}>
        <sphereGeometry args={[node.r, 24, 24]} />
        <meshStandardMaterial color={col} emissive={col} emissiveIntensity={0.5} roughness={0.4} />
      </mesh>
      {hover && (
        <Html position={[0, node.r + 0.25, 0]} center distanceFactor={10}>
          <div className="px-2 py-1 rounded-md bg-slate-900/95 border border-slate-600 text-[10px] text-slate-200 whitespace-nowrap shadow-xl pointer-events-none">
            Sharpe {node.p.oos_sharpe.toFixed(2)} · DD {node.p.max_drawdown_pct}% · gap {node.p.overfit_gap.toFixed(2)}
          </div>
        </Html>
      )}
    </group>
  )
}

export default function ParetoFrontier3D({ points }: Readonly<{ points: ParetoPoint[] }>) {
  if (!points.length) return <div className="text-slate-500 text-sm text-center py-16">Sin frontera que mostrar.</div>
  return (
    <Viz3DFrame camera={[8, 6, 10]} height={400}>
      <Points points={points} />
    </Viz3DFrame>
  )
}
