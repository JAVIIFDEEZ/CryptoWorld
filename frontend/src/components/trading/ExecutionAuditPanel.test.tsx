/**
 * ExecutionAuditPanel.test.tsx — Auditoría de ejecución real.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import ExecutionAuditPanel from './ExecutionAuditPanel'
import { tradingService, type ExecutionAudit } from '@/services/tradingService'

const AUDIT: ExecutionAudit = {
  status: 'OK',
  summary: {
    total_attempts: 3, sent: 1, failed: 1, blocked: 1, executed_notional_usd: 100,
    fill_rate_pct: 33.3, distinct_symbols: 1,
    blocked_reasons: [{ reason: 'límite de pérdida diaria', count: 1 }],
    failed_reasons: [{ reason: 'boom', count: 1 }],
  },
  entries: [
    { id: 1, created_at: '2026-01-01T00:00:00Z', symbol: 'BTC/USDT', side: 'buy', amount: 0.001,
      ref_price: 100, fill_price: 100.05, notional_usd: 0.1, status: 'sent', error: '', broker_order_id: 'x', is_testnet: true },
    { id: 2, created_at: '2026-01-01T00:01:00Z', symbol: 'BTC/USDT', side: 'buy', amount: 0.001,
      ref_price: 100, fill_price: null, notional_usd: 0.1, status: 'blocked', error: 'límite de pérdida diaria', broker_order_id: '', is_testnet: true },
  ],
  note: 'x',
}

describe('ExecutionAuditPanel', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('no pinta nada sin intentos', async () => {
    vi.spyOn(tradingService, 'getAudit').mockResolvedValue({
      status: 'EMPTY',
      summary: { total_attempts: 0, sent: 0, failed: 0, blocked: 0, executed_notional_usd: 0, fill_rate_pct: null, distinct_symbols: 0, blocked_reasons: [], failed_reasons: [] },
      entries: [],
    })
    const { container } = render(<ExecutionAuditPanel />)
    await waitFor(() => expect(tradingService.getAudit).toHaveBeenCalled())
    expect(container.textContent).toBe('')
  })

  it('muestra el resumen y el registro; filtra por estado', async () => {
    const spy = vi.spyOn(tradingService, 'getAudit').mockResolvedValue(AUDIT)
    render(<ExecutionAuditPanel />)
    await waitFor(() => expect(screen.getByText('Auditoría de ejecución real')).toBeInTheDocument())
    expect(screen.getAllByText('Bloqueada').length).toBeGreaterThanOrEqual(1)
    fireEvent.click(screen.getByRole('button', { name: 'Bloqueada' }))
    await waitFor(() => expect(spy).toHaveBeenCalledWith(expect.objectContaining({ status: 'blocked' })))
  })
})
