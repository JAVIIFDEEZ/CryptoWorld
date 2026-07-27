/**
 * PredictionMonitoringPanel.test.tsx — Dashboard de drift del modelo.
 *
 * Verifica que, dado el resultado de monitorización del servicio, el panel pinta
 * la insignia de estado correcta (estable/vigilancia/drift) y las métricas
 * prometida/realizada/brecha; y que se oculta cuando no hay nada resuelto.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import PredictionMonitoringPanel from './PredictionMonitoringPanel'
import { analysisService, type PredictionMonitoring } from '@/services/analysisService'

vi.mock('@/services/analysisService', async (orig) => {
  const actual = await orig<typeof import('@/services/analysisService')>()
  return { ...actual, analysisService: { ...actual.analysisService, getPredictionMonitoring: vi.fn() } }
})

const base: PredictionMonitoring = {
  status: 'ok',
  message: 'Estable: en línea con lo prometido.',
  expected_accuracy: 0.56,
  realized_accuracy: 0.58,
  gap: 0.02,
  n_resolved: 12,
  min_sample: 10,
  series: [
    { from: '2026-06-01T00:00:00Z', to: '2026-06-02T00:00:00Z', n: 6, accuracy: 0.6 },
    { from: '2026-06-03T00:00:00Z', to: '2026-06-04T00:00:00Z', n: 6, accuracy: 0.56 },
  ],
  by_asset: { BTC: { n: 12, accuracy: 0.58 } },
  thresholds: { watch: -0.08, drift: -0.15 },
}

describe('PredictionMonitoringPanel', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders the OK status badge and expected/realized metrics', async () => {
    vi.mocked(analysisService.getPredictionMonitoring).mockResolvedValue(base)
    render(<PredictionMonitoringPanel />)
    await waitFor(() => expect(screen.getByText('● Estable')).toBeInTheDocument())
    expect(screen.getByText('56.0%')).toBeInTheDocument() // prometida
    expect(screen.getByText('58.0%')).toBeInTheDocument() // realizada
    expect(screen.getByText('+2.0%')).toBeInTheDocument() // brecha
  })

  it('renders a drift badge when the model degrades', async () => {
    vi.mocked(analysisService.getPredictionMonitoring).mockResolvedValue({
      ...base, status: 'drift', gap: -0.35, realized_accuracy: 0.25,
      message: 'Degradación: conviene reoptimizar.',
    })
    render(<PredictionMonitoringPanel />)
    await waitFor(() => expect(screen.getByText(/Drift detectado/)).toBeInTheDocument())
    expect(screen.getByText('-35.0%')).toBeInTheDocument()
  })

  it('renders nothing when there are no resolved predictions', async () => {
    vi.mocked(analysisService.getPredictionMonitoring).mockResolvedValue({
      ...base, status: 'insufficient', n_resolved: 0, expected_accuracy: null,
      realized_accuracy: null, gap: null, series: [], by_asset: {},
    })
    const { container } = render(<PredictionMonitoringPanel />)
    await waitFor(() => expect(analysisService.getPredictionMonitoring).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })
})
