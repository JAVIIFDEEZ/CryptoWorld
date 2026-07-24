/**
 * RiskAttributionPanel.test.tsx — Atribución de riesgo del libro.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import RiskAttributionPanel from './RiskAttributionPanel'
import { portfolioService, type RiskAttribution } from '../../services/portfolioService'

const OK: RiskAttribution = {
  status: 'OK',
  components: {
    status: 'OK', tail_cvar_usd: 1200, days: 90, tail_days: 5,
    components: [
      { symbol: 'BTC', component_usd: 800, marginal: -0.04, pct: 66.7, exposure_usd: 20000 },
      { symbol: 'ETH', component_usd: 400, marginal: -0.03, pct: 33.3, exposure_usd: 10000 },
    ],
  },
  factor: { status: 'OK', beta_usd: 15000, systematic_pct: 72, idiosyncratic_pct: 28, r_squared: 0.72, days: 90 },
  gross_usd: 30000, note: 'x',
}

describe('RiskAttributionPanel', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('no pinta nada si no hay datos suficientes', async () => {
    vi.spyOn(portfolioService, 'getRiskAttribution').mockResolvedValue({
      status: 'INSUFICIENTE', components: { status: 'INSUFICIENTE', components: [] },
      factor: { status: 'INSUFICIENTE' },
    })
    const { container } = render(<RiskAttributionPanel />)
    await waitFor(() => expect(portfolioService.getRiskAttribution).toHaveBeenCalled())
    expect(container.textContent).toBe('')
  })

  it('muestra componentes y el reparto sistemática/idiosincrásica', async () => {
    vi.spyOn(portfolioService, 'getRiskAttribution').mockResolvedValue(OK)
    render(<RiskAttributionPanel />)
    await waitFor(() => expect(screen.getByText('Atribución del riesgo')).toBeInTheDocument())
    expect(screen.getByText('BTC')).toBeInTheDocument()
    expect(screen.getByText('ETH')).toBeInTheDocument()
    expect(screen.getByText('72%')).toBeInTheDocument()   // sistemática
    expect(screen.getByText('28%')).toBeInTheDocument()   // idiosincrásica
  })
})
