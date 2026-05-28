/**
 * components/ui/Sparkline.tsx — Minigráfico de línea para tendencias.
 *
 * Dibuja una serie de precios como una polilínea SVG compacta, sin ejes
 * ni etiquetas. El color se deriva automáticamente de la tendencia
 * (verde si el último valor supera al primero, rojo en caso contrario),
 * o se puede forzar con la prop `color`.
 */

interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  /** Color de línea explícito. Si se omite, se infiere de la tendencia. */
  color?: string
  /** Rellena el área bajo la línea con una versión tenue del color. */
  fill?: boolean
  className?: string
}

export default function Sparkline({
  data,
  width = 96,
  height = 28,
  color,
  fill = true,
  className = '',
}: SparklineProps) {
  if (!data || data.length < 2) {
    return <div style={{ width, height }} className={className} aria-hidden />
  }

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const pad = 2

  const points = data.map((value, i) => {
    const x = (i / (data.length - 1)) * (width - pad * 2) + pad
    const y = height - pad - ((value - min) / range) * (height - pad * 2)
    return [x, y] as const
  })

  const trendUp = data[data.length - 1] >= data[0]
  const stroke = color ?? (trendUp ? '#22c55e' : '#ef4444')
  const line = points.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' ')
  const area =
    `${pad},${height - pad} ` + line + ` ${width - pad},${height - pad}`

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={className}
      role="img"
      aria-label={trendUp ? 'Tendencia al alza' : 'Tendencia a la baja'}
    >
      {fill && (
        <polygon points={area} fill={stroke} fillOpacity={0.1} stroke="none" />
      )}
      <polyline
        points={line}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  )
}
