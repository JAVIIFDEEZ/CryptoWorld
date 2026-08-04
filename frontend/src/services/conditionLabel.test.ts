/**
 * conditionLabel.test.ts — Etiqueta corta de una condición del spec.
 *
 * Las vistas gráficas (hélice 3D y diagrama 2D) tenían cada una su propia
 * versión de esta función, y ninguna de las dos conocía los tipos de condición
 * añadidos después: estado, pendiente y patrón salían como «undefined ↗
 * undefined». Una estrategia que el usuario no puede leer no la puede juzgar.
 */

import { describe, it, expect } from 'vitest'
import { combineLabel, conditionLabel } from './strategyGeneratorService'
import type { SpecCondition } from './strategyGeneratorService'

describe('conditionLabel', () => {
  it('describe un umbral', () => {
    const c: SpecCondition = { type: 'threshold', indicator: 'RSI', op: 'lt', threshold: 30 }
    expect(conditionLabel(c)).toBe('RSI < 30')
  })

  it('describe un cruce', () => {
    const c: SpecCondition = {
      type: 'cross', op: 'cross_above',
      a: { indicator: 'EMA', params: { window: 12 } },
      b: { indicator: 'EMA', params: { window: 26 } },
    }
    expect(conditionLabel(c)).toBe('EMA ↗ EMA')
  })

  it('describe un estado, que antes caía en la rama del cruce', () => {
    const c: SpecCondition = {
      type: 'compare', op: 'above',
      a: { indicator: 'PRICE', params: {} },
      b: { indicator: 'SMA', params: { window: 200 } },
    }
    expect(conditionLabel(c)).toBe('PRICE > SMA')
  })

  it('describe una pendiente', () => {
    const c: SpecCondition = { type: 'slope', indicator: 'WMA', op: 'rising', bars: 4 }
    expect(conditionLabel(c)).toBe('WMA ↗ 4v')
  })

  it('traduce el patrón y dice su ventana de vigencia', () => {
    const c: SpecCondition = { type: 'pattern', pattern: 'SWEEP_LOW', lookback: 4 }
    expect(conditionLabel(c)).toBe('barrida ↓ ≤4v')
  })

  it('omite la ventana cuando es de una sola vela', () => {
    const c: SpecCondition = { type: 'pattern', pattern: 'CRT', lookback: 1 }
    expect(conditionLabel(c)).toBe('CRT')
  })

  it('cae al nombre del patrón si no está traducido, nunca a undefined', () => {
    const c: SpecCondition = { type: 'pattern', pattern: 'PATRON_NUEVO', lookback: 1 }
    expect(conditionLabel(c)).toBe('PATRON_NUEVO')
  })

  it('no dice undefined ni con una condición de patrón vacía', () => {
    expect(conditionLabel({ type: 'pattern' })).not.toMatch(/undefined/)
  })
})

describe('conditionLabel — negación', () => {
  it('marca la condición negada', () => {
    expect(conditionLabel({ type: 'threshold', indicator: 'RSI', op: 'lt', threshold: 30, negate: true }))
      .toBe('¬RSI < 30')
  })

  it('no marca la que no lo está', () => {
    expect(conditionLabel({ type: 'threshold', indicator: 'RSI', op: 'lt', threshold: 30 }))
      .not.toContain('¬')
  })
})

describe('combineLabel', () => {
  it('deja AND y OR tal cual', () => {
    expect(combineLabel({ combine: 'AND', conditions: [] })).toBe('AND')
    expect(combineLabel({ combine: 'OR', conditions: [] })).toBe('OR')
  })

  it('lee «k de n» como confirmación parcial, no como una sigla', () => {
    expect(combineLabel({
      combine: 'K_OF_N', k: 2,
      conditions: [{ type: 'threshold' }, { type: 'threshold' }, { type: 'threshold' }],
    })).toBe('2 de 3')
  })
})
