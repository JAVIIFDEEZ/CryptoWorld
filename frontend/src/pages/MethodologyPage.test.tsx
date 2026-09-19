/**
 * MethodologyPage.test.tsx — La escala de la curva del azar.
 *
 * El gráfico de esta página hace una afirmación fuerte: que la campeona está por
 * encima o por debajo de lo que produce el puro azar. Si la proyección a
 * coordenadas se equivoca, la página afirma lo contrario de lo que dicen los
 * datos — y lo hace con aspecto de rigor, que es el peor de los errores posibles
 * para una nota metodológica.
 */

import { describe, it, expect } from 'vitest'
import { chartCeiling, curveToPoints } from './MethodologyPage'

const curva = [
  { trials: 1, expected_max_sharpe: 0.0 },
  { trials: 10, expected_max_sharpe: 1.0 },
  { trials: 100, expected_max_sharpe: 1.5 },
  { trials: 1000, expected_max_sharpe: 1.9 },
]

describe('chartCeiling', () => {
  it('deja aire por encima de la serie más alta', () => {
    expect(chartCeiling(curva, null)).toBeGreaterThan(1.9)
  })

  it('sube el techo si la campeona supera a la curva', () => {
    // Si no lo hiciera, una campeona excelente se saldría del gráfico justo
    // cuando el gráfico tiene algo bueno que enseñar.
    expect(chartCeiling(curva, 5.0)).toBeGreaterThan(5.0)
  })

  it('nunca devuelve cero aunque no haya nada que dibujar', () => {
    // Un techo de cero haría una división por cero y dejaría NaN en el SVG.
    expect(chartCeiling([], null)).toBeGreaterThan(0)
  })
})

describe('curveToPoints', () => {
  it('genera un punto por cada entrada de la curva', () => {
    expect(curveToPoints(curva, 2.2).split(' ')).toHaveLength(curva.length)
  })

  it('usa escala logarítmica en el eje de pruebas', () => {
    // En escala lineal, el 99 % del gráfico sería plano y el tramo interesante
    // —las primeras decenas de pruebas— se aplastaría contra el eje.
    const xs = curveToPoints(curva, 2.2).split(' ').map((p) => Number(p.split(',')[0]))
    const saltos = xs.slice(1).map((x, i) => x - xs[i])
    // Con log10 y trials ×10 cada paso, los saltos son iguales; en lineal no.
    expect(Math.max(...saltos) - Math.min(...saltos)).toBeLessThan(1)
  })

  it('un Sharpe mayor queda más arriba (menor Y)', () => {
    const ys = curveToPoints(curva, 2.2).split(' ').map((p) => Number(p.split(',')[1]))
    expect(ys[3]).toBeLessThan(ys[0])
  })

  it('mantiene los puntos dentro del lienzo', () => {
    const coords = curveToPoints(curva, 1.0).split(' ')   // techo por debajo del máximo
    for (const c of coords) {
      const [x, y] = c.split(',').map(Number)
      expect(x).toBeGreaterThanOrEqual(0)
      expect(x).toBeLessThanOrEqual(100)
      expect(y).toBeGreaterThanOrEqual(0)
      expect(y).toBeLessThanOrEqual(100)
    }
  })

  it('devuelve vacío en vez de NaN cuando no hay nada que dibujar', () => {
    expect(curveToPoints([], 1)).toBe('')
    expect(curveToPoints(curva, 0)).toBe('')
  })
})
