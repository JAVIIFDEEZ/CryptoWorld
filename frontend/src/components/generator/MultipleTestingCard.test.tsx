/**
 * MultipleTestingCard.test.tsx — Control de multiplicidad.
 *
 * Lo que importa de esta tarjeta es que no mienta: debe decir con claridad si
 * la campeona supera o no el Sharpe que produce el puro azar con el número de
 * pruebas realizadas.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import MultipleTestingCard from './MultipleTestingCard'

function control(observed: number, threshold: number) {
  return {
    evaluated: 3000,
    sampled: 300,
    capacity: 300,
    effective_trials: 412,
    best_deflated_sharpe: 0.4,
    expected_max_sharpe_curve: {
      curve: [
        { trials: 1, expected_max_sharpe: 0 },
        { trials: 100, expected_max_sharpe: threshold * 0.6 },
        { trials: 3000, expected_max_sharpe: threshold },
      ],
      variance: 0.02,
      n_trials: 3000,
      observed_sharpe: observed,
      expected_max_at_n: threshold,
      trials_to_match_by_chance: observed < threshold ? 900 : null,
    },
    note: 'Se evaluaron 3000 configuraciones distintas.',
  }
}

describe('MultipleTestingCard', () => {
  it('marca como indistinguible del azar a la campeona por debajo del umbral', () => {
    render(<MultipleTestingCard control={control(0.20, 0.45)} />)
    expect(screen.getByText(/no se distingue del azar/i)).toBeInTheDocument()
  })

  it('reconoce a la campeona que sí supera el umbral', () => {
    render(<MultipleTestingCard control={control(0.80, 0.45)} />)
    expect(screen.getByText(/supera al azar/i)).toBeInTheDocument()
  })

  it('muestra el número de pruebas y las independientes', () => {
    render(<MultipleTestingCard control={control(0.8, 0.45)} />)
    // El separador de miles depende del ICU disponible ('3.000' en navegador,
    // '3000' en el Node del entorno de test): se acepta cualquiera de los dos.
    expect(screen.getAllByText(/^3[.,]?000$/).length).toBeGreaterThan(0)
    expect(screen.getByText('412')).toBeInTheDocument()
  })

  it('no renderiza nada sin curva suficiente', () => {
    const c = control(0.5, 0.4)
    c.expected_max_sharpe_curve.curve = [{ trials: 1, expected_max_sharpe: 0 }]
    const { container } = render(<MultipleTestingCard control={c} />)
    expect(container).toBeEmptyDOMElement()
  })
})
