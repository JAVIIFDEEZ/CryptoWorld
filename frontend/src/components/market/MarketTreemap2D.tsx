/**
 * components/market/MarketTreemap2D.tsx — Mapa de calor del mercado (treemap 2D).
 *
 * Rectángulos dimensionados por capitalización y coloreados por la variación 24h
 * (rojo→verde). Alternativa 2D del universo 3D; a menudo lee mejor el "mapa" del
 * mercado de un vistazo.
 */

import { Treemap, ResponsiveContainer } from 'recharts'
import { changeColor, type MarketBody } from './marketViz'

interface TreemapDatum {
  [key: string]: string | number
  name: string
  size: number
  change: number
}

interface ContentProps {
  x?: number
  y?: number
  width?: number
  height?: number
  name?: string
  change?: number
  onSelect: (s: string) => void
}

function Cell({ x = 0, y = 0, width = 0, height = 0, name = '', change = 0, onSelect }: ContentProps) {
  const showLabel = width > 44 && height > 26
  return (
    <g onClick={() => name && onSelect(name)} style={{ cursor: name ? 'pointer' : 'default' }}>
      <rect x={x} y={y} width={width} height={height} fill={changeColor(change)} stroke="#0f172a" strokeWidth={1.5} />
      {showLabel && (
        <>
          <text x={x + width / 2} y={y + height / 2 - 3} textAnchor="middle" fill="#fff" fontSize={Math.min(14, width / 4)} fontWeight={700}>
            {name}
          </text>
          <text x={x + width / 2} y={y + height / 2 + 12} textAnchor="middle" fill="rgba(255,255,255,0.85)" fontSize={Math.min(11, width / 5)}>
            {change >= 0 ? '+' : ''}{change.toFixed(1)}%
          </text>
        </>
      )}
    </g>
  )
}

export default function MarketTreemap2D({ bodies, onSelect }: Readonly<{ bodies: MarketBody[]; onSelect: (s: string) => void }>) {
  if (!bodies.length) {
    return <div className="text-slate-500 text-sm text-center py-16">Sin datos de mercado para visualizar.</div>
  }
  const data: TreemapDatum[] = bodies.map((b) => ({ name: b.symbol, size: b.marketCap, change: b.change }))
  return (
    <div className="rounded-xl border border-slate-700/70 bg-slate-900/40 p-2" style={{ height: 460 }}>
      <ResponsiveContainer width="100%" height="100%">
        <Treemap
          data={data}
          dataKey="size"
          stroke="#0f172a"
          isAnimationActive={false}
          content={<Cell onSelect={onSelect} />}
        />
      </ResponsiveContainer>
    </div>
  )
}
