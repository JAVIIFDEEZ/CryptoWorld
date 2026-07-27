/**
 * components/portfolio/RiskReturn3D.tsx — Riesgo / retorno 3D.
 *
 * Cada holding es una esfera: X = volatilidad 7d, Y = retorno 7d, tamaño = peso
 * en la cartera; color verde/rojo según el retorno. Un "mini mapa" de la frontera
 * riesgo-retorno de tu cartera.
 */

import { useMemo, useState } from 'react'
import { Html } from '@react-three/drei'
import Viz3DFrame from '@/components/viz3d/Viz3DFrame'
import type { RiskReturnPoint } from './portfolioViz'

const SPAN = 4

function scaler(values: number[]): (v: number) => number {
  const vals = values.filter(Number.isFinite)
  const min = Math.min(0, ...vals)
  const max = Math.max(...vals, 0.0001)
  const range = max - min || 1
  return (v) => ((v - min) / range) * (SPAN * 2) - SPAN
}

export default function RiskReturn3D({ points }: Readonly<{ points: RiskReturnPoint[] }>) {
  if (!points.length) {
    return <div className="text-slate-500 text-sm text-center py-16">Sin posiciones con histórico suficiente.</div>
  }
  return (
    <div className="relative">
      <Viz3DFrame camera={[8, 5, 9]} height={420}>
        <Scene points={points} />
      </Viz3DFrame>
      <div className="absolute top-3 right-3 text-[10px] text-slate-400 pointer-events-none">Tamaño = peso en la cartera</div>
    </div>
  )
}

function Scene({ points }: Readonly<{ points: RiskReturnPoint[] }>) {
  const nodes = useMemo(() => {
    const sx = scaler(points.map((p) => p.vol))
    const sy = scaler(points.map((p) => p.ret))
    return points.map((p) => ({
      p,
      pos: [sx(p.vol), sy(p.ret), 0] as [number, number, number],
      radius: 0.2 + Math.sqrt(p.weight) * 0.9,
      col: p.ret >= 0 ? '#34d399' : '#f87171',
    }))
  }, [points])

  return (
    <group>
      {/* Plano del cero (retorno 0) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, scalerZero(points), 0]}>
        <planeGeometry args={[SPAN * 2.4, 0.02]} />
        <meshBasicMaterial color="#334155" />
      </mesh>
      {nodes.map((n) => (
        <Bubble key={n.p.symbol} pos={n.pos} radius={n.radius} col={n.col} p={n.p} />
      ))}
      <Html position={[SPAN, -SPAN - 0.8, 0]} center>
        <span className="text-[10px] text-amber-300/80 whitespace-nowrap">Volatilidad →</span>
      </Html>
      <Html position={[-SPAN - 0.9, SPAN, 0]} center>
        <span className="text-[10px] text-emerald-300/80 whitespace-nowrap">↑ Retorno 7d</span>
      </Html>
    </group>
  )
}

function scalerZero(points: RiskReturnPoint[]): number {
  const vals = points.map((p) => p.ret)
  const min = Math.min(0, ...vals)
  const max = Math.max(...vals, 0.0001)
  const range = max - min || 1
  return ((0 - min) / range) * (SPAN * 2) - SPAN
}

function Bubble({ pos, radius, col, p }: Readonly<{ pos: [number, number, number]; radius: number; col: string; p: RiskReturnPoint }>) {
  const [hover, setHover] = useState(false)
  return (
    <group position={pos}>
      <mesh scale={hover ? 1.2 : 1} onPointerOver={(e) => { e.stopPropagation(); setHover(true) }} onPointerOut={() => setHover(false)}>
        <sphereGeometry args={[radius, 24, 24]} />
        <meshStandardMaterial color={col} emissive={col} emissiveIntensity={0.4} roughness={0.4} />
      </mesh>
      <Html position={[0, radius + 0.2, 0]} center distanceFactor={11}>
        <div className="text-[10px] font-bold whitespace-nowrap pointer-events-none" style={{ color: col }}>{p.symbol}</div>
      </Html>
      {hover && (
        <Html position={[0, -radius - 0.2, 0]} center distanceFactor={10}>
          <div className="px-2 py-1 rounded-md bg-slate-900/95 border border-slate-600 text-[10px] text-slate-200 whitespace-nowrap shadow-xl pointer-events-none">
            ret {p.ret >= 0 ? '+' : ''}{p.ret.toFixed(1)}% · vol {p.vol.toFixed(1)}% · peso {(p.weight * 100).toFixed(0)}%
          </div>
        </Html>
      )}
    </group>
  )
}
