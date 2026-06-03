/**
 * components/ui/Skeleton.tsx — Placeholder animado para estados de carga.
 *
 * Usa el efecto shimmer (brillo deslizante) en lugar del simple pulse,
 * lo que da una apariencia más moderna y profesional.
 */

interface SkeletonProps {
  className?: string
}

export default function Skeleton({ className = '' }: SkeletonProps) {
  return (
    <div
      className={`cw-shimmer rounded-md ${className}`}
      aria-hidden
    />
  )
}

/** Fila de skeleton para listas de activos (tabla Market / Dashboard). */
export function SkeletonRow() {
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <div className="cw-shimmer w-8 h-8 rounded-full shrink-0" aria-hidden />
      <div className="flex-1 space-y-1.5">
        <div className="cw-shimmer h-3 w-20 rounded-md" aria-hidden />
        <div className="cw-shimmer h-2.5 w-28 rounded-md" aria-hidden />
      </div>
      <div className="cw-shimmer h-3 w-16 rounded-md" aria-hidden />
      <div className="cw-shimmer h-3 w-12 rounded-md" aria-hidden />
    </div>
  )
}
