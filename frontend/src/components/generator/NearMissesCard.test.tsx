/**
 * NearMissesCard.test.tsx — La distancia se enseña; el listón no se mueve.
 *
 * Esta tarjeta camina sobre una línea fina: informar de que algo se quedó cerca
 * es útil, e insinuar que por eso el umbral debería bajar es el sesgo que el
 * gating existe para frenar. Los tests fijan las dos mitades — que la distancia
 * se vea, y que el aviso de que no se toca nada esté ahí.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import NearMissesCard from './NearMissesCard'
import type { NearMiss } from '@/services/strategyGeneratorService'

function miss(over: Partial<NearMiss> = {}): NearMiss {
  return {
    spec_hash: 'abc123',
    description: 'ENTRAR si RSI(14) < 30',
    fitness: 1.1,
    check: 'mc_p5_positive',
    label: 'percentil 5 del Monte Carlo',
    observed: -0.02,
    required: 0,
    gap: 0.02,
    gap_ratio: 0.0005,
    note: 'Falló solo este control.',
    ...over,
  }
}

describe('NearMissesCard', () => {
  it('no se dibuja cuando no hay ninguna', () => {
    const { container } = render(<NearMissesCard misses={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('dice que siguen fuera del libro', () => {
    /* Sin esto, una lista de candidatas «casi aprobadas» se lee como si fueran
       resultados de la ejecución. */
    render(<NearMissesCard misses={[miss()]} />)
    expect(screen.getByText(/Siguen fuera del libro/)).toBeInTheDocument()
  })

  it('distingue rozar la línea de quedarse lejos', () => {
    render(<NearMissesCard misses={[
      miss({ spec_hash: 'cerca', gap_ratio: 0.0005 }),
      miss({ spec_hash: 'lejos', gap_ratio: 0.45 }),
    ]} />)

    expect(screen.getByText(/rozando 0\.1%/)).toBeInTheDocument()
    expect(screen.getByText(/^a 45\.0%$/)).toBeInTheDocument()
  })

  it('enseña lo observado contra lo exigido, en las unidades del control', () => {
    render(<NearMissesCard misses={[
      miss({ check: 'min_trades', label: 'operaciones', observed: 7, required: 12, gap_ratio: 0.4167 }),
    ]} />)

    expect(screen.getByText('7 / 12')).toBeInTheDocument()
  })

  it('no inventa una escala donde el control no la tiene', () => {
    /* El control por lado no se mide contra un número: decir «a un 0%» sería
       una precisión falsa. */
    render(<NearMissesCard misses={[
      miss({
        check: 'sides_stand_alone', label: 'cada lado se sostiene solo',
        observed: null, required: null, gap: null, gap_ratio: null,
      }),
    ]} />)

    expect(screen.getByText('sin escala comparable')).toBeInTheDocument()
  })

  it('avisa de que bajar el umbral sería elegir el listón después del salto', () => {
    render(<NearMissesCard misses={[miss()]} />)
    expect(screen.getByText(/Los umbrales no se mueven por esto/)).toBeInTheDocument()
    expect(screen.getByText(/elegir el listón después de ver el salto/)).toBeInTheDocument()
  })

  it('propone lo que sí es legítimo: más histórico u otra semilla', () => {
    render(<NearMissesCard misses={[miss()]} />)
    expect(screen.getByText(/contra el\s+mismo listón/)).toBeInTheDocument()
  })
})
