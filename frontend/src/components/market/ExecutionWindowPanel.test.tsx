/**
 * ExecutionWindowPanel.test.tsx — Que el panel no diga lo contrario de lo que mide.
 *
 * Dos modos de fallo caros, los dos cubiertos aquí:
 *
 * 1. **Que «sin datos» o «sin base» se pinte como si fuera algo bueno.** Un gris
 *    que parece verde se lee como «momento favorable», y eso es peor que no pintar
 *    nada.
 * 2. **Que una casilla sin base se vea igual que una de actividad media.** Lo
 *    primero es «no se sabe» y lo segundo «es normal»; confundirlos es exactamente
 *    el error que el panel existe para no cometer.
 */

import { describe, it, expect } from 'vitest'
import {
  activityColor,
  countdown,
  importanceDot,
  verdictStyle,
} from './ExecutionWindowPanel'

describe('verdictStyle', () => {
  it('traduce cada veredicto a una etiqueta legible', () => {
    expect(verdictStyle('FAVORABLE').label).toBe('Momento favorable')
    expect(verdictStyle('ESPERAR').label).toBe('Esperar')
    expect(verdictStyle('DESFAVORABLE').label).toBe('Momento caro')
    expect(verdictStyle('EL_TAMANO_MANDA').label).toBe('El tamaño manda')
    expect(verdictStyle('SIN_BASE_HORARIA').label).toBe('Sin base horaria')
    expect(verdictStyle('SIN_DATOS').label).toBe('Sin datos')
  })

  it('ninguna etiqueta sugiere dirección', () => {
    // El modo de fallo de lectura: «favorable» tiene que significar «barato de
    // ejecutar», nunca «va a subir».
    const todos = (
      [
        'FAVORABLE',
        'NEUTRAL',
        'DESFAVORABLE',
        'ESPERAR',
        'EL_TAMANO_MANDA',
        'SIN_BASE_HORARIA',
        'SIN_DATOS',
      ] as const
    ).map((v) => verdictStyle(v).label.toLowerCase())
    for (const etiqueta of todos) {
      for (const prohibido of ['comprar', 'vender', 'alcista', 'bajista', 'sube']) {
        expect(etiqueta).not.toContain(prohibido)
      }
    }
  })

  it('«esperar» avisa en rojo y «favorable» en verde', () => {
    expect(verdictStyle('ESPERAR').cls).toContain('red')
    expect(verdictStyle('FAVORABLE').cls).toContain('emerald')
  })

  it('«el tamaño manda» es ámbar y no rojo', () => {
    // No dice que el momento sea malo: dice que la pregunta es otra y que esperar
    // no arregla nada. Pintarlo de rojo mandaría esperar.
    expect(verdictStyle('EL_TAMANO_MANDA').cls).toContain('amber')
    expect(verdictStyle('EL_TAMANO_MANDA').cls).not.toContain('red')
  })

  it('«sin base» y «sin datos» no se pintan como algo bueno', () => {
    for (const v of ['SIN_BASE_HORARIA', 'SIN_DATOS'] as const) {
      expect(verdictStyle(v).cls).not.toContain('emerald')
      expect(verdictStyle(v).cls).toContain('slate')
    }
  })
})

describe('activityColor', () => {
  it('cambia de color donde cambia la decisión', () => {
    // 1,25× es el punto en el que el movimiento extra se nota sobre el diferencial
    // típico; por debajo de 0,85× es una de las horas tranquilas.
    expect(activityColor(1.8)).toContain('red')
    expect(activityColor(1.3)).toContain('orange')
    expect(activityColor(0.95)).toContain('slate')
    expect(activityColor(0.5)).toContain('blue')
  })

  it('«sin base» se ve distinto de «actividad media»', () => {
    // Es la confusión que importa: null es «no se sabe» y 1,0 es «es normal».
    expect(activityColor(null)).toBe('bg-slate-800/60')
    expect(activityColor(null)).not.toBe(activityColor(1.0))
    expect(activityColor(Number.NaN)).toBe(activityColor(null))
  })

  it('es monótono: más actividad nunca se pinta más frío', () => {
    const orden = [0.4, 0.7, 0.9, 1.1, 1.3, 1.8]
    const colores = orden.map(activityColor)
    expect(new Set(colores).size).toBe(orden.length)
  })
})

describe('countdown', () => {
  it('usa minutos por debajo de la hora', () => {
    expect(countdown(0.5)).toBe('30 min')
  })

  it('usa horas dentro del día', () => {
    expect(countdown(7)).toBe('7 h')
    expect(countdown(23.4)).toBe('23 h')
  })

  it('usa días y horas más allá', () => {
    expect(countdown(26)).toBe('1 d 2 h')
    expect(countdown(48)).toBe('2 d')
  })

  it('no imprime una cuenta atrás negativa', () => {
    // La ventana propuesta nunca es pasada, pero si lo fuera por un desfase de
    // reloj, «-3 h» se leería como un error de la aplicación.
    expect(countdown(0)).toBe('ahora')
    expect(countdown(-5)).toBe('ahora')
    expect(countdown(Number.NaN)).toBe('ahora')
  })
})

describe('importanceDot', () => {
  it('la importancia alta destaca sobre la baja', () => {
    expect(importanceDot('alta')).toContain('red')
    expect(importanceDot('media')).toContain('amber')
    expect(importanceDot('baja')).toContain('slate')
  })

  it('una importancia desconocida no se pinta como alta', () => {
    expect(importanceDot('inventada')).toBe(importanceDot('baja'))
  })
})
