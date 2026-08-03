/**
 * CpcvDistributionCard.test.tsx — Distribución CPCV del campeón.
 *
 * Lo que esta tarjeta no puede hacer es tranquilizar cuando el suelo se hunde:
 * un máximo brillante con percentil 5 negativo significa que la estrategia
 * depende del troceo del histórico, y debe leerse así.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import CpcvDistributionCard from './CpcvDistributionCard'

function cpcv(p5: number, positive: number) {
  return {
    n_paths: 15,
    n_blocks: 6,
    blocks_per_path: 2,
    sharpe_mean: 2.6,
    sharpe_median: 2.72,
    sharpe_p5: p5,
    sharpe_p25: 1.8,
    sharpe_p75: 4.37,
    sharpe_min: p5 - 0.5,
    sharpe_max: 6.11,
    pct_paths_positive: positive,
    embargo_pct: 0.02,
    embargo_bars: 3,
    note: 'Distribución sobre 15 caminos de 2 bloques.',
    purge_note: 'Cada bloque se backtestea aislado.',
  }
}

describe('CpcvDistributionCard', () => {
  it('muestra la mediana y el escenario adverso', () => {
    render(<CpcvDistributionCard cpcv={cpcv(1.19, 100)} />)
    expect(screen.getByText('1.19')).toBeInTheDocument()
    expect(screen.getByText('2.72')).toBeInTheDocument()
  })

  it('avisa cuando no todos los caminos son positivos', () => {
    render(<CpcvDistributionCard cpcv={cpcv(-0.8, 40)} />)
    expect(screen.getByText(/40% de caminos en positivo/)).toBeInTheDocument()
  })

  it('sitúa el walk-forward junto a la distribución para poder compararlos', () => {
    render(<CpcvDistributionCard cpcv={cpcv(1.19, 100)} walkForwardSharpe={6.6} />)
    expect(screen.getByText('6.60')).toBeInTheDocument()
    expect(screen.getByText('walk-forward')).toBeInTheDocument()
  })

  it('no renderiza nada sin caminos suficientes', () => {
    const { container } = render(
      <CpcvDistributionCard cpcv={{ n_paths: 0, n_blocks: 0, note: 'insuficiente' }} />,
    )
    expect(container).toBeEmptyDOMElement()
  })
})
