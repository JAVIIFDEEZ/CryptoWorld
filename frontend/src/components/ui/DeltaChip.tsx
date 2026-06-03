/**
 * components/ui/DeltaChip.tsx — Chip de variación porcentual.
 *
 * Muestra un cambio (ej. +6.4% / -1.8%) con color semántico y un
 * fondo tenue. Verde para subidas, rojo para bajadas, ámbar para 0.
 */

import { formatPercent } from '@/utils/format'

interface DeltaChipProps {
  value: number | string | null | undefined
  /** Tamaño compacto para tablas. */
  size?: 'sm' | 'md'
  /** Muestra una flecha de dirección. */
  arrow?: boolean
  className?: string
}

export default function DeltaChip({ value, size = 'md', arrow = false, className = '' }: DeltaChipProps) {
  const n = value === null || value === undefined || value === '' ? null : parseFloat(String(value))
  if (n === null || Number.isNaN(n)) {
    return <span className="text-slate-500 text-xs">—</span>
  }

  const tone =
    n > 0
      ? 'bg-positive-soft text-positive'
      : n < 0
        ? 'bg-negative-soft text-negative'
        : 'bg-caution-soft text-caution'

  const dims = size === 'sm' ? 'text-[11px] px-1.5 py-0.5' : 'text-xs px-2 py-1'

  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded-md font-medium tabular-nums ${tone} ${dims} ${className}`}
    >
      {arrow && <span aria-hidden>{n > 0 ? '▲' : n < 0 ? '▼' : '–'}</span>}
      {formatPercent(n)}
    </span>
  )
}
