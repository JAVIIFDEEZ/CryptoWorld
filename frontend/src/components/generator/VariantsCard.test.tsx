/**
 * VariantsCard.test.tsx — Las que no encabezan el libro decorrelacionado.
 *
 * Lo que esta tarjeta no puede hacer es presentarlas como descartes. Superaron
 * exactamente los mismos controles que la cabeza de libro; lo que las aparta es
 * correlacionar con ella, no fallar nada.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import VariantsCard from './VariantsCard'
import type { StrategyVariant } from '@/services/strategyGeneratorService'

function variant(hash: string, corr: number, dd: number): StrategyVariant {
  return {
    spec: { entry: { combine: 'AND', conditions: [] }, exit: { combine: 'OR', conditions: [] } },
    spec_hash: hash,
    description: `ENTRAR si RSI < 30 (${hash})`,
    fitness: 1.4,
    passed_gating: true,
    correlation_with_parent: corr,
    gating: {
      checks: { min_trades: true, no_lookahead: true, wf_efficiency: true, pbo: true, mc_p5_positive: true },
      metrics: {
        n_trades: 34, total_return_pct: 22.5, max_drawdown_pct: dd, exposure_pct: 40,
        sharpe: 1.62, sortino: 2.1, wf_efficiency: 0.7, mean_oos_sharpe: 1.1, pbo: 0.2,
        monte_carlo: { prob_profit_pct: 88, return_p5_pct: 3, return_p50_pct: 20 },
        lookahead_leaky: false,
      },
    },
    evolution_metrics: { fitness: 1.4, wf_efficiency: 0.7, mean_oos_sharpe: 1.1, pbo: 0.2 },
    holdout_validation: {
      return_pct: 8.3, sharpe: 1.2, max_drawdown_pct: 9.0, n_trades: 11,
      win_rate_pct: 55, candles: 300,
    },
  }
}

describe('VariantsCard', () => {
  it('lista cada variante con sus métricas ya validadas', () => {
    render(<VariantsCard variants={[variant('aaa', 0.82, 12.4), variant('bbb', 0.95, 18.1)]} />)
    expect(screen.getByText(/2 variantes/)).toBeInTheDocument()
    expect(screen.getByText('0.82')).toBeInTheDocument()
    expect(screen.getByText('0.95')).toBeInTheDocument()
  })

  it('muestra la correlación, porque 0.72 y 0.99 no son lo mismo', () => {
    render(<VariantsCard variants={[variant('aaa', 0.72, 10)]} />)
    expect(screen.getByText('0.72')).toBeInTheDocument()
  })

  it('deja ver la caída máxima, que es el motivo típico para preferir una variante', () => {
    render(<VariantsCard variants={[variant('aaa', 0.8, 12.4)]} />)
    expect(screen.getByText('−12.4%')).toBeInTheDocument()
  })

  it('dice con qué estrategia correlacionan', () => {
    render(<VariantsCard variants={[variant('aaa', 0.8, 10)]} championDesc="ENTRAR si EMA cruza SMA" />)
    expect(screen.getByText(/ENTRAR si EMA cruza SMA/)).toBeInTheDocument()
  })

  it('no las presenta como un fallo', () => {
    render(<VariantsCard variants={[variant('aaa', 0.8, 10)]} />)
    expect(screen.getByText(/no es un fallo/i)).toBeInTheDocument()
  })

  it('no renderiza nada cuando no hay variantes', () => {
    const { container } = render(<VariantsCard variants={[]} />)
    expect(container).toBeEmptyDOMElement()
  })
})
