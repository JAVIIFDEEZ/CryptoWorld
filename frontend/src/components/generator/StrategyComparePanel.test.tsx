/**
 * StrategyComparePanel.test.tsx — Comparador cara a cara.
 *
 * Verifica los veredictos por dimensión, la gráfica superpuesta con leyenda,
 * la tabla con el mejor de cada fila resaltado y la correlación entre pares.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import StrategyComparePanel from './StrategyComparePanel'
import { strategyGeneratorService, type StrategyComparison } from '@/services/strategyGeneratorService'

const COMPARISON: StrategyComparison = {
  status: 'OK',
  items: [
    {
      strategy_id: 1, label: 'BTC 1d', asset_symbol: 'BTC', interval: '1d',
      description: 'RSI < 30', spec_hash: 'a', generated_at: null,
      stored: { fitness: 1.5, sharpe: 1.4, mean_oos_sharpe: 1.0, pbo: 0.2, wf_efficiency: 0.8,
                n_trades: 20, max_drawdown_pct: -10, cross_consistency: 0.67,
                holdout_return_pct: 12, holdout_sharpe: 1.1 },
      fresh: { available: true, candles: 300, data_source: 'test',
               equity: [1, 1.05, 1.12], window_return_pct: 12, oos_sharpe: 0.9, wf_efficiency: 0.7 },
    },
    {
      strategy_id: 2, label: 'ETH 1d', asset_symbol: 'ETH', interval: '1d',
      description: 'MACD cruce', spec_hash: 'b', generated_at: null,
      stored: { fitness: 0.9, sharpe: 1.0, mean_oos_sharpe: 0.7, pbo: 0.3, wf_efficiency: 0.6,
                n_trades: 15, max_drawdown_pct: -8, cross_consistency: 1.0,
                holdout_return_pct: 20, holdout_sharpe: 1.4 },
      fresh: { available: true, candles: 300, data_source: 'test',
               equity: [1, 0.98, 1.06], window_return_pct: 6, oos_sharpe: 0.5, wf_efficiency: 0.5 },
    },
  ],
  correlation: { labels: ['BTC 1d', 'ETH 1d'], matrix: [[1, 0.21], [0.21, 1]], common_days: 120 },
  verdicts: {
    best_fitness: 'BTC 1d', best_holdout: 'ETH 1d', best_fresh: 'BTC 1d',
    best_generalization: 'ETH 1d',
    most_diversifying_pair: { a: 'BTC 1d', b: 'ETH 1d', corr: 0.21 },
  },
  note: 'No constituye consejo financiero.',
}

beforeEach(() => {
  vi.spyOn(strategyGeneratorService, 'compare').mockResolvedValue(COMPARISON)
})

describe('StrategyComparePanel', () => {
  it('muestra los veredictos por dimensión', async () => {
    render(<StrategyComparePanel ids={[1, 2]} onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText(/Mejor fitness/)).toBeInTheDocument())
    expect(screen.getByText(/Mejor holdout/)).toBeInTheDocument()
    expect(screen.getByText(/Pareja más diversificadora/)).toBeInTheDocument()
    expect(screen.getByText(/ρ 0.21/)).toBeInTheDocument()
  })

  it('pinta la equity superpuesta con leyenda y etiquetas directas', async () => {
    render(<StrategyComparePanel ids={[1, 2]} onClose={() => {}} />)
    await waitFor(() =>
      expect(screen.getByRole('img', { name: /Equity comparada/ })).toBeInTheDocument())
    expect(screen.getByText('BTC +12%')).toBeInTheDocument()   // etiqueta directa
    expect(screen.getAllByText('BTC 1d').length).toBeGreaterThanOrEqual(2) // leyenda + tabla
  })

  it('resalta el mejor de cada fila en la tabla', async () => {
    render(<StrategyComparePanel ids={[1, 2]} onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText('Fitness')).toBeInTheDocument())
    expect(screen.getByText('1.500 ★')).toBeInTheDocument()    // mejor fitness
    expect(screen.getByText('20% ★')).toBeInTheDocument()      // mejor PBO (menor)... holdout +20%? ver abajo
    expect(screen.getByText('+20% ★')).toBeInTheDocument()     // mejor holdout
  })

  it('muestra la correlación del par', async () => {
    render(<StrategyComparePanel ids={[1, 2]} onClose={() => {}} />)
    await waitFor(() => expect(screen.getByText(/120 días comunes/)).toBeInTheDocument())
    expect(screen.getByText(/BTC 1d↔ETH 1d/)).toBeInTheDocument()
  })
})
