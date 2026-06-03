/**
 * hooks/useCountUp.ts — Anima un número desde 0 hasta su valor objetivo.
 *
 * Usa requestAnimationFrame con easing suave (easeOutCubic). Si el usuario
 * tiene activada la preferencia "reducir movimiento", devuelve el valor
 * final de inmediato sin animar. Reanima cuando cambia el objetivo.
 */

import { useEffect, useRef, useState } from 'react'

const prefersReducedMotion = () =>
  typeof window !== 'undefined' &&
  window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3)

export function useCountUp(target: number, durationMs = 700): number {
  const [value, setValue] = useState(() => (prefersReducedMotion() ? target : 0))
  const fromRef = useRef(0)
  const rafRef = useRef<number>(0)

  useEffect(() => {
    if (prefersReducedMotion() || !Number.isFinite(target)) {
      setValue(target)
      return
    }

    const from = fromRef.current
    const start = performance.now()

    const tick = (now: number) => {
      const progress = Math.min((now - start) / durationMs, 1)
      const current = from + (target - from) * easeOutCubic(progress)
      setValue(current)
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(tick)
      } else {
        fromRef.current = target
      }
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafRef.current)
  }, [target, durationMs])

  return value
}
