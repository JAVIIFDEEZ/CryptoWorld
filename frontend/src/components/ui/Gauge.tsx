/**
 * components/ui/Gauge.tsx — Medidor semicircular tipo "Fear & Greed".
 *
 * Representa un valor 0–100 sobre un arco de tres zonas (rojo = miedo,
 * ámbar = neutral, verde = codicia) con una aguja que apunta al valor.
 * Es la representación canónica del índice de sentimiento de mercado.
 */

interface GaugeProps {
  /** Valor 0–100. */
  value: number
  /** Etiqueta de clasificación (ej. "Miedo", "Codicia extrema"). */
  label?: string
  width?: number
}

const CX = 100
const CY = 100
const R = 80

// Convierte un valor 0–100 a coordenadas sobre el semicírculo superior.
function pointAt(value: number, radius: number): [number, number] {
  const angle = Math.PI - (value / 100) * Math.PI // 180° (izq) → 0° (der)
  const x = CX + radius * Math.cos(angle)
  const y = CY - radius * Math.sin(angle)
  return [x, y]
}

function arc(fromValue: number, toValue: number): string {
  const [x1, y1] = pointAt(fromValue, R)
  const [x2, y2] = pointAt(toValue, R)
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${R} ${R} 0 0 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`
}

function colorFor(value: number): string {
  if (value <= 33) return '#ef4444'
  if (value <= 66) return '#eab308'
  return '#22c55e'
}

export default function Gauge({ value, label, width = 168 }: GaugeProps) {
  const v = Math.max(0, Math.min(100, value))
  const [nx, ny] = pointAt(v, R - 16)
  const valueColor = colorFor(v)

  return (
    <div className="flex flex-col items-center" style={{ width }}>
      <svg width={width} height={width * 0.62} viewBox="0 0 200 124" role="img" aria-label={`Índice ${v} de 100${label ? `, ${label}` : ''}`}>
        {/* Pista de fondo */}
        <path d={arc(0, 100)} fill="none" stroke="#1e293b" strokeWidth={14} strokeLinecap="round" />
        {/* Zonas de color */}
        <path d={arc(0, 33)} fill="none" stroke="#ef4444" strokeWidth={14} strokeLinecap="round" />
        <path d={arc(34, 66)} fill="none" stroke="#eab308" strokeWidth={14} strokeLinecap="round" />
        <path d={arc(67, 100)} fill="none" stroke="#22c55e" strokeWidth={14} strokeLinecap="round" />
        {/* Aguja */}
        <line x1={CX} y1={CY} x2={nx.toFixed(2)} y2={ny.toFixed(2)} stroke="#f1f5f9" strokeWidth={3} strokeLinecap="round" />
        <circle cx={CX} cy={CY} r={5} fill="#f1f5f9" />
        {/* Valor */}
        <text x={CX} y={CY - 22} textAnchor="middle" fontSize={30} fontWeight={700} fill={valueColor} fontFamily="JetBrains Mono, monospace">
          {Math.round(v)}
        </text>
      </svg>
      {label && <p className="text-xs text-slate-400 -mt-1">{label}</p>}
    </div>
  )
}
