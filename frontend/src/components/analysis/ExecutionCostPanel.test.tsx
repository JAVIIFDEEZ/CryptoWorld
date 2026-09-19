/**
 * ExecutionCostPanel.test.tsx — Que el coste se lea por lo que es.
 *
 * El modo de fallo caro de este panel no es equivocarse en el número: es que
 * alguien lea una estimación como una medición del libro de órdenes, o que un
 * tamaño que no entra en el mercado se vea igual que uno que sí.
 */

import { describe, it, expect } from 'vitest'
import { compactUsd, costClass } from './ExecutionCostPanel'

describe('compactUsd', () => {
  it('abrevia los órdenes de magnitud que aparecen en la escalera', () => {
    expect(compactUsd(1_000)).toBe('$1K')
    expect(compactUsd(100_000)).toBe('$100K')
    expect(compactUsd(1_000_000)).toBe('$1.0M')
    expect(compactUsd(2_500_000_000)).toBe('$2.50B')
  })

  it('no abrevia lo que cabe entero', () => {
    expect(compactUsd(320)).toBe('$320')
  })

  it('devuelve un guion en vez de NaN o $null', () => {
    // El techo de ejecutable es null cuando no hay datos; pintarlo como "$NaN"
    // sería peor que no pintar nada.
    expect(compactUsd(null)).toBe('—')
    expect(compactUsd(undefined)).toBe('—')
    expect(compactUsd(Number.NaN)).toBe('—')
  })
})

describe('costClass', () => {
  it('trata como benigno lo que no cambia ninguna decisión', () => {
    // Por debajo de 10 bps el coste está en el entorno de una comisión normal.
    expect(costClass(3)).toContain('emerald')
  })

  it('avisa en la franja en la que el coste empieza a competir con el edge', () => {
    expect(costClass(25)).toContain('amber')
  })

  it('marca en rojo lo que se come cualquier edge realista', () => {
    // A partir de 50 bps no queda edge de esta plataforma que lo soporte.
    expect(costClass(120)).toContain('red')
  })

  it('los cortes son monótonos', () => {
    const orden = [costClass(1), costClass(9.9), costClass(10), costClass(49.9), costClass(50)]
    expect(orden[0]).toBe(orden[1])
    expect(orden[2]).toBe(orden[3])
    expect(orden[4]).not.toBe(orden[3])
  })
})
