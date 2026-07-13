/**
 * ForensicsPanel.test.tsx — Submódulo forense on-chain.
 *
 * Verifica el cambio de herramienta, la validación de dirección de la barra de
 * entrada y el renderizado del resultado de concentración (con veredicto).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import ForensicsPanel from './ForensicsPanel'
import { blockchainService, type TokenConcentration } from '@/services/blockchainService'

const CONC: TokenConcentration = {
  status: 'OK', chain: 'ethereum', token: '0x' + 'c'.repeat(40),
  token_name: 'Test Token', token_symbol: 'TST',
  concentration: {
    available: true, sample_size: 100, top10_share_pct: 72, top50_share_pct: 90,
    gini: 0.85, hhi: 0.5, contract_share_pct: 10,
    top_holders: [{ address: '0x' + 'w'.repeat(40), value: 900, share_pct: 72, is_contract: false }],
    verdict: 'CRÍTICA', verdict_note: 'Riesgo extremo', note: 'muestra',
  },
}

describe('ForensicsPanel', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('arranca en el rastreador de flujos y cambia de herramienta', () => {
    render(<ForensicsPanel />)
    expect(screen.getByPlaceholderText(/Dirección de origen/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Concentración'))
    expect(screen.getByPlaceholderText(/Contrato del token/)).toBeInTheDocument()
  })

  it('deshabilita Analizar hasta que la dirección es válida', () => {
    render(<ForensicsPanel />)
    const btn = screen.getByRole('button', { name: 'Analizar' })
    expect(btn).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText(/Dirección de origen/), {
      target: { value: '0x' + 'a'.repeat(40) },
    })
    expect(btn).not.toBeDisabled()
  })

  it('muestra el veredicto de concentración y los tenedores', async () => {
    vi.spyOn(blockchainService, 'tokenConcentration').mockResolvedValue(CONC)
    render(<ForensicsPanel />)
    fireEvent.click(screen.getByText('Concentración'))
    fireEvent.change(screen.getByPlaceholderText(/Contrato del token/), {
      target: { value: '0x' + 'c'.repeat(40) },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Analizar' }))
    await waitFor(() => expect(screen.getByText('CRÍTICA')).toBeInTheDocument())
    expect(screen.getByText('TST')).toBeInTheDocument()
    expect(screen.getAllByText('72%').length).toBeGreaterThanOrEqual(1)  // KPI + barra tenedor
    expect(screen.getByText('0.85')).toBeInTheDocument()   // Gini
  })
})
