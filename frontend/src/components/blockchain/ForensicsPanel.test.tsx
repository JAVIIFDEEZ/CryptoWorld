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

  it('arranca en el dossier y cambia entre herramientas', () => {
    render(<ForensicsPanel />)
    expect(screen.getByPlaceholderText(/Dirección para el informe/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Riesgo de dirección'))
    expect(screen.getByPlaceholderText(/Dirección a evaluar/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Rastreo de flujos'))
    expect(screen.getByPlaceholderText(/Dirección de origen/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Concentración'))
    expect(screen.getByPlaceholderText(/Contrato del token/)).toBeInTheDocument()
  })

  it('deshabilita Analizar hasta que la dirección es válida', () => {
    render(<ForensicsPanel />)
    fireEvent.click(screen.getByText('Riesgo de dirección'))
    const btn = screen.getByRole('button', { name: 'Analizar' })
    expect(btn).toBeDisabled()
    fireEvent.change(screen.getByPlaceholderText(/Dirección a evaluar/), {
      target: { value: '0x' + 'a'.repeat(40) },
    })
    expect(btn).not.toBeDisabled()
  })

  it('muestra la puntuación de riesgo con su banda y factores', async () => {
    vi.spyOn(blockchainService, 'addressRisk').mockResolvedValue({
      status: 'OK', chain: 'ethereum', address: '0x' + 'a'.repeat(40),
      score: 52, band: 'ALTO', flagged_counterparties: 1, counterparties_analyzed: 3,
      self_labels: [], note: 'heurístico',
      factors: [{ kind: 'counterparty', category: 'scam', weight: 32, detail: '1 contraparte de riesgo (scam).' }],
    })
    render(<ForensicsPanel />)
    fireEvent.click(screen.getByText('Riesgo de dirección'))
    fireEvent.change(screen.getByPlaceholderText(/Dirección a evaluar/), {
      target: { value: '0x' + 'a'.repeat(40) },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Analizar' }))
    await waitFor(() => expect(screen.getByText('Riesgo ALTO')).toBeInTheDocument())
    expect(screen.getByText('52')).toBeInTheDocument()
    expect(screen.getByText(/1 contraparte de riesgo/)).toBeInTheDocument()
  })

  it('muestra el veredicto de seguridad de token con banderas', async () => {
    vi.spyOn(blockchainService, 'tokenSafety').mockResolvedValue({
      status: 'OK', chain: 'ethereum', token: '0x' + 'c'.repeat(40),
      token_name: 'Rug Token', token_symbol: 'RUG', score: 78, verdict: 'PELIGROSO',
      verified: true, ownership_renounced: false, is_proxy: true, owner: '0xowner',
      flags: [{ category: 'mint', weight: 22, label: 'Emisión (mint)', detail: 'El propietario puede crear tokens.' }],
      green_flags: ['Código fuente verificado y auditable.'],
      top10_concentration_pct: 80, note: 'heurístico',
    })
    render(<ForensicsPanel />)
    fireEvent.click(screen.getByText('Seguridad de token'))
    fireEvent.change(screen.getByPlaceholderText(/Contrato del token/), {
      target: { value: '0x' + 'c'.repeat(40) },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Analizar' }))
    await waitFor(() => expect(screen.getByText('PELIGROSO')).toBeInTheDocument())
    expect(screen.getByText('RUG')).toBeInTheDocument()
    expect(screen.getByText(/Emisión \(mint\)/)).toBeInTheDocument()
    expect(screen.getByText(/Proxy actualizable/)).toBeInTheDocument()
  })

  it('muestra el veredicto de wash trading con pares round-trip', async () => {
    vi.spyOn(blockchainService, 'washTrading').mockResolvedValue({
      status: 'OK', chain: 'ethereum', token: '0x' + 'c'.repeat(40),
      token_name: 'Pump', token_symbol: 'PUMP', available: true,
      wash_score: 88, verdict: 'MANIPULADO', total_transfers: 40, unique_addresses: 4,
      round_trip_ratio: 0.92, round_trip_volume_pct: 92, top5_pair_share_pct: 95, self_transfers: 0,
      suspicious_pairs: [{ a: '0x' + 'a'.repeat(40), b: '0x' + 'b'.repeat(40),
        volume_ab: 100, volume_ba: 100, round_trip_volume: 200, transfers: 16, share_pct: 50 }],
      note: 'heurístico',
    })
    render(<ForensicsPanel />)
    fireEvent.click(screen.getByText('Wash trading'))
    fireEvent.change(screen.getByPlaceholderText(/Contrato del token/), {
      target: { value: '0x' + 'c'.repeat(40) },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Analizar' }))
    await waitFor(() => expect(screen.getByText('MANIPULADO')).toBeInTheDocument())
    expect(screen.getByText('88/100')).toBeInTheDocument()
    expect(screen.getByText('92%')).toBeInTheDocument()
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
