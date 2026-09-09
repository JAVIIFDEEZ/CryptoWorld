/**
 * PredictTab.test.tsx — La escala de la barra de importancia.
 *
 * La métrica que alimenta esta lista cambió de significado: era MDI —un reparto
 * dentro de muestra que suma 1— y ahora es MDA, puntos de precisión perdidos al
 * permutar el grupo fuera de muestra. El cambio importa aquí porque **MDA puede
 * ser negativo**, y la fórmula anterior (`valor / primero`) producía entonces un
 * `width` negativo que el navegador descarta: la barra quedaba a cero y el grupo
 * parecía irrelevante, que es justo lo contrario de lo que dice el dato.
 */

import { describe, it, expect } from 'vitest'
import { importanceBarWidth } from './PredictTab'

const grupos = (...v: number[]) => v.map((importance) => ({ importance }))

describe('importanceBarWidth', () => {
  it('da el carril completo al grupo de mayor magnitud', () => {
    const todos = grupos(0.12, 0.03, 0.001)
    expect(importanceBarWidth(0.12, todos)).toBe(100)
  })

  it('escala el resto proporcionalmente', () => {
    const todos = grupos(0.10, 0.05)
    expect(importanceBarWidth(0.05, todos)).toBeCloseTo(50)
  })

  it('pinta las caídas negativas con su magnitud, no a cero', () => {
    // El caso que rompía la fórmula anterior: romper el grupo MEJORA el acierto.
    const todos = grupos(0.10, -0.10)
    expect(importanceBarWidth(-0.10, todos)).toBe(100)
  })

  it('nunca devuelve un ancho negativo', () => {
    const todos = grupos(0.10, -0.04)
    expect(importanceBarWidth(-0.04, todos)).toBeGreaterThan(0)
  })

  it('no se pasa del carril aunque el valor supere al máximo declarado', () => {
    expect(importanceBarWidth(5, grupos(1))).toBeLessThanOrEqual(100)
  })

  it('sobrevive a una lista donde todo vale cero', () => {
    // Ocurre cuando ningún grupo mueve la precisión: dividir por el máximo sería
    // dividir por cero y dejar NaN en el atributo `width`.
    expect(importanceBarWidth(0, grupos(0, 0, 0))).toBe(0)
  })

  it('sobrevive a una lista vacía', () => {
    expect(importanceBarWidth(0.1, [])).toBe(0)
  })
})
