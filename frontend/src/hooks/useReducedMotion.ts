/**
 * lib/useReducedMotion.ts — Hook de preferencia de movimiento reducido.
 *
 * Respeta `prefers-reduced-motion` del sistema operativo: cuando el usuario pide
 * menos animación, las visualizaciones 3D desactivan la rotación automática y los
 * giros continuos (accesibilidad / confort vestibular).
 */

import { useEffect, useState } from 'react'

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    setReduced(mq.matches)
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches)
    mq.addEventListener?.('change', handler)
    return () => mq.removeEventListener?.('change', handler)
  }, [])

  return reduced
}
