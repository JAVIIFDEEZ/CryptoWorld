/**
 * components/learn/BlockchainGraph2D.tsx — Fallback 2D del grafo de blockchains.
 *
 * Mismo dataset que el grafo 3D, dibujado en SVG: las L1 en un anillo, las
 * L2/sidechains agrupadas junto a Ethereum, y las conexiones (liquidación en
 * verde-azulado, puentes en ámbar) como líneas. Sin WebGL, misma información.
 */

import { useMemo } from 'react'
import { CHAINS, allEdges, nodeRadius2D, type ChainNode } from '@/data/learnData'

const W = 640, H = 460, CX = W / 2, CY = H / 2

function positions(): Map<string, { x: number; y: number }> {
  const pos = new Map<string, { x: number; y: number }>()
  const l1 = CHAINS.filter((c) => c.category === 'L1')
  const R = 170
  l1.forEach((c, i) => {
    const a = (i / l1.length) * Math.PI * 2 - Math.PI / 2
    pos.set(c.id, { x: CX + Math.cos(a) * R, y: CY + Math.sin(a) * R })
  })
  const eth = pos.get('ethereum') ?? { x: CX, y: CY }
  const stacked = CHAINS.filter((c) => c.settlesOn === 'ethereum')
  stacked.forEach((c, k) => {
    const a = k * 2.399963
    // Acercar el racimo de L2 hacia el centro respecto a Ethereum.
    const toward = 62
    const bx = eth.x + (CX - eth.x) * 0.42
    const by = eth.y + (CY - eth.y) * 0.42
    pos.set(c.id, { x: bx + Math.cos(a) * toward, y: by + Math.sin(a) * toward })
  })
  return pos
}

export default function BlockchainGraph2D({ selected, onSelect }: Readonly<{
  selected: string | null; onSelect: (id: string) => void
}>) {
  const pos = useMemo(positions, [])
  const edges = useMemo(() => allEdges(), [])
  const neighbors = useMemo(() => {
    if (!selected) return null
    const set = new Set<string>([selected])
    edges.forEach((e) => {
      if (e.from === selected) set.add(e.to)
      if (e.to === selected) set.add(e.from)
    })
    return set
  }, [selected, edges])

  const dim = (id: string) => !!neighbors && !neighbors.has(id)

  return (
    <div
      className="rounded-xl overflow-hidden border border-slate-700/60 bg-[radial-gradient(ellipse_at_center,#0b1426_0%,#070b14_70%)]"
      style={{ height: H }}
    >
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-full" role="img" aria-label="Grafo de blockchains y puentes">
        <rect x={0} y={0} width={W} height={H} fill="transparent" onClick={() => onSelect('')} />
        {/* Aristas */}
        {edges.map((e, i) => {
          const a = pos.get(e.from), b = pos.get(e.to)
          if (!a || !b) return null
          const settle = e.kind === 'settlement'
          const touches = !selected || e.from === selected || e.to === selected
          return (
            <line
              key={i}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={settle ? '#2dd4bf' : '#f59e0b'}
              strokeWidth={touches ? 1.6 : 0.6}
              strokeOpacity={touches ? (settle ? 0.55 : 0.4) : 0.1}
              strokeDasharray={settle ? undefined : '5 4'}
            />
          )
        })}
        {/* Nodos */}
        {CHAINS.map((c: ChainNode) => {
          const p = pos.get(c.id)
          if (!p) return null
          const r = nodeRadius2D(c)
          const isSel = selected === c.id
          const d = dim(c.id)
          return (
            <g
              key={c.id}
              transform={`translate(${p.x},${p.y})`}
              className="cursor-pointer"
              onClick={(ev) => { ev.stopPropagation(); onSelect(c.id) }}
              opacity={d ? 0.4 : 1}
            >
              {isSel && <circle r={r + 6} fill={c.color} opacity={0.18} />}
              <circle r={r} fill={c.color} stroke={isSel ? '#fff' : c.color} strokeWidth={isSel ? 2 : 0} fillOpacity={0.9} />
              <text y={-r - 5} textAnchor="middle" className="fill-slate-200 font-mono" fontSize={11} fontWeight={700}>
                {c.symbol}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}
