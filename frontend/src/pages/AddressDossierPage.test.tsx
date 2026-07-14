/**
 * AddressDossierPage.test.tsx — Documento del dossier forense de dirección.
 *
 * Verifica el documento puro (AddressDossierDocument): veredicto global,
 * hallazgos clave por severidad y las secciones con degradación honesta.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AddressDossierDocument } from './AddressDossierPage'
import type { AddressDossier } from '@/services/blockchainService'

const DOSSIER = {
  status: 'OK', chain: 'ethereum', address: '0x' + 'a'.repeat(40),
  verdict: {
    overall_score: 62, band: 'ELEVADO', headline: 'Señales de riesgo relevantes.',
    risk_band: 'ALTO', worst_approval: 'ALTO',
    key_findings: [
      { severity: 'high', text: 'Riesgo de dirección ALTO (44/100).' },
      { severity: 'medium', text: 'Aprobación ERC-20 viva de riesgo ALTO (2 ilimitadas).' },
      { severity: 'info', text: 'Conducta: Distribuidora.' },
    ],
  },
  sections: {
    risk: { score: 44, band: 'ALTO', flagged_counterparties: 1, counterparties_analyzed: 5,
            factors: [{ kind: 'counterparty', category: 'mixer', weight: 38, detail: '1 contraparte de riesgo (mixer).' }] },
    fingerprint: { fingerprint: { available: true, archetype: 'Distribuidora', sample_txs: 40,
                   span_days: 30, txs_per_week: 9.3, unique_counterparties: 25, days_since_last: 2 } },
    approvals: { total: 3, unlimited: 2, worst: 'ALTO',
                 approvals: [{ token_symbol: 'USDC', spender: '0x' + 'b'.repeat(40), risk: 'ALTO', is_unlimited: true }] },
    entity: { entity_size: 4, neighbors_scanned: 8 },
    flow: { patterns: [{ type: 'peel_chain', depth: 3, note: 'Peel chain detectada.' }] },
  },
  note: 'No constituye consejo.',
} as unknown as AddressDossier

describe('AddressDossierDocument', () => {
  it('muestra el veredicto global y la cabecera', () => {
    render(<AddressDossierDocument d={DOSSIER} />)
    expect(screen.getByText('ELEVADO')).toBeInTheDocument()
    expect(screen.getByText('62/100')).toBeInTheDocument()
    expect(screen.getByText(/Señales de riesgo relevantes/)).toBeInTheDocument()
  })

  it('lista los hallazgos clave', () => {
    render(<AddressDossierDocument d={DOSSIER} />)
    expect(screen.getByText(/Riesgo de dirección ALTO/)).toBeInTheDocument()
    expect(screen.getByText(/Conducta: Distribuidora/)).toBeInTheDocument()
  })

  it('pinta las secciones de riesgo, conducta, aprobaciones y flujos', () => {
    render(<AddressDossierDocument d={DOSSIER} />)
    expect(screen.getByText(/1 contraparte de riesgo/)).toBeInTheDocument()
    expect(screen.getByText(/Arquetipo/)).toBeInTheDocument()
    expect(screen.getByText(/peor:/)).toBeInTheDocument()
    expect(screen.getByText(/Peel chain/)).toBeInTheDocument()
    expect(screen.getByText(/Entidad probable:/)).toBeInTheDocument()
  })
})
