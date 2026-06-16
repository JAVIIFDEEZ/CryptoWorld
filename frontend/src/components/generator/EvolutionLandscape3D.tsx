/**
 * components/generator/EvolutionLandscape3D.tsx — Paisaje evolutivo (terreno 3D).
 *
 * Muestra cómo sube el fitness generación a generación: una hilera frontal de
 * columnas (mejor fitness por generación, que se elevan al montarse) y una
 * hilera trasera translúcida (fitness medio de la población). El degradado de
 * color comunica la convergencia del algoritmo genético.
 */

import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import Viz3DFrame from './Viz3DFrame'
import type { GenerationHistoryPoint } from '@/services/strategyGeneratorService'

const WIDTH = 9 // ancho total del terreno
const MAX_H = 4 // altura máxima de columna

function color(t: number): string {
  // t en [0,1]: rojo→ámbar→esmeralda (peor→mejor)
  const c = new THREE.Color()
  c.setHSL(0.0 + t * 0.38, 0.75, 0.55)
  return `#${c.getHexString()}`
}

function Bar({ x, height, z, col, opacity, delay }: Readonly<{
  x: number; height: number; z: number; col: string; opacity: number; delay: number
}>) {
  const ref = useRef<THREE.Mesh>(null)
  useFrame(({ clock }) => {
    if (!ref.current) return
    const t = Math.min(1, Math.max(0, (clock.elapsedTime - delay) / 0.8))
    const eased = 1 - Math.pow(1 - t, 3)
    const h = Math.max(0.001, height * eased)
    ref.current.scale.y = h
    ref.current.position.y = h / 2
  })
  return (
    <mesh ref={ref} position={[x, 0, z]}>
      <boxGeometry args={[WIDTH / 26, 1, 0.5]} />
      <meshStandardMaterial
        color={col}
        emissive={col}
        emissiveIntensity={opacity >= 1 ? 0.5 : 0.15}
        transparent={opacity < 1}
        opacity={opacity}
        roughness={0.4}
      />
    </mesh>
  )
}

function Terrain({ history }: Readonly<{ history: GenerationHistoryPoint[] }>) {
  const { bestBars, meanBars } = useMemo(() => {
    const all = history.flatMap((h) => [h.best, h.mean])
    const min = Math.min(...all), max = Math.max(...all)
    const range = max - min || 1
    const n = history.length
    const step = n > 1 ? WIDTH / (n - 1) : 0
    const norm = (v: number) => 0.15 + ((v - min) / range) * (MAX_H - 0.15)
    const x = (i: number) => (n > 1 ? -WIDTH / 2 + i * step : 0)
    const t = (v: number) => (v - min) / range
    return {
      bestBars: history.map((h, i) => ({ x: x(i), height: norm(h.best), col: color(t(h.best)), delay: i * 0.05 })),
      meanBars: history.map((h, i) => ({ x: x(i), height: norm(h.mean), col: color(t(h.mean)), delay: i * 0.05 })),
    }
  }, [history])

  return (
    <group position={[0, -MAX_H / 2, 0]}>
      {/* Suelo */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
        <planeGeometry args={[WIDTH + 2, 4]} />
        <meshStandardMaterial color="#0b1426" roughness={1} />
      </mesh>
      {/* Rejilla del suelo */}
      <gridHelper args={[WIDTH + 2, 16, '#1e3a5f', '#14233d']} position={[0, 0.01, 0]} />

      {meanBars.map((b, i) => (
        <Bar key={`m${i}`} x={b.x} z={-0.8} height={b.height} col={b.col} opacity={0.4} delay={b.delay} />
      ))}
      {bestBars.map((b, i) => (
        <Bar key={`b${i}`} x={b.x} z={0.5} height={b.height} col={b.col} opacity={1} delay={b.delay} />
      ))}

      <Html position={[-WIDTH / 2, -0.4, 1]} center>
        <span className="text-[10px] text-slate-400 whitespace-nowrap">gen 0</span>
      </Html>
      <Html position={[WIDTH / 2, -0.4, 1]} center>
        <span className="text-[10px] text-slate-400 whitespace-nowrap">gen {history.length - 1}</span>
      </Html>
      <Html position={[0, MAX_H + 0.4, 0]} center>
        <span className="text-[10px] text-emerald-300/80 whitespace-nowrap">↑ fitness (mejor · medio)</span>
      </Html>
    </group>
  )
}

export default function EvolutionLandscape3D({ history }: Readonly<{ history: GenerationHistoryPoint[] }>) {
  if (!history.length) {
    return <div className="text-slate-500 text-sm text-center py-16">Sin historia de evolución.</div>
  }
  return (
    <Viz3DFrame camera={[0, 5, 11]} autoRotate={false}>
      <Terrain history={history} />
    </Viz3DFrame>
  )
}
