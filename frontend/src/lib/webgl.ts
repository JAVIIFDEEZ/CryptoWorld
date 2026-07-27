/**
 * lib/webgl.ts — Detección de soporte WebGL.
 *
 * El generador usa three.js para sus visualizaciones 3D; en navegadores o
 * dispositivos sin WebGL (o con la aceleración deshabilitada) caemos a vistas
 * 2D equivalentes en lugar de mostrar un lienzo en negro.
 */

let cached: boolean | null = null

export function isWebGLAvailable(): boolean {
  if (cached !== null) return cached
  try {
    const canvas = document.createElement('canvas')
    cached = !!(
      window.WebGLRenderingContext &&
      (canvas.getContext('webgl') || canvas.getContext('experimental-webgl'))
    )
  } catch {
    cached = false
  }
  return cached
}
