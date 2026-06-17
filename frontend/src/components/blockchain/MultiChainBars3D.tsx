/**
 * components/blockchain/MultiChainBars3D.tsx — Comparador multi-cadena 3D.
 *
 * Terreno de barras: filas = cadenas, columnas = métricas, altura = valor
 * normalizado (min-max por métrica), color por métrica. Compara de un vistazo
 * varias blockchains entre sí.
 */

import { useMemo, useState } from 'react'
import { Html } from '@react-three/drei'
import Viz3DFrame from '@/components/viz3d/Viz3DFrame'
import { METRIC_PALETTE, type CompareData } from './blockchainViz'

const W = 9

function Bars({ data }: Readonly<{ data: CompareData }>) {
  const nc = data.chains.length
  const nm = data.metrics.length
  const cellX = W / Math.max(1, nm)
  const cellZ = W / Math.max(1, nc)
  const offX = -W / 2 + cellX / 2
  const offZ = -W / 2 + cellZ / 2

  const bars = useMemo(() => {
    const out: { key: string; x: number; z: number; h: number; col: string; chain: string; metric: string; raw: number | null }[] = []
    for (let i = 0; i < nc; i++) {
      for (let j = 0; j < nm; j++) {
        const v = data.norm[i][j]
        if (v === null) continue
        out.push({
          key: `${i}-${j}`,
          x: offX + j * cellX,
          z: offZ + i * cellZ,
          h: 0.15 + v * 3.2,
          col: METRIC_PALETTE[j % METRIC_PALETTE.length],
          chain: data.chains[i],
          metric: data.metrics[j].label,
          raw: data.raw[i][j],
        })
      }
    }
    return out
  }, [data, nc, nm, cellX, cellZ, offX, offZ])

  return (
    <group position={[0, -1.6, 0]}>
      <gridHelper args={[W, Math.max(nc, nm), '#1e3a5f', '#14233d']} />
      {bars.map((b) => <BarMesh key={b.key} b={b} sx={cellX * 0.7} sz={cellZ * 0.7} />)}
      {data.chains.map((c, i) => (
        <Html key={`ch${c}`} position={[offX - cellX * 0.8, 0.1, offZ + i * cellZ]} center>
          <span className="text-[10px] font-semibold text-slate-300 whitespace-nowrap">{c}</span>
        </Html>
      ))}
    </group>
  )
}

function BarMesh({ b, sx, sz }: Readonly<{ b: { x: number; z: number; h: number; col: string; chain: string; metric: string; raw: number | null }; sx: number; sz: number }>) {
  const [hover, setHover] = useState(false)
  return (
    <group position={[b.x, 0, b.z]}>
      <mesh position={[0, b.h / 2, 0]} onPointerOver={(e) => { e.stopPropagation(); setHover(true) }} onPointerOut={() => setHover(false)}>
        <boxGeometry args={[sx, b.h, sz]} />
        <meshStandardMaterial color={b.col} emissive={b.col} emissiveIntensity={hover ? 0.7 : 0.3} roughness={0.5} />
      </mesh>
      {hover && (
        <Html position={[0, b.h + 0.3, 0]} center distanceFactor={10}>
          <div className="px-2 py-1 rounded-md bg-slate-900/95 border border-slate-600 text-[10px] text-slate-200 whitespace-nowrap shadow-xl pointer-events-none">
            {b.chain} · {b.metric}
          </div>
        </Html>
      )}
    </group>
  )
}

export default function MultiChainBars3D({ data }: Readonly<{ data: CompareData }>) {
  if (data.chains.length < 2 || data.metrics.length === 0) {
    return <div className="text-slate-500 text-sm text-center py-16">Datos insuficientes para comparar cadenas.</div>
  }
  return (
    <div className="relative">
      <Viz3DFrame camera={[8, 7, 9]} height={440}>
        <Bars data={data} />
      </Viz3DFrame>
      <div className="absolute top-3 right-3 flex flex-col gap-0.5 pointer-events-none">
        {data.metrics.map((m, j) => (
          <div key={m.key} className="flex items-center gap-1.5 text-[10px] text-slate-300 justify-end">
            <span className="w-2 h-2 rounded-sm" style={{ background: METRIC_PALETTE[j % METRIC_PALETTE.length] }} />
            {m.label}
          </div>
        ))}
      </div>
    </div>
  )
}
