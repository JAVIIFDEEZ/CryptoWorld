/**
 * components/Sparkline.tsx — Mini gráfico de línea SVG para sparklines.
 *
 * Acepta un array de valores numéricos y dibuja una línea poligonal
 * con área de relleno. Sin ejes, sin etiquetas — puramente visual.
 */

interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  positive?: boolean  // verde si positive, rojo si false, auto-detectado si undefined
}

export default function Sparkline({ data, width = 80, height = 28, positive }: SparklineProps) {
  if (!data || data.length < 2) {
    return <span className="text-slate-600 text-xs">—</span>
  }

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const padding = 2
  const innerW = width - padding * 2
  const innerH = height - padding * 2

  const points = data.map((val, i) => {
    const x = padding + (i / (data.length - 1)) * innerW
    const y = padding + innerH - ((val - min) / range) * innerH
    return `${x},${y}`
  })

  // Determinar color por primer vs último valor si no se especifica
  const isPositive = positive !== undefined ? positive : data[data.length - 1] >= data[0]
  const strokeColor = isPositive ? '#34d399' : '#f87171'   // emerald-400 : red-400
  const fillColor = isPositive ? '#34d39920' : '#f8717120'

  // Área de relleno: cerrar el path hasta la base
  const lastX = padding + innerW
  const firstX = padding
  const baseY = padding + innerH

  const areaPath =
    `M ${firstX},${baseY} ` +
    points.map((p) => `L ${p}`).join(' ') +
    ` L ${lastX},${baseY} Z`

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="inline-block"
      aria-hidden="true"
    >
      {/* Área de relleno */}
      <path d={areaPath} fill={fillColor} />
      {/* Línea */}
      <polyline
        points={points.join(' ')}
        fill="none"
        stroke={strokeColor}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
