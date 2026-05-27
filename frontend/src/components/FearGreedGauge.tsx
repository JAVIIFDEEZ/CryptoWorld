/**
 * components/FearGreedGauge.tsx — Gauge semicircular para el índice Fear & Greed.
 *
 * El índice va de 0 (Miedo extremo) a 100 (Codicia extrema).
 * Representación estándar: arco con gradiente rojo→amarillo→verde.
 */

interface FearGreedGaugeProps {
  value: number  // 0-100
  size?: number  // diámetro del gauge en px (default 120)
}

function getLabel(value: number): string {
  if (value >= 75) return 'Codicia extrema'
  if (value >= 55) return 'Codicia'
  if (value >= 45) return 'Neutral'
  if (value >= 25) return 'Miedo'
  return 'Miedo extremo'
}

function getColor(value: number): string {
  if (value >= 75) return '#22c55e'   // green-500
  if (value >= 55) return '#84cc16'   // lime-500
  if (value >= 45) return '#eab308'   // yellow-500
  if (value >= 25) return '#f97316'   // orange-500
  return '#ef4444'                     // red-500
}

export default function FearGreedGauge({ value, size = 120 }: FearGreedGaugeProps) {
  const clampedValue = Math.max(0, Math.min(100, value))

  // Arco semicircular: de 180° a 0° (izquierda a derecha)
  // Usamos un viewBox de 120x70 para mostrar solo la mitad superior
  const cx = 60
  const cy = 60
  const r = 48
  const strokeWidth = 10

  // Convertir valor (0-100) a ángulo: 0 → 180°, 100 → 0° (en radianes desde izquierda)
  const startAngle = Math.PI         // 180°
  const angle = startAngle - (clampedValue / 100) * Math.PI

  // Punto del indicador needle
  const needleX = cx + r * Math.cos(angle)
  const needleY = cy - r * Math.sin(angle)

  // Arco de fondo (gris)
  const bgStart = { x: cx - r, y: cy }
  const bgEnd = { x: cx + r, y: cy }

  // Segmentos de color del arco
  const segments = [
    { from: 0, to: 25, color: '#ef4444' },   // Miedo extremo - rojo
    { from: 25, to: 45, color: '#f97316' },  // Miedo - naranja
    { from: 45, to: 55, color: '#eab308' },  // Neutral - amarillo
    { from: 55, to: 75, color: '#84cc16' },  // Codicia - lima
    { from: 75, to: 100, color: '#22c55e' }, // Codicia extrema - verde
  ]

  function polarToCartesian(angle: number) {
    return {
      x: cx + r * Math.cos(angle),
      y: cy - r * Math.sin(angle),
    }
  }

  function describeArc(fromVal: number, toVal: number): string {
    const startA = Math.PI - (fromVal / 100) * Math.PI
    const endA = Math.PI - (toVal / 100) * Math.PI
    const start = polarToCartesian(startA)
    const end = polarToCartesian(endA)
    const largeArc = toVal - fromVal > 50 ? 1 : 0
    return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 1 ${end.x} ${end.y}`
  }

  const color = getColor(clampedValue)
  const label = getLabel(clampedValue)

  return (
    <div className="flex flex-col items-center">
      <svg
        width={size}
        height={size * 0.6}
        viewBox="0 0 120 72"
        className="overflow-visible"
      >
        {/* Arco de fondo */}
        <path
          d={`M ${bgStart.x} ${bgStart.y} A ${r} ${r} 0 0 1 ${bgEnd.x} ${bgEnd.y}`}
          fill="none"
          stroke="#1e293b"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />

        {/* Segmentos de color */}
        {segments.map((seg) => (
          <path
            key={seg.from}
            d={describeArc(seg.from, seg.to)}
            fill="none"
            stroke={seg.color}
            strokeWidth={strokeWidth - 2}
            opacity={0.85}
          />
        ))}

        {/* Indicador (needle): línea desde centro hasta el arco */}
        <line
          x1={cx}
          y1={cy}
          x2={needleX}
          y2={needleY}
          stroke={color}
          strokeWidth={2.5}
          strokeLinecap="round"
        />
        {/* Centro del gauge */}
        <circle cx={cx} cy={cy} r={4} fill={color} />

        {/* Valor numérico */}
        <text
          x={cx}
          y={cy - 14}
          textAnchor="middle"
          fontSize="16"
          fontWeight="bold"
          fill="white"
          fontFamily="ui-monospace, monospace"
        >
          {clampedValue}
        </text>
      </svg>

      {/* Etiqueta de sentimiento */}
      <p className="text-xs font-medium mt-1" style={{ color }}>
        {label}
      </p>
    </div>
  )
}
