/**
 * LeadLagPanel.test.tsx — Señales lead-lag.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import LeadLagPanel from './LeadLagPanel'
import { regimeService, type LeadLag } from '../../services/regimeService'

const DATA: LeadLag = {
  status: 'OK', symbols: ['BTC', 'ETH'], max_lag: 5,
  pairs: [{ leader: 'BTC', follower: 'ETH', lag: 2, corr: 0.71 }],
  leaders: [{ symbol: 'BTC', leads: 1 }, { symbol: 'ETH', leads: 0 }],
  note: 'x',
}

describe('LeadLagPanel', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('no pinta nada sin relaciones', async () => {
    vi.spyOn(regimeService, 'leadLag').mockResolvedValue({ status: 'INSUFICIENTE' })
    const { container } = render(<LeadLagPanel />)
    await waitFor(() => expect(regimeService.leadLag).toHaveBeenCalled())
    expect(container.textContent).toBe('')
  })

  it('muestra el líder y la relación con su desfase', async () => {
    vi.spyOn(regimeService, 'leadLag').mockResolvedValue(DATA)
    render(<LeadLagPanel />)
    await waitFor(() => expect(screen.getByText('Señales lead-lag')).toBeInTheDocument())
    expect(screen.getByText('BTC lidera 1')).toBeInTheDocument()
    expect(screen.getByText(/\+2 barras · r=0.71/)).toBeInTheDocument()
  })
})
