/**
 * RetestCascadeCard.test.tsx — Cascada de retests del campeón.
 *
 * Lo que esta tarjeta no puede hacer es pintar de verde una prueba que no llegó
 * a ejecutarse: ausencia de evidencia no es evidencia de solidez, y ese adorno
 * es justo lo que el panel existe para evitar.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import RetestCascadeCard from './RetestCascadeCard'
import type { RetestCascade } from '@/services/strategyGeneratorService'

function cascade(overrides: Partial<RetestCascade> = {}): RetestCascade {
  return {
    survived: true,
    checks: {
      noise: true, starting_bar: true, skip_trades: true,
      parameter_sensitivity: true, temporal_stability: true,
    },
    failed: [],
    noise: { n_runs: 10, base_sharpe: 2.1, noisy_sharpe_median: 1.9, pct_runs_positive: 90, degradation_pct: 9 },
    starting_bar: { n_offsets: 5, sharpe_std: 0.3, sharpe_min: 1.4, pct_offsets_positive: 100 },
    skip_trades: { n_runs: 200, full_pnl_pct: 42, pnl_median_pct: 34, pnl_p5_pct: 12, pct_runs_profitable: 100 },
    parameter_sensitivity: { n_neighbors: 12, base_sharpe: 2.1, pct_neighbors_positive: 83, median_degradation_pct: 14 },
    temporal_stability: { n_buckets: 10, concentration: 0.22, positive_buckets: 8, stable: true },
    note: 'Sobrevive a todas las perturbaciones.',
    ...overrides,
  }
}

describe('RetestCascadeCard', () => {
  it('resume que sobrevive a todas las pruebas', () => {
    render(<RetestCascadeCard retests={cascade()} />)
    // El veredicto sale en la insignia y de nuevo en la nota del backend.
    expect(screen.getAllByText(/sobrevive a todas/i).length).toBeGreaterThan(0)
  })

  it('dice cuántas pruebas falla cuando no sobrevive', () => {
    render(
      <RetestCascadeCard
        retests={cascade({
          survived: false,
          failed: ['noise', 'skip_trades'],
          checks: {
            noise: false, starting_bar: true, skip_trades: false,
            parameter_sensitivity: true, temporal_stability: true,
          },
        })}
      />,
    )
    expect(screen.getByText(/falla 2 de 5/i)).toBeInTheDocument()
  })

  it('marca como "sin datos" la prueba que no llegó a ejecutarse', () => {
    render(
      <RetestCascadeCard
        retests={cascade({ starting_bar: { n_offsets: 0 } })}
      />,
    )
    expect(screen.getByText('sin datos')).toBeInTheDocument()
    expect(screen.getByText(/Histórico insuficiente/i)).toBeInTheDocument()
  })

  it('enumera las cinco perturbaciones con su pregunta', () => {
    render(<RetestCascadeCard retests={cascade()} />)
    expect(screen.getByText('Ruido en los precios')).toBeInTheDocument()
    expect(screen.getByText('Arranque desplazado')).toBeInTheDocument()
    expect(screen.getByText('Operaciones omitidas')).toBeInTheDocument()
    expect(screen.getByText('Parámetros perturbados')).toBeInTheDocument()
    expect(screen.getByText('Reparto en el tiempo')).toBeInTheDocument()
  })
})
