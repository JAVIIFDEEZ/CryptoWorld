/**
 * components/learn/BlockchainGraph3D.tsx — Grafo 3D de blockchains y puentes.
 *
 * Cada esfera es una blockchain (tamaño = ecosistema, color = marca). Las L1 se
 * reparten en un anillo; las L2/sidechains que liquidan en Ethereum se apilan
 * VERTICALMENTE sobre él — así se ve, literalmente, la "capa 2 encima de la capa
 * 1". Las aristas son conexiones: liquidación (L2→base, en verde-azulado) y
 * puentes cross-chain (en ámbar). Hover muestra la cadena; clic la selecciona y
 * la página abre su ficha educativa.
 */

import { useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Line, Html } from '@react-three/drei'
import * as THREE from 'three'
import Viz3DFrame from '@/components/viz3d/Viz3DFrame'
import { CHAINS, allEdges, type ChainNode } from '@/data/learnData'

const RING = 6.4

/** Posiciones deterministas: L1 en anillo, L2/sidechains apiladas sobre Ethereum. */
function useLayout(): Map<string, THREE.Vector3> {
  return useMemo(() => {
    const pos = new Map<string, THREE.Vector3>()
    const l1 = CHAINS.filter((c) => c.category === 'L1')
    l1.forEach((c, i) => {
      const a = (i / l1.length) * Math.PI * 2
      pos.set(c.id, new THREE.Vector3(Math.cos(a) * RING, 0, Math.sin(a) * RING))
    })
    const eth = pos.get('ethereum') ?? new THREE.Vector3(0, 0, 0)
    const stacked = CHAINS.filter((c) => c.settlesOn === 'ethereum')
    stacked.forEach((c, k) => {
      const a = k * 2.399963  // ángulo áureo → reparto uniforme sin solapes
      pos.set(c.id, new THREE.Vector3(eth.x + Math.cos(a) * 1.5, 1.9 + k * 1.02, eth.z + Math.sin(a) * 1.5))
    })
    return pos
  }, [])
}

function nodeRadius(c: ChainNode): number {
  return 0.26 + c.size * 0.44
}

function Node({ chain, pos, selected, dimmed, onSelect }: Readonly<{
  chain: ChainNode; pos: THREE.Vector3; selected: boolean; dimmed: boolean
  onSelect: (id: string) => void
}>) {
  const [hover, setHover] = useState(false)
  const r = nodeRadius(chain)
  const active = hover || selected
  return (
    <group position={pos}>
      <mesh
        onPointerOver={(e) => { e.stopPropagation(); setHover(true); document.body.style.cursor = 'pointer' }}
        onPointerOut={() => { setHover(false); document.body.style.cursor = 'auto' }}
        onClick={(e) => { e.stopPropagation(); onSelect(chain.id) }}
      >
        <sphereGeometry args={[r, 32, 32]} />
        <meshStandardMaterial
          color={chain.color}
          emissive={chain.color}
          emissiveIntensity={active ? 0.85 : dimmed ? 0.1 : 0.35}
          opacity={dimmed && !active ? 0.5 : 1}
          transparent
          roughness={0.4}
          metalness={0.3}
        />
      </mesh>
      {selected && (
        <mesh>
          <sphereGeometry args={[r * 1.5, 24, 24]} />
          <meshBasicMaterial color={chain.color} transparent opacity={0.16} />
        </mesh>
      )}
      {/* Etiqueta permanente (símbolo) + ficha al pasar el ratón */}
      <Html center distanceFactor={11} position={[0, r + 0.42, 0]} style={{ pointerEvents: 'none' }}>
        {active ? (
          <div className="px-2 py-1 rounded-lg bg-slate-900/95 border border-slate-600 text-[10px] text-white whitespace-nowrap shadow-xl text-center">
            <span className="font-semibold">{chain.name}</span>
            <span className="text-slate-400"> · {chain.category}</span>
            <div className="text-[9px] text-slate-500">{chain.consensus}</div>
          </div>
        ) : (
          <span className="text-[10px] font-mono font-bold text-slate-200 drop-shadow" style={{ opacity: dimmed ? 0.4 : 1 }}>
            {chain.symbol}
          </span>
        )}
      </Html>
    </group>
  )
}

function Scene({ selected, onSelect }: Readonly<{ selected: string | null; onSelect: (id: string) => void }>) {
  const pos = useLayout()
  const group = useRef<THREE.Group>(null)
  useFrame((_, delta) => {
    // Rotación lenta que se pausa al seleccionar una cadena (para leer la ficha).
    if (group.current && !selected) group.current.rotation.y += delta * 0.08
  })

  const edges = useMemo(() => allEdges(), [])
  // Vecinos de la cadena seleccionada (para atenuar el resto).
  const neighbors = useMemo(() => {
    if (!selected) return null
    const set = new Set<string>([selected])
    edges.forEach((e) => {
      if (e.from === selected) set.add(e.to)
      if (e.to === selected) set.add(e.from)
    })
    return set
  }, [selected, edges])

  return (
    <group ref={group} onPointerMissed={() => onSelect('')}>
      {/* Aristas */}
      {edges.map((e, i) => {
        const a = pos.get(e.from), b = pos.get(e.to)
        if (!a || !b) return null
        const isSettle = e.kind === 'settlement'
        const touches = !selected || e.from === selected || e.to === selected
        return (
          <Line
            key={i}
            points={[[a.x, a.y, a.z], [b.x, b.y, b.z]]}
            color={isSettle ? '#2dd4bf' : '#f59e0b'}
            lineWidth={touches ? (isSettle ? 1.6 : 1.3) : 0.6}
            transparent
            opacity={touches ? (isSettle ? 0.6 : 0.45) : 0.12}
            dashed={!isSettle}
            dashScale={3}
          />
        )
      })}
      {/* Nodos */}
      {CHAINS.map((c) => {
        const p = pos.get(c.id)
        if (!p) return null
        return (
          <Node
            key={c.id}
            chain={c}
            pos={p}
            selected={selected === c.id}
            dimmed={!!neighbors && !neighbors.has(c.id)}
            onSelect={onSelect}
          />
        )
      })}
    </group>
  )
}

export default function BlockchainGraph3D({ selected, onSelect }: Readonly<{
  selected: string | null; onSelect: (id: string) => void
}>) {
  return (
    <Viz3DFrame camera={[0, 4, 14]} height={460} autoRotate={false} zoom>
      <Scene selected={selected} onSelect={onSelect} />
    </Viz3DFrame>
  )
}
