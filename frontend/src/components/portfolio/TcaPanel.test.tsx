/**
 * TcaPanel.test.tsx — Analítica de coste de ejecución.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import TcaPanel from './TcaPanel'
import { tradingService, type ExecutionTca } from '@/services/tradingService'

const OK: ExecutionTca = {
  status: 'OK', fills: 2, total_notional_usd: 200, avg_slippage_bps: 3,
  total_cost_usd: 0.06, fill_rate_pct: 66.7,
  worst: { symbol: 'BTC/USDT', side: 'sell', slippage_bps: 4, cost_usd: 0.04 },
  best: { symbol: 'BTC/USDT', side: 'buy', slippage_bps: 2, cost_usd: 0.02 },
  by_symbol: [{ symbol: 'BTC/USDT', fills: 2, notional_usd: 200, cost_usd: 0.06, avg_slippage_bps: 3 }],
  orders_analyzed: 3, note: 'x',
}

describe('TcaPanel', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('no pinta nada sin ejecuciones', async () => {
    vi.spyOn(tradingService, 'getTca').mockResolvedValue({ status: 'EMPTY', fills: 0 })
    const { container } = render(<TcaPanel />)
    await waitFor(() => expect(tradingService.getTca).toHaveBeenCalled())
    expect(container.textContent).toBe('')
  })

  it('muestra slippage, fill rate y desglose por símbolo', async () => {
    vi.spyOn(tradingService, 'getTca').mockResolvedValue(OK)
    render(<TcaPanel />)
    await waitFor(() => expect(screen.getByText('Coste de ejecución (TCA)')).toBeInTheDocument())
    expect(screen.getByText('3.00 bps')).toBeInTheDocument()
    expect(screen.getByText('67%')).toBeInTheDocument()
    expect(screen.getByText('BTC/USDT')).toBeInTheDocument()
  })
})
