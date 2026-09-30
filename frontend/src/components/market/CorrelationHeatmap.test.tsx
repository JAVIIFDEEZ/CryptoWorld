/**
 * CorrelationHeatmap.test.tsx — Que el degradado no diga más de lo que sabe.
 *
 * El modo de fallo caro de un mapa de calor no es equivocar un color: es que
 * alguien lea una diferencia que es ruido, o que cuente las celdas marcadas sin
 * saber cuántas se esperan por azar. Los dos casos se cubren aquí.
 */

import { describe, it, expect } from 'vitest'
import { cellColor, expectedFalseMarks, verdictStyle } from './CorrelationHeatmap'

describe('cellColor', () => {
  it('cambia de color donde cambia la decisión', () => {
    // Por encima de 0,7 la diversificación entre esos dos activos es casi nula;
    // por debajo de 0,3 hay riesgo distinto de verdad. Los cortes caen ahí.
    expect(cellColor(0.95)).toContain('red-600')
    expect(cellColor(0.75)).toContain('red-500')
    expect(cellColor(0.4)).toContain('amber')
    expect(cellColor(0.0)).toContain('slate')
  })

  it('distingue la correlación negativa, que es la que de verdad diversifica', () => {
    expect(cellColor(-0.8)).toContain('blue')
    expect(cellColor(-0.6)).toContain('sky')
  })

  it('es simétrico en torno a cero en la banda neutra', () => {
    expect(cellColor(0.1)).toBe(cellColor(-0.1))
  })

  it('no pinta un color cualquiera cuando el valor no es un número', () => {
    // Una celda sin datos tiene que verse distinta de una con correlación cero,
    // no igual.
    expect(cellColor(Number.NaN)).toBe('bg-slate-800')
    expect(cellColor(Number.NaN)).not.toBe(cellColor(0))
  })
})

describe('expectedFalseMarks', () => {
  it('cuenta las parejas y no los activos', () => {
    // Con 12 activos hay 66 parejas, no 12: es el número que hay que comparar
    // con las marcas que se ven.
    expect(expectedFalseMarks(12)).toBe(Math.round(66 * 0.05))
    expect(expectedFalseMarks(20)).toBe(Math.round(190 * 0.05))
  })

  it('con dos activos no espera ninguna marca falsa', () => {
    expect(expectedFalseMarks(2)).toBe(0)
  })

  it('crece de forma cuadrática, que es el motivo de publicarlo', () => {
    // Duplicar los activos cuadruplica las comparaciones y con ellas las marcas
    // espurias. Sin este número, el usuario leería veinte marcas como veinte
    // hallazgos.
    expect(expectedFalseMarks(40)).toBeGreaterThan(3 * expectedFalseMarks(20))
  })
})

describe('verdictStyle', () => {
  it('traduce cada veredicto a una etiqueta legible', () => {
    expect(verdictStyle('CONCENTRADO').label).toBe('Concentrado')
    expect(verdictStyle('REPARTIDO').label).toBe('Repartido')
    expect(verdictStyle('INTERMEDIO').label).toBe('Intermedio')
    expect(verdictStyle('SIN_DATOS').label).toBe('Sin datos')
  })

  it('el concentrado avisa en rojo y el repartido no', () => {
    expect(verdictStyle('CONCENTRADO').cls).toContain('red')
    expect(verdictStyle('REPARTIDO').cls).toContain('emerald')
  })

  it('«sin datos» no se pinta como si fuera un resultado bueno', () => {
    // Es la confusión que importa: la ausencia de datos en verde se lee como
    // «cartera diversificada».
    expect(verdictStyle('SIN_DATOS').cls).not.toContain('emerald')
    expect(verdictStyle('SIN_DATOS').cls).toContain('slate')
  })
})
