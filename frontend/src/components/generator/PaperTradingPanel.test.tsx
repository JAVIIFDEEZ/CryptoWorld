/**
 * PaperTradingPanel.test.tsx — Que el «no» de la puerta del dinero se explique.
 *
 * Esta es la pantalla desde la que se cruza al capital real. El backend responde
 * con un 409 que detalla cada requisito que falta y el plazo estimado, y ese
 * detalle se descartaba en un `catch` vacío: el usuario pulsaba «Activar», no
 * ocurría nada y nadie le decía por qué.
 *
 * Los tests cubren los dos modos de fallo que importan:
 *
 * 1. **Que el error se tragué en silencio.** Cualquier fallo —incluido uno que no
 *    sea de incubación— tiene que producir un mensaje legible, nunca `null`.
 * 2. **Que se publique un plazo absurdo.** El MinTRL diverge cuando el Sharpe
 *    observado roza el umbral; el backend deja de dar cifra y aquí hay que decir lo
 *    que implica en lugar de inventar una fecha.
 */

import { describe, it, expect } from 'vitest'
import {
  missingLabel,
  readIncubationBlock,
  runwayText,
  type IncubationBlock,
} from './PaperTradingPanel'

function error409(incubation: Record<string, unknown>) {
  return { response: { status: 409, data: { blocked_by: 'incubation', incubation } } }
}

describe('readIncubationBlock', () => {
  it('extrae lo que falta y el bloque estadístico', () => {
    const b = readIncubationBlock(
      error409({
        note: 'Incubación no superada: faltan 6 días de simulado.',
        missing: ['min_days', 'statistical_edge'],
        days_remaining: 6,
        trades_remaining: 0,
        statistical: {
          psr: 0.62,
          min_psr: 0.95,
          days_remaining_estimate: 48,
          runway_beyond_horizon: false,
          observations: 30,
          observations_required: 14,
        },
      }),
    )
    expect(b.missing).toEqual(['min_days', 'statistical_edge'])
    expect(b.psr).toBe(0.62)
    expect(b.min_psr).toBe(0.95)
    expect(b.days_remaining_estimate).toBe(48)
    expect(b.note).toContain('6 días')
  })

  it('nunca devuelve null: un error sin detalle da un mensaje legible', () => {
    // Es el defecto que se está corrigiendo. Si esto devolviera null, la interfaz
    // quedaría igual que con el `catch` vacío.
    for (const err of [
      {},
      null,
      undefined,
      { response: { status: 500, data: {} } },
      new Error('network'),
    ]) {
      const b = readIncubationBlock(err)
      expect(b.note.length).toBeGreaterThan(0)
      expect(b.missing).toEqual([])
    }
  })

  it('usa el campo error del backend cuando no es un bloqueo de incubación', () => {
    const b = readIncubationBlock({
      response: { status: 400, data: { error: 'Conexión de exchange no encontrada.' } },
    })
    expect(b.note).toContain('Conexión de exchange')
  })

  it('tolera un bloque estadístico ausente o incompleto', () => {
    const b = readIncubationBlock(error409({ note: 'x', missing: ['min_trades'] }))
    expect(b.psr).toBeNull()
    expect(b.days_remaining_estimate).toBeNull()
    expect(b.runway_beyond_horizon).toBe(false)
  })
})

describe('missingLabel', () => {
  it('traduce el criterio estadístico a lo que significa', () => {
    // Es el requisito que de verdad importa y el que nadie entendería por su
    // nombre técnico.
    expect(missingLabel('statistical_edge')).toContain('ventaja')
    expect(missingLabel('statistical_edge')).not.toContain('statistical')
  })

  it('traduce los demás criterios', () => {
    expect(missingLabel('min_days')).toContain('simulado')
    expect(missingLabel('min_trades')).toBe('operaciones')
    expect(missingLabel('not_decayed')).toContain('degradado')
    expect(missingLabel('profitable')).toContain('P&L')
  })

  it('una clave desconocida se muestra tal cual en vez de desaparecer', () => {
    expect(missingLabel('criterio_nuevo')).toBe('criterio_nuevo')
  })
})

describe('runwayText', () => {
  const base: IncubationBlock = { note: '', missing: [] }

  it('cuando falta curva, dice cuántos días de curva faltan', () => {
    const t = runwayText({ ...base, observations: 5, observations_required: 14 })
    expect(t).toContain('9 días')
  })

  it('cuando hay plazo, lo da en días', () => {
    const t = runwayText({ ...base, days_remaining_estimate: 48 })
    expect(t).toContain('48')
  })

  it('cuando no converge, dice que el problema no es esperar', () => {
    // El mensaje tiene que redirigir al Sharpe, no a la paciencia: es la
    // diferencia entre una barrera con plazo y una espera sin final.
    const t = runwayText({ ...base, runway_beyond_horizon: true })
    expect(t).toContain('no converge')
    expect(t).toContain('Sharpe')
  })

  it('nunca inventa un plazo cuando no hay ninguno', () => {
    expect(runwayText(base)).toBeNull()
    expect(runwayText({ ...base, days_remaining_estimate: 0 })).toBeNull()
  })

  it('la falta de curva manda sobre el plazo estimado', () => {
    // Si aún no hay serie que contrastar, hablar de «48 días más» sugeriría que el
    // contraste ya se hizo y salió corto.
    const t = runwayText({
      ...base, observations: 3, observations_required: 14, days_remaining_estimate: 48,
    })
    expect(t).toContain('para poder evaluarlo')
  })
})
