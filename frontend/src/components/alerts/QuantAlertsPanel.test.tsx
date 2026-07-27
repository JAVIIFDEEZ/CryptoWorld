/**
 * QuantAlertsPanel.test.tsx — Panel de alertas cuantitativas.
 *
 * Verifica la carga del catálogo + reglas, el formulario adaptativo
 * (activo solo para métricas de activo) y la creación de una alerta.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import QuantAlertsPanel from './QuantAlertsPanel'
import { quantAlertsService, type QuantMetric, type QuantAlert } from '../../services/quantAlertsService'

const METRICS: QuantMetric[] = [
  { key: 'rsi', label: 'RSI', unit: '', category: 'tecnica', scope: 'asset', hint: '0–100' },
  { key: 'portfolio_var', label: 'VaR de cartera', unit: '%', category: 'riesgo', scope: 'portfolio', hint: '' },
]

const ALERT: QuantAlert = {
  id: 1, asset_symbol: 'BTC', asset_name: 'Bitcoin', metric: 'rsi', metric_label: 'RSI',
  metric_unit: '', scope: 'asset', timeframe: '4h', operator: 'gt', threshold: 70,
  cooldown_minutes: 60, is_active: true, last_value: 55, last_fired_at: null, note: '',
  created_at: '2026-01-01T00:00:00Z',
}

describe('QuantAlertsPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.spyOn(quantAlertsService, 'list').mockResolvedValue({ alerts: [ALERT], metrics: METRICS })
    vi.spyOn(quantAlertsService, 'firings').mockResolvedValue([])
  })

  it('carga el catálogo y muestra la regla existente', async () => {
    render(<QuantAlertsPanel />)
    await waitFor(() => expect(screen.getByText(/Reglas \(1\)/)).toBeInTheDocument())
    expect(screen.getByRole('option', { name: /RSI/ })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /VaR de cartera/ })).toBeInTheDocument()
  })

  it('pide activo solo para métricas de activo', async () => {
    render(<QuantAlertsPanel />)
    await waitFor(() => expect(screen.getByText(/Reglas \(1\)/)).toBeInTheDocument())
    const metricSelect = screen.getByText('Métrica').parentElement!.querySelector('select')!
    // Métrica de activo → aparece el campo Activo
    fireEvent.change(metricSelect, { target: { value: 'rsi' } })
    expect(screen.getByPlaceholderText('BTC')).toBeInTheDocument()
    // Métrica de cartera → desaparece
    fireEvent.change(metricSelect, { target: { value: 'portfolio_var' } })
    expect(screen.queryByPlaceholderText('BTC')).not.toBeInTheDocument()
  })

  it('crea una alerta al enviar el formulario', async () => {
    const create = vi.spyOn(quantAlertsService, 'create').mockResolvedValue(ALERT)
    render(<QuantAlertsPanel />)
    await waitFor(() => expect(screen.getByText(/Reglas \(1\)/)).toBeInTheDocument())
    const metricSelect = screen.getByText('Métrica').parentElement!.querySelector('select')!
    fireEvent.change(metricSelect, { target: { value: 'rsi' } })
    fireEvent.change(screen.getByPlaceholderText('BTC'), { target: { value: 'eth' } })
    fireEvent.change(screen.getByPlaceholderText('70'), { target: { value: '75' } })
    fireEvent.click(screen.getByRole('button', { name: 'Crear alerta' }))
    await waitFor(() => expect(create).toHaveBeenCalledOnce())
    expect(create).toHaveBeenCalledWith(expect.objectContaining({
      metric: 'rsi', operator: 'gt', threshold: 75, asset_symbol: 'ETH',
    }))
  })
})
