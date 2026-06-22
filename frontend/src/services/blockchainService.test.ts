/**
 * blockchainService.test.ts — Contrato del servicio de blockchain.
 *
 * Verifica que los métodos del explorador de wallets llaman al endpoint correcto
 * y desempaquetan bien la respuesta, con axios mockeado.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import apiClient from '@/services/api'
import { blockchainService } from './blockchainService'

vi.mock('@/services/api', () => ({
  default: { get: vi.fn() },
}))

const mockApi = apiClient as unknown as { get: ReturnType<typeof vi.fn> }

beforeEach(() => { mockApi.get.mockReset() })

describe('blockchainService wallet explorer', () => {
  it('getWalletChains unwraps the chains array', async () => {
    mockApi.get.mockResolvedValue({ data: { chains: [{ slug: 'ethereum', name: 'Ethereum' }] } })
    const r = await blockchainService.getWalletChains()
    expect(mockApi.get).toHaveBeenCalledWith('/blockchain/wallet/chains/')
    expect(r[0].slug).toBe('ethereum')
  })

  it('getWalletOverview hits the wallet endpoint with chain and address', async () => {
    mockApi.get.mockResolvedValue({ data: { address: '0xabc', portfolio_value_usd: 100 } })
    const r = await blockchainService.getWalletOverview('base', '0xABC')
    const url = mockApi.get.mock.calls[0][0] as string
    expect(url.startsWith('/blockchain/wallet/?')).toBe(true)
    expect(url).toContain('chain=base')
    expect(url).toContain('address=0xABC')
    expect(r.portfolio_value_usd).toBe(100)
  })

  it('getMultiChainStats forwards the symbol', async () => {
    mockApi.get.mockResolvedValue({ data: { symbol: 'ETH', stats: [] } })
    const r = await blockchainService.getMultiChainStats('ETH')
    expect(mockApi.get).toHaveBeenCalledWith('/blockchain/multichain/?symbol=ETH')
    expect(r.symbol).toBe('ETH')
  })
})
