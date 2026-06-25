/**
 * components/generator/StrategyDNAHelix3D.tsx — ADN de la estrategia (hélice 3D).
 *
 * Representa los bloques de la estrategia ganadora como una doble hélice: las
 * condiciones de entrada (azul) y de salida (ámbar) son cuentas luminosas
 * ensartadas en una cadena que gira, con su etiqueta legible. Es la "firma"
 * visual de la estrategia campeona.
 */

import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import Viz3DFrame from '@/components/viz3d/Viz3DFrame'
import { useReducedMotion } from '@/hooks/useReducedMotion'
import type { StrategySpec, SpecCondition } from '@/services/strategyGeneratorService'

const R = 2.1            // radio de la hélice
const TURN = 2.4         // separación angular entre cuentas
const Y_STEP = 0.95      // separación vertical entre cuentas

function label(c: SpecCondition): string {
  if (c.type === 'threshold') {
    const sym = c.op === 'gt' ? '>' : '<'
    return `${c.indicator}${sym}${c.threshold}`
  }
  const arrow = c.op === 'cross_above' ? '↗' : '↘'
  return `${c.a?.indicator}${arrow}${c.b?.indicator}`
}

interface Bead {
  c: SpecCondition
  side: 'entry' | 'exit'
  y: number
  a: number
}

function Helix({ spec }: Readonly<{ spec: StrategySpec }>) {
  const group = useRef<THREE.Group>(null)
  const reduced = useReducedMotion()

  const beads = useMemo<Bead[]>(() => {
    const items: { c: SpecCondition; side: 'entry' | 'exit' }[] = [
      ...spec.entry.conditions.map((c) => ({ c, side: 'entry' as const })),
      ...spec.exit.conditions.map((c) => ({ c, side: 'exit' as const })),
    ]
    const total = items.length
    return items.map((it, i) => ({
      ...it,
      y: (i - (total - 1) / 2) * Y_STEP,
      a: i * TURN,
    }))
  }, [spec])

  // Cadenas continuas (backbones) como tubos
  const { strandA, strandB } = useMemo(() => {
    const a: THREE.Vector3[] = []
    const b: THREE.Vector3[] = []
    const total = beads.length
    const steps = Math.max(2, total * 8)
    const yTop = ((total - 1) / 2) * Y_STEP
    for (let s = 0; s <= steps; s++) {
      const f = s / steps
      const ang = f * (total - 1) * TURN
      const y = yTop - f * (total - 1) * Y_STEP
      a.push(new THREE.Vector3(Math.cos(ang) * R, y, Math.sin(ang) * R))
      b.push(new THREE.Vector3(Math.cos(ang + Math.PI) * R, y, Math.sin(ang + Math.PI) * R))
    }
    return {
      strandA: new THREE.CatmullRomCurve3(a),
      strandB: new THREE.CatmullRomCurve3(b),
    }
  }, [beads])

  useFrame((_, delta) => {
    if (group.current && !reduced) group.current.rotation.y += delta * 0.35
  })

  return (
    <group ref={group}>
      {/* Backbones */}
      <mesh>
        <tubeGeometry args={[strandA, 120, 0.05, 8, false]} />
        <meshStandardMaterial color="#1e3a5f" emissive="#1e3a5f" emissiveIntensity={0.4} />
      </mesh>
      <mesh>
        <tubeGeometry args={[strandB, 120, 0.05, 8, false]} />
        <meshStandardMaterial color="#3b2f5f" emissive="#3b2f5f" emissiveIntensity={0.4} />
      </mesh>

      {beads.map((bd, i) => {
        const col = bd.side === 'entry' ? '#60a5fa' : '#fbbf24'
        const px = Math.cos(bd.a) * R
        const pz = Math.sin(bd.a) * R
        const qx = Math.cos(bd.a + Math.PI) * R
        const qz = Math.sin(bd.a + Math.PI) * R
        // Rung (par de bases)
        const mid = new THREE.Vector3((px + qx) / 2, bd.y, (pz + qz) / 2)
        const dir = new THREE.Vector3(qx - px, 0, qz - pz)
        const len = dir.length()
        const quat = new THREE.Quaternion().setFromUnitVectors(
          new THREE.Vector3(0, 1, 0),
          dir.clone().normalize(),
        )
        return (
          <group key={i}>
            {/* Rung */}
            <mesh position={mid} quaternion={quat}>
              <cylinderGeometry args={[0.025, 0.025, len, 6]} />
              <meshStandardMaterial color="#334155" transparent opacity={0.6} />
            </mesh>
            {/* Cuenta etiquetada (lado principal) */}
            <mesh position={[px, bd.y, pz]}>
              <sphereGeometry args={[0.28, 20, 20]} />
              <meshStandardMaterial color={col} emissive={col} emissiveIntensity={1.3} roughness={0.3} />
            </mesh>
            <mesh position={[px, bd.y, pz]}>
              <sphereGeometry args={[0.5, 12, 12]} />
              <meshBasicMaterial color={col} transparent opacity={0.16} blending={THREE.AdditiveBlending} depthWrite={false} />
            </mesh>
            {/* Cuenta espejo (lado secundario, decorativa) */}
            <mesh position={[qx, bd.y, qz]}>
              <sphereGeometry args={[0.13, 12, 12]} />
              <meshStandardMaterial color={col} emissive={col} emissiveIntensity={0.5} transparent opacity={0.55} />
            </mesh>
            <Html position={[px, bd.y + 0.42, pz]} center distanceFactor={9}>
              <div
                className="px-1.5 py-0.5 rounded text-[9px] font-mono whitespace-nowrap pointer-events-none"
                style={{
                  background: 'rgba(2,6,23,0.85)',
                  border: `1px solid ${col}`,
                  color: col,
                }}
              >
                {label(bd.c)}
              </div>
            </Html>
          </group>
        )
      })}
    </group>
  )
}

export default function StrategyDNAHelix3D({ spec }: Readonly<{ spec: StrategySpec | null }>) {
  if (!spec) {
    return <div className="text-slate-500 text-sm text-center py-16">Sin estrategia ganadora que mostrar.</div>
  }
  return (
    <div className="relative">
      <Viz3DFrame camera={[0, 0, 9]} autoRotate={false}>
        <Helix spec={spec} />
      </Viz3DFrame>
      <div className="absolute top-3 right-3 text-right pointer-events-none space-y-1">
        <div className="flex items-center gap-2 justify-end text-[11px]">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-400 shadow-[0_0_8px_#60a5fa]" />
          <span className="text-slate-300">Entrada</span>
        </div>
        <div className="flex items-center gap-2 justify-end text-[11px]">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-400 shadow-[0_0_8px_#fbbf24]" />
          <span className="text-slate-300">Salida</span>
        </div>
      </div>
    </div>
  )
}
