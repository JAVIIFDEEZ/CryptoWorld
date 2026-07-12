/**
 * WalkForwardMatrixCard.test.tsx — Matriz walk-forward del campeón.
 *
 * Verifica el heatmap de estabilidad temporal: filas por troceo, celdas con el
 * Sharpe OOS por tramo y el veredicto agregado de tramos positivos.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import WalkForwardMatrixCard from './WalkForwardMatrixCard'

const MATRIX = {
  rows: [
    { n_splits: 3, folds: [0.8, 1.2, -0.3], mean_oos_sharpe: 0.57, efficiency: 0.7 },
    { n_splits: 4, folds: [0.5, 0.9, 0.2, 1.1], mean_oos_sharpe: 0.68, efficiency: 0.8 },
  ],
  total_folds: 7,
  positive_folds: 6,
  stability_score: 0.857,
  note: 'Sharpe OOS de cada tramo walk-forward bajo distintos troceos.',
}

describe('WalkForwardMatrixCard', () => {
  it('pinta filas por troceo y el veredicto de estabilidad', () => {
    render(<WalkForwardMatrixCard matrix={MATRIX} championDesc="RSI(14) < 30 → RSI(14) > 70" />)
    expect(screen.getByText('Matriz walk-forward del campeón')).toBeInTheDocument()
    expect(screen.getByText('3 tramos')).toBeInTheDocument()
    expect(screen.getByText('4 tramos')).toBeInTheDocument()
    expect(screen.getByText('6/7 tramos positivos · 86%')).toBeInTheDocument()
    expect(screen.getByText('RSI(14) < 30 → RSI(14) > 70')).toBeInTheDocument()
  })

  it('colorea celdas por signo del Sharpe OOS con su valor', () => {
    render(<WalkForwardMatrixCard matrix={MATRIX} championDesc="x" />)
    const negative = screen.getByTitle(/tramo 3 con 3 particiones: -0.300/)
    expect(negative).toHaveClass('text-red-200')
    const positive = screen.getByTitle(/tramo 2 con 3 particiones: 1.200/)
    expect(positive).toHaveClass('text-emerald-100')
  })
})
