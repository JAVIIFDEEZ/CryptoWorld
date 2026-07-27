/**
 * DataHealthPanel.test.tsx — Salud del almacén OHLCV.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import DataHealthPanel from './DataHealthPanel'
import { dataHealthService, type DataHealth } from '@/services/dataHealthService'

const OK: DataHealth = {
  status: 'OK',
  series: [
    { symbol: 'BTC', interval: '1h', candles: 500, gaps: 0, missing_candles: 0, first: 1, last: 2,
      completeness_pct: 100, freshness_hours: 1, fresh: true, status: 'SANO' },
    { symbol: 'ETH', interval: '1h', candles: 480, gaps: 2, missing_candles: 20, first: 1, last: 2,
      completeness_pct: 96, freshness_hours: 2, fresh: true, status: 'CON_HUECOS' },
  ],
  summary: { series: 2, healthy_pct: 50, with_gaps: 1, stale: 0, total_candles: 980, grade: 'ACEPTABLE' },
  note: 'x',
}

describe('DataHealthPanel', () => {
  beforeEach(() => { vi.restoreAllMocks() })

  it('muestra el resumen y las series con su estado', async () => {
    vi.spyOn(dataHealthService, 'get').mockResolvedValue(OK)
    render(<DataHealthPanel />)
    await waitFor(() => expect(screen.getByText('ACEPTABLE')).toBeInTheDocument())
    expect(screen.getByText('BTC · 1h')).toBeInTheDocument()
    expect(screen.getByText('Sano')).toBeInTheDocument()
    expect(screen.getAllByText('Con huecos').length).toBeGreaterThanOrEqual(1)
  })

  it('avisa cuando el almacén está vacío', async () => {
    vi.spyOn(dataHealthService, 'get').mockResolvedValue({
      status: 'EMPTY', series: [],
      summary: { series: 0, healthy_pct: 0, with_gaps: 0, stale: 0, total_candles: 0, grade: 'SIN_DATOS' },
    })
    render(<DataHealthPanel />)
    await waitFor(() => expect(screen.getByText(/aún no tiene datos/)).toBeInTheDocument())
  })
})
