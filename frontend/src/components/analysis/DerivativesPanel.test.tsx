/**
 * DerivativesPanel.test.tsx — Microestructura de perpetuos.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import DerivativesPanel from './DerivativesPanel'
import { analysisService, type DerivativesSnapshot } from '@/services/analysisService'

const SNAP: DerivativesSnapshot = {
  available: true, symbol: 'BTC', perp_symbol: 'BTCUSDT',
  mark_price: 65200, index_price: 65000, funding_rate: 0.0005,
  funding_annualized_pct: 54.75, funding_verdict: 'LARGOS SOBRECALENTADOS',
  basis_pct: 0.31, basis_verdict: 'contango',
  open_interest: 1000, open_interest_usd: 65_200_000, note: 'x',
}

describe('DerivativesPanel', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('muestra funding, basis, OI y veredictos', async () => {
    vi.spyOn(analysisService, 'getDerivatives').mockResolvedValue(SNAP)
    render(<DerivativesPanel symbol="BTC" />)
    await waitFor(() => expect(screen.getByText('BTCUSDT')).toBeInTheDocument())
    expect(screen.getByText('+54.75%')).toBeInTheDocument()
    expect(screen.getByText('LARGOS SOBRECALENTADOS')).toBeInTheDocument()
    expect(screen.getByText('contango')).toBeInTheDocument()
    expect(screen.getByText('$65.2M')).toBeInTheDocument()
  })

  it('avisa cuando el activo no tiene perpetuo', async () => {
    vi.spyOn(analysisService, 'getDerivatives').mockResolvedValue({ available: false })
    render(<DerivativesPanel symbol="XYZ" />)
    await waitFor(() => expect(screen.getByText(/no tiene perpetuo/)).toBeInTheDocument())
  })
})
