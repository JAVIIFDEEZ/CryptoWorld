/**
 * webgl.test.ts — Detección de WebGL.
 *
 * En jsdom no hay contexto WebGL, así que la detección debe devolver false y
 * cachear el resultado (no recrear el canvas en cada llamada).
 */

import { describe, it, expect, vi } from 'vitest'
import { isWebGLAvailable } from './webgl'

describe('isWebGLAvailable', () => {
  it('returns false in a jsdom environment without WebGL', () => {
    expect(isWebGLAvailable()).toBe(false)
  })

  it('caches the result (no new canvas on repeated calls)', () => {
    const spy = vi.spyOn(document, 'createElement')
    isWebGLAvailable()
    isWebGLAvailable()
    // Ya cacheado de la prueba anterior: no debe crear ningún canvas nuevo
    expect(spy).not.toHaveBeenCalledWith('canvas')
    spy.mockRestore()
  })
})
