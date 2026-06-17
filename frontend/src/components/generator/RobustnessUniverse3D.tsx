/**
 * components/generator/RobustnessUniverse3D.tsx — Universo de robustez (scatter 3D).
 *
 * Cada estrategia evolucionada es un nodo flotante posicionado por sus tres ejes
 * de robustez: eficiencia walk-forward (X), Sharpe out-of-sample (Y) y robustez
 * = 1−PBO (Z). Las que superan el gating brillan en verde con halo aditivo; las
 * descartadas quedan tenues. Comunica de un vistazo que el generador explora un
 * espacio amplio y solo conserva el rincón robusto.
 */

import { useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
import * as THREE from 'three'
import Viz3DFrame from '@/components/viz3d/Viz3DFrame'
import type { Candidate } from '@/services/strategyGeneratorService'

const SPAN = 4 // semieje del cubo de la escena

/** Escala lineal recortada de un valor en [min,max] a [-SPAN, SPAN]. */
function scaler(values: number[]): (v: number | null) => number {
  const valid = values.filter((v) => Number.isFinite(v))
  const min = valid.length ? Math.min(...valid) : 0
  const max = valid.length ? Math.max(...valid) : 1
  const range = max - min || 1
  return (v) => {
    if (v == null || !Number.isFinite(v)) return 0
    return ((v - min) / range) * (SPAN * 2) - SPAN
  }
}

interface Node {
  key: string
  pos: [number, number, number]
  passed: boolean
  size: number
  c: Candidate
}

function Nodes({ candidates, onHover }: Readonly<{ candidates: Candidate[]; onHover: (c: Candidate | null) => void }>) {
  const nodes = useMemo<Node[]>(() => {
    const sx = scaler(candidates.map((c) => c.wf_efficiency ?? 0))
    const sy = scaler(candidates.map((c) => c.oos_sharpe ?? 0))
    const sz = scaler(candidates.map((c) => (c.pbo == null ? 1 : 1 - c.pbo)))
    const fits = candidates.map((c) => c.fitness)
    const fMin = Math.min(...fits), fMax = Math.max(...fits)
    const fRange = fMax - fMin || 1
    return candidates.map((c, i) => ({
      key: c.spec_hash + i,
      pos: [sx(c.wf_efficiency), sy(c.oos_sharpe), sz(c.pbo == null ? 1 : 1 - c.pbo)] as [number, number, number],
      passed: c.passed_gating,
      size: 0.18 + ((c.fitness - fMin) / fRange) * 0.28,
      c,
    }))
  }, [candidates])

  return (
    <group>
      {nodes.map((n) => (
        <NodeMesh key={n.key} node={n} onHover={onHover} />
      ))}
    </group>
  )
}

function NodeMesh({ node, onHover }: Readonly<{ node: Node; onHover: (c: Candidate | null) => void }>) {
  const halo = useRef<THREE.Mesh>(null)
  const [hover, setHover] = useState(false)
  const color = node.passed ? '#34d399' : '#64748b'

  useFrame(({ clock }) => {
    if (halo.current && node.passed) {
      const s = 1 + Math.sin(clock.elapsedTime * 2 + node.pos[0]) * 0.12
      halo.current.scale.setScalar(s)
    }
  })

  return (
    <group position={node.pos}>
      {/* Núcleo */}
      <mesh
        onPointerOver={(e) => { e.stopPropagation(); setHover(true); onHover(node.c) }}
        onPointerOut={() => { setHover(false); onHover(null) }}
        scale={hover ? 1.4 : 1}
      >
        <sphereGeometry args={[node.size, 24, 24]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={node.passed ? 1.4 : 0.25}
          roughness={0.35}
        />
      </mesh>

      {/* Halo aditivo (solo supervivientes) */}
      {node.passed && (
        <mesh ref={halo}>
          <sphereGeometry args={[node.size * 2.1, 16, 16]} />
          <meshBasicMaterial color={color} transparent opacity={0.18} blending={THREE.AdditiveBlending} depthWrite={false} />
        </mesh>
      )}

      {hover && (
        <Html distanceFactor={10} position={[0, node.size + 0.3, 0]} center>
          <div className="px-2 py-1 rounded-md bg-slate-900/95 border border-slate-600 text-[10px] text-slate-200 whitespace-nowrap shadow-xl pointer-events-none">
            <span className={node.passed ? 'text-emerald-400 font-semibold' : 'text-slate-400'}>
              {node.passed ? '✓ robusta' : '✗ descartada'}
            </span>
            {' · '}fit {node.c.fitness.toFixed(2)}
            {' · '}PBO {node.c.pbo != null ? `${Math.round(node.c.pbo * 100)}%` : '—'}
          </div>
        </Html>
      )}
    </group>
  )
}

/** Aristas del cubo + etiquetas de eje. */
function AxesCube() {
  const lines = useMemo(() => {
    const s = SPAN + 0.4
    const geo = new THREE.BufferGeometry()
    const c = [
      [-s, -s, -s], [s, -s, -s], [s, -s, s], [-s, -s, s],
      [-s, s, -s], [s, s, -s], [s, s, s], [-s, s, s],
    ]
    const edges = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]]
    const pts: number[] = []
    edges.forEach(([a, b]) => { pts.push(...c[a], ...c[b]) })
    geo.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    return geo
  }, [])

  return (
    <group>
      <lineSegments geometry={lines}>
        <lineBasicMaterial color="#1e3a5f" transparent opacity={0.6} />
      </lineSegments>
      <Html position={[SPAN, -SPAN - 0.9, -SPAN]} center>
        <span className="text-[10px] text-blue-300/80 whitespace-nowrap">Eficiencia WF →</span>
      </Html>
      <Html position={[-SPAN - 0.9, SPAN, -SPAN]} center>
        <span className="text-[10px] text-emerald-300/80 whitespace-nowrap">↑ Sharpe OOS</span>
      </Html>
      <Html position={[-SPAN - 0.5, -SPAN - 0.9, SPAN]} center>
        <span className="text-[10px] text-purple-300/80 whitespace-nowrap">Robustez (1−PBO) ↗</span>
      </Html>
    </group>
  )
}

export default function RobustnessUniverse3D({ candidates }: Readonly<{ candidates: Candidate[] }>) {
  const [hovered, setHovered] = useState<Candidate | null>(null)

  if (!candidates.length) {
    return <div className="text-slate-500 text-sm text-center py-16">Sin candidatas para visualizar.</div>
  }

  return (
    <div className="relative">
      <Viz3DFrame camera={[8, 6, 10]}>
        <AxesCube />
        <Nodes candidates={candidates} onHover={setHovered} />
      </Viz3DFrame>
      <div className="absolute top-3 right-3 text-right pointer-events-none">
        <div className="flex items-center gap-2 justify-end text-[11px]">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
          <span className="text-slate-300">Supera el gating</span>
        </div>
        <div className="flex items-center gap-2 justify-end text-[11px] mt-1">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-slate-500" />
          <span className="text-slate-400">Descartada</span>
        </div>
      </div>
      {hovered && (
        <div className="mt-2 text-[11px] text-slate-400 font-mono truncate">{hovered.description}</div>
      )}
    </div>
  )
}
