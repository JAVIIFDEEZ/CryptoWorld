/**
 * components/portfolio/CorrelationMatrix3D.tsx — Matriz de correlación 3D.
 *
 * Cuadrícula NxN de columnas: altura y color = correlación 7d entre cada par de
 * holdings (azul = diversifica, rojo = se mueven juntos). Visualiza de un vistazo
 * la diversificación real de la cartera.
 */

import { useMemo } from 'react'
import { Html } from '@react-three/drei'
import Viz3DFrame from '@/components/viz3d/Viz3DFrame'
import { correlationColor, type CorrelationData } from './portfolioViz'

const GRID = 7 // ancho del tablero en unidades de escena

function Board({ data }: Readonly<{ data: CorrelationData }>) {
  const n = data.symbols.length
  const cell = GRID / n
  const off = -GRID / 2 + cell / 2

  const bars = useMemo(() => {
    const out: { key: string; x: number; z: number; h: number; col: string }[] = []
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const c = data.matrix[i][j]
        out.push({
          key: `${i}-${j}`,
          x: off + j * cell,
          z: off + i * cell,
          h: 0.1 + Math.abs(c) * 2.6,
          col: correlationColor(c),
        })
      }
    }
    return out
  }, [data, n, cell, off])

  return (
    <group>
      <gridHelper args={[GRID, n, '#1e3a5f', '#14233d']} position={[0, 0, 0]} />
      {bars.map((b) => (
        <mesh key={b.key} position={[b.x, b.h / 2, b.z]}>
          <boxGeometry args={[cell * 0.8, b.h, cell * 0.8]} />
          <meshStandardMaterial color={b.col} emissive={b.col} emissiveIntensity={0.3} roughness={0.5} />
        </mesh>
      ))}
      {data.symbols.map((s, i) => (
        <Html key={`r${s}`} position={[off - cell * 0.7, 0.1, off + i * cell]} center>
          <span className="text-[9px] text-slate-400 whitespace-nowrap">{s}</span>
        </Html>
      ))}
      {data.symbols.map((s, j) => (
        <Html key={`c${s}`} position={[off + j * cell, 0.1, off - cell * 0.7]} center>
          <span className="text-[9px] text-slate-400 whitespace-nowrap">{s}</span>
        </Html>
      ))}
    </group>
  )
}

export default function CorrelationMatrix3D({ data }: Readonly<{ data: CorrelationData }>) {
  if (data.symbols.length < 2) {
    return <div className="text-slate-500 text-sm text-center py-16">Necesitas al menos 2 posiciones con histórico.</div>
  }
  return (
    <div className="relative">
      <Viz3DFrame camera={[6, 7, 8]} height={420}>
        <Board data={data} />
      </Viz3DFrame>
      <div className="absolute top-3 right-3 text-[10px] text-slate-400 pointer-events-none text-right">
        <span className="text-blue-300">azul</span> = diversifica · <span className="text-red-300">rojo</span> = se mueven juntos
      </div>
    </div>
  )
}
