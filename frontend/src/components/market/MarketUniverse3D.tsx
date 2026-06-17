/**
 * components/market/MarketUniverse3D.tsx — Universo de mercado (galaxia 3D).
 *
 * Cada cripto es una esfera: tamaño = capitalización (log), posición por
 * variación 24h (X), volatilidad 7d (Y) y rango de capitalización (Z), color por
 * signo de la variación. Halo en los grandes movimientos. Al hacer clic, navega
 * a la ficha del activo.
 */

import { useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import Viz3DFrame from '@/components/viz3d/Viz3DFrame'
import { changeColor, type MarketBody } from './marketViz'

const SPAN = 4.2

function scaler(values: number[], clampAbs?: number): (v: number) => number {
  let vals = values.filter(Number.isFinite)
  if (clampAbs) vals = vals.map((v) => Math.max(-clampAbs, Math.min(clampAbs, v)))
  const min = vals.length ? Math.min(...vals) : 0
  const max = vals.length ? Math.max(...vals) : 1
  const range = max - min || 1
  return (v) => {
    const c = clampAbs ? Math.max(-clampAbs, Math.min(clampAbs, v)) : v
    return ((c - min) / range) * (SPAN * 2) - SPAN
  }
}

interface Body3D {
  b: MarketBody
  pos: [number, number, number]
  radius: number
}

function Bodies({ bodies, onSelect }: Readonly<{ bodies: MarketBody[]; onSelect: (s: string) => void }>) {
  const nodes = useMemo<Body3D[]>(() => {
    const sx = scaler(bodies.map((b) => b.change), 15)
    const sy = scaler(bodies.map((b) => b.volatility))
    const caps = bodies.map((b) => Math.log10(b.marketCap + 1))
    const sz = scaler(caps)
    const cMin = Math.min(...caps), cMax = Math.max(...caps)
    const cRange = cMax - cMin || 1
    return bodies.map((b) => {
      const lc = Math.log10(b.marketCap + 1)
      return {
        b,
        pos: [sx(b.change), sy(b.volatility), sz(lc)] as [number, number, number],
        radius: 0.22 + ((lc - cMin) / cRange) * 0.7,
      }
    })
  }, [bodies])

  return (
    <group>
      {nodes.map((n) => <Planet key={n.b.symbol} node={n} onSelect={onSelect} />)}
    </group>
  )
}

function Planet({ node, onSelect }: Readonly<{ node: Body3D; onSelect: (s: string) => void }>) {
  const halo = useRef<THREE.Mesh>(null)
  const [hover, setHover] = useState(false)
  const color = changeColor(node.b.change)
  const big = Math.abs(node.b.change) >= 6

  useFrame(({ clock }) => {
    if (halo.current && big) halo.current.scale.setScalar(1 + Math.sin(clock.elapsedTime * 2 + node.pos[0]) * 0.15)
  })

  return (
    <group position={node.pos}>
      <mesh
        scale={hover ? 1.25 : 1}
        onPointerOver={(e) => { e.stopPropagation(); setHover(true) }}
        onPointerOut={() => setHover(false)}
        onClick={(e) => { e.stopPropagation(); onSelect(node.b.symbol) }}
      >
        <sphereGeometry args={[node.radius, 28, 28]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={big ? 0.9 : 0.35} roughness={0.4} />
      </mesh>
      {big && (
        <mesh ref={halo}>
          <sphereGeometry args={[node.radius * 1.8, 16, 16]} />
          <meshBasicMaterial color={color} transparent opacity={0.16} blending={THREE.AdditiveBlending} depthWrite={false} />
        </mesh>
      )}
      <Html position={[0, node.radius + 0.25, 0]} center distanceFactor={12}>
        <div className={`text-[10px] font-bold whitespace-nowrap pointer-events-none transition-opacity ${hover ? 'opacity-100' : 'opacity-70'}`} style={{ color }}>
          {node.b.symbol}
        </div>
      </Html>
      {hover && (
        <Html position={[0, -node.radius - 0.2, 0]} center distanceFactor={10}>
          <div className="px-2 py-1 rounded-md bg-slate-900/95 border border-slate-600 text-[10px] text-slate-200 whitespace-nowrap shadow-xl pointer-events-none">
            {node.b.name} · {node.b.change >= 0 ? '+' : ''}{node.b.change.toFixed(2)}% · vol {node.b.volatility.toFixed(1)}%
          </div>
        </Html>
      )}
    </group>
  )
}

function Axes() {
  return (
    <group>
      <Html position={[SPAN, -SPAN - 0.8, -SPAN]} center>
        <span className="text-[10px] text-blue-300/80 whitespace-nowrap">Variación 24h →</span>
      </Html>
      <Html position={[-SPAN - 0.9, SPAN, -SPAN]} center>
        <span className="text-[10px] text-amber-300/80 whitespace-nowrap">↑ Volatilidad 7d</span>
      </Html>
      <Html position={[-SPAN - 0.4, -SPAN - 0.8, SPAN]} center>
        <span className="text-[10px] text-purple-300/80 whitespace-nowrap">Capitalización ↗</span>
      </Html>
    </group>
  )
}

export default function MarketUniverse3D({ bodies, onSelect }: Readonly<{ bodies: MarketBody[]; onSelect: (s: string) => void }>) {
  if (!bodies.length) {
    return <div className="text-slate-500 text-sm text-center py-16">Sin datos de mercado para visualizar.</div>
  }
  return (
    <div className="relative">
      <Viz3DFrame camera={[9, 6, 11]} height={460}>
        <Axes />
        <Bodies bodies={bodies} onSelect={onSelect} />
      </Viz3DFrame>
      <div className="absolute top-3 right-3 text-[10px] text-slate-400 pointer-events-none">
        Tamaño = capitalización · clic para abrir la ficha
      </div>
    </div>
  )
}
