/**
 * EvolutionLiveBoard.test.tsx — Evolución genética en vivo.
 *
 * Verifica que el cuadro de mando pinta la convergencia, las tarjetas de
 * candidatas con su curva de equity y los estados del motor (islas,
 * hipermutación, gating) a partir de un snapshot de progreso.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import EvolutionLiveBoard from './EvolutionLiveBoard'
import type { EvolutionProgress } from '@/services/strategyGeneratorService'

const HISTORY = Array.from({ length: 5 }, (_, g) => ({
  generation: g, best: 0.1 * g, mean: 0.05 * g, diversity: 20 - g,
}))

const EVOLVING: EvolutionProgress = {
  phase: 'evolving',
  generation: 4,
  generations_total: 15,
  best: 0.4,
  mean: 0.2,
  diversity: 16,
  island_best: [0.4, 0.31],
  hypermutation: true,
  evaluations: 87,
  history: HISTORY,
  top: [
    {
      hash: 'abc123', description: 'RSI(14) < 30 → RSI(14) > 70', fitness: 0.412,
      equity: [1.0, 1.01, 1.05, 1.04, 1.09], total_return_pct: 9.2,
      max_drawdown_pct: -3.1, n_trades: 14,
    },
    {
      hash: 'def456', description: 'EMA(12) cruza SMA(26)', fitness: 0.377,
      equity: [1.0, 0.99, 1.02, 1.03, 1.06], total_return_pct: 6.1,
      max_drawdown_pct: -4.0, n_trades: 11,
    },
  ],
}

describe('EvolutionLiveBoard', () => {
  it('pinta la generación, las islas y la hipermutación', () => {
    render(<EvolutionLiveBoard progress={EVOLVING} />)
    expect(screen.getByText('Generación 5/15')).toBeInTheDocument()
    expect(screen.getByText('87 genomas evaluados')).toBeInTheDocument()
    expect(screen.getByText(/2 islas/)).toBeInTheDocument()
    expect(screen.getByText(/Hipermutación/)).toBeInTheDocument()
  })

  it('pinta las tarjetas de candidatas con fitness y retorno', () => {
    render(<EvolutionLiveBoard progress={EVOLVING} />)
    expect(screen.getByText('0.412')).toBeInTheDocument()
    expect(screen.getByText('+9.2%')).toBeInTheDocument()
    expect(screen.getByText('14 ops')).toBeInTheDocument()
    expect(screen.getByText('RSI(14) < 30 → RSI(14) > 70')).toBeInTheDocument()
  })

  it('pinta la convergencia con leyenda de mejor y media', () => {
    render(<EvolutionLiveBoard progress={EVOLVING} />)
    expect(screen.getByText('mejor de la generación')).toBeInTheDocument()
    expect(screen.getByText('media de la población')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Convergencia del fitness/ })).toBeInTheDocument()
  })

  it('muestra la ronda de búsqueda hasta objetivo cuando hay varias', () => {
    render(<EvolutionLiveBoard progress={{ ...EVOLVING, restart: 2, restarts_total: 3 }} />)
    expect(screen.getByText(/Ronda 2\/3/)).toBeInTheDocument()
  })

  it('en fase de refinamiento muestra el avance del hill-climb', () => {
    const refining: EvolutionProgress = {
      phase: 'refining', history: HISTORY,
      refining: { current: 2, total: 5, candidate: 'RSI(14) < 30' },
    }
    render(<EvolutionLiveBoard progress={refining} />)
    expect(screen.getByText('Refinando finalistas')).toBeInTheDocument()
    expect(screen.getByText('2/5')).toBeInTheDocument()
    expect(screen.getByText(/Afinando: RSI\(14\) < 30/)).toBeInTheDocument()
  })

  it('en fase de validación multi-activo muestra la cesta y el avance', () => {
    const cross: EvolutionProgress = {
      phase: 'cross_validating', history: HISTORY,
      cross: { current: 1, total: 3, basket: ['ETH', 'SOL'], candidate: 'RSI(14) < 30' },
    }
    render(<EvolutionLiveBoard progress={cross} />)
    expect(screen.getByText('Validación multi-activo')).toBeInTheDocument()
    expect(screen.getByText(/ETH · SOL/)).toBeInTheDocument()
    expect(screen.getByText('1/3')).toBeInTheDocument()
  })

  it('en fase de gating muestra el avance y las aprobadas', () => {
    const gating: EvolutionProgress = {
      phase: 'gating', history: HISTORY,
      gating: { current: 3, total: 12, passed: 1, candidate: 'MACD > señal' },
    }
    render(<EvolutionLiveBoard progress={gating} />)
    expect(screen.getByText('Gating de robustez')).toBeInTheDocument()
    expect(screen.getByText('3/12 · 1 aprobadas')).toBeInTheDocument()
    expect(screen.getByText(/Examinando: MACD > señal/)).toBeInTheDocument()
  })
})
