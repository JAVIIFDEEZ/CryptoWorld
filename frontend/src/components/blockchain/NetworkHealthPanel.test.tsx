/**
 * NetworkHealthPanel.test.tsx — Salud de red con almacén propio.
 *
 * Lo que este panel no puede hacer es presentar un dato de hace tres horas como
 * si fuera de ahora. Antes, cuando la fuente fallaba, se quedaba vacío; ahora
 * sirve lo guardado, y por eso mismo tiene la obligación de decir que es viejo.
 *
 * Tampoco puede pintar cuatro lecturas como si fueran una tendencia mientras el
 * histórico se llena.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import NetworkHealthPanel from './NetworkHealthPanel'
import { blockchainService, type ChainHealth, type ChainMetricHistory } from '@/services/blockchainService'

function health(over: Partial<ChainHealth> = {}): ChainHealth {
  return {
    chain: 'ethereum', chain_name: 'Ethereum', native_symbol: 'ETH',
    explorer_url: 'https://eth.blockscout.com',
    gas_slow: 10, gas_average: 12, gas_fast: 16,
    gas_level: 'normal', gas_text: 'Gas en niveles normales (12 Gwei).',
    gas_unit: 'Gwei', gas_updated_at: null,
    network_utilization_pct: 55, block_time_sec: 12,
    coin_price_usd: 3000, coin_price_change_pct: 1.2,
    total_transactions: '1', total_blocks: '1', total_addresses: '1',
    transactions_today: '1200000', source: 'blockscout', stale: false,
    ...over,
  }
}

function history(n: number): ChainMetricHistory {
  return {
    chain: 'ethereum', metric: 'gas_average', days: 7,
    points: Array.from({ length: n }, (_, i) => ({ t: 1_700_000_000_000 + i * 300_000, v: 10 + i })),
    coverage: { chain: 'ethereum', points: n, metrics: 1, first: 1, last: 2, span_days: 1, note: '' },
  }
}

beforeEach(() => {
  vi.restoreAllMocks()
  vi.spyOn(blockchainService, 'getWalletChains').mockResolvedValue([])
  vi.spyOn(blockchainService, 'getChainHistory').mockResolvedValue(history(0))
})

describe('NetworkHealthPanel', () => {
  it('avisa de que el dato es del almacén y cuánto tiene', async () => {
    vi.spyOn(blockchainService, 'getChainHealth').mockResolvedValue(health({
      stale: true, data_age_seconds: 10_800,
      note: 'La fuente en vivo no responde. Estos datos son del almacén propio y tienen 180 min de antigüedad.',
      source: 'store',
    }))
    render(<NetworkHealthPanel />)
    expect(await screen.findByText(/no en vivo/i)).toBeInTheDocument()
    // Sale en la línea de edad y otra vez en la nota del backend.
    expect(screen.getAllByText(/180 min de antigüedad/).length).toBeGreaterThan(0)
  })

  it('no pone el aviso cuando el dato sí es en vivo', async () => {
    vi.spyOn(blockchainService, 'getChainHealth').mockResolvedValue(health())
    render(<NetworkHealthPanel />)
    await screen.findByText(/Gas en niveles normales/)
    expect(screen.queryByText(/no en vivo/i)).not.toBeInTheDocument()
  })

  it('dice cuándo el veredicto sale de un umbral fijo y no de la historia', async () => {
    vi.spyOn(blockchainService, 'getChainHealth').mockResolvedValue(health({ gas_basis: 'fixed' }))
    render(<NetworkHealthPanel />)
    expect(await screen.findByText(/umbral fijo/i)).toBeInTheDocument()
  })

  it('muestra el rango propio cuando el veredicto viene del percentil', async () => {
    vi.spyOn(blockchainService, 'getChainHealth').mockResolvedValue(health({
      gas_basis: 'history',
      gas_percentile: { percentile: 18, n_points: 900, days: 30, min: 8, median: 22, max: 90 },
    }))
    render(<NetworkHealthPanel />)
    expect(await screen.findByText(/8–90 Gwei/)).toBeInTheDocument()
    expect(screen.getByText(/900 lecturas/)).toBeInTheDocument()
  })

  it('no dibuja una tendencia con cuatro lecturas', async () => {
    vi.spyOn(blockchainService, 'getChainHealth').mockResolvedValue(health())
    vi.spyOn(blockchainService, 'getChainHistory').mockResolvedValue(history(4))
    render(<NetworkHealthPanel />)
    expect(await screen.findByText(/se está llenando/i)).toBeInTheDocument()
  })

  it('dibuja la evolución cuando ya hay histórico suficiente', async () => {
    vi.spyOn(blockchainService, 'getChainHealth').mockResolvedValue(health())
    vi.spyOn(blockchainService, 'getChainHistory').mockResolvedValue(history(40))
    render(<NetworkHealthPanel />)
    await waitFor(() => expect(screen.getByRole('img', { name: /evolución del gas/i })).toBeInTheDocument())
    expect(screen.queryByText(/se está llenando/i)).not.toBeInTheDocument()
  })
})
