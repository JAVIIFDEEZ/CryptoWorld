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
import { importanceBarWidth, neutralReason } from './PredictTab'

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

describe('neutralReason', () => {
  const conformal = (status: string) => ({
    available: true,
    min_proba: 0.213,
    prediction_set: { status },
  })

  it('distingue «no distingue» de «no reconoce el terreno»', () => {
    // Antes había un solo motivo posible y los dos se contaban igual. El segundo
    // merece más cautela, no la misma.
    const ambos = neutralReason({ prob_up: 0.51, conformal: conformal('AMBOS') })
    const vacio = neutralReason({ prob_up: 0.51, conformal: conformal('VACIO') })
    expect(ambos).not.toBe(vacio)
    expect(ambos).toContain('no distingue')
    expect(vacio).toContain('no reconoce el terreno')
  })

  it('dice que el umbral no es una constante elegida', () => {
    expect(neutralReason({ prob_up: 0.51, conformal: conformal('AMBOS') }))
      .toContain('tasa de error')
  })

  it('muestra el umbral calibrado, no el 5 % fijo', () => {
    expect(neutralReason({ prob_up: 0.51, conformal: conformal('AMBOS') }))
      .toContain('21.3%')
  })

  it('cae al texto de la banda fija cuando no hay conformal', () => {
    // Con poca muestra el umbral no se calibra y la regla anterior sigue
    // gobernando: el texto tiene que corresponder a la regla que decidió.
    const texto = neutralReason({ prob_up: 0.52, neutral_band: 0.05 })
    expect(texto).toContain('5 puntos del 50%')
  })

  it('nunca deja el porcentaje en NaN', () => {
    expect(neutralReason({})).not.toContain('NaN')
  })
})
