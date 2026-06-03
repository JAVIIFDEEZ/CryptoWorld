/**
 * components/ui/AnimatedNumber.tsx — Número con animación count-up.
 *
 * Envoltorio fino sobre useCountUp para usar en cualquier punto donde
 * no se quiera el contenedor de StatCard (KPIs del Portfolio, total del
 * donut, etc.). Respeta `prefers-reduced-motion` vía el hook.
 */

import { useCountUp } from '@/hooks/useCountUp'

interface AnimatedNumberProps {
  value: number
  format?: (n: number) => string
  durationMs?: number
  className?: string
}

export default function AnimatedNumber({ value, format, durationMs, className }: AnimatedNumberProps) {
  const animated = useCountUp(value, durationMs)
  return <span className={className}>{format ? format(animated) : Math.round(animated).toLocaleString('en-US')}</span>
}
