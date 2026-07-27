/**
 * MarketRegimePanel.test.tsx — Régimen de mercado + correlaciones.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import MarketRegimePanel from './MarketRegimePanel'
import { regimeService, type MarketRegime } from '../../services/regimeService'

const DATA: MarketRegime = {
  status: 'OK',
  correlations: {
    status: 'OK', symbols: ['BTC', 'ETH'],
    matrix: [[1, 0.8], [0.8, 1]], avg_correlation: 0.8, days: 90,
    most_correlated: [{ a: 'BTC', b: 'ETH', corr: 0.8 }], least_correlated: [],
  },
  btc_trend_pct: -4.2, breadth_pct: 30,
  regime: { regime: 'RISK_OFF', label: 'Risk-off — todo cae en bloque', correlation_state: 'alta' },
  basket: ['BTC', 'ETH'], note: 'x',
}

describe('MarketRegimePanel', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('no pinta nada sin datos suficientes', async () => {
    vi.spyOn(regimeService, 'get').mockResolvedValue({ status: 'INSUFICIENTE' })
    const { container } = render(<MarketRegimePanel />)
    await waitFor(() => expect(regimeService.get).toHaveBeenCalled())
    expect(container.textContent).toBe('')
  })

  it('muestra el régimen, la correlación media y el mapa de calor', async () => {
    vi.spyOn(regimeService, 'get').mockResolvedValue(DATA)
    render(<MarketRegimePanel />)
    await waitFor(() => expect(screen.getByText('Risk-off — todo cae en bloque')).toBeInTheDocument())
    expect(screen.getByText('0.80')).toBeInTheDocument()      // correlación media
    expect(screen.getByText('-4.2%')).toBeInTheDocument()     // tendencia BTC
    // dos símbolos en cabecera de la matriz (col) + fila
    expect(screen.getAllByText('BTC').length).toBeGreaterThanOrEqual(2)
  })
})
