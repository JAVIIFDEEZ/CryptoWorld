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
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

const mockApi = apiClient as unknown as {
  get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn>; delete: ReturnType<typeof vi.fn>
}

beforeEach(() => { mockApi.get.mockReset(); mockApi.post.mockReset(); mockApi.delete.mockReset() })

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

  it('getChainHealth hits the health endpoint with chain', async () => {
    mockApi.get.mockResolvedValue({ data: { chain: 'ethereum', gas_level: 'cheap' } })
    const r = await blockchainService.getChainHealth('ethereum')
    expect((mockApi.get.mock.calls[0][0] as string)).toContain('/blockchain/health/?chain=ethereum')
    expect(r.gas_level).toBe('cheap')
  })

  it('getWalletBalanceHistory hits the history endpoint', async () => {
    mockApi.get.mockResolvedValue({ data: { points: 2, history: [] } })
    await blockchainService.getWalletBalanceHistory('base', '0xABC')
    const url = mockApi.get.mock.calls[0][0] as string
    expect(url).toContain('/blockchain/wallet/history/?')
    expect(url).toContain('chain=base')
  })

  it('getWatchlist fetches the watchlist', async () => {
    mockApi.get.mockResolvedValue({ data: { count: 0, results: [], alerts: [] } })
    const r = await blockchainService.getWatchlist()
    expect(mockApi.get).toHaveBeenCalledWith('/blockchain/watchlist/')
    expect(r.count).toBe(0)
  })

  it('addWatchedAddress posts chain, address and optional fields', async () => {
    mockApi.post.mockResolvedValue({ data: { id: 1, address: '0xABC' } })
    await blockchainService.addWatchedAddress('ethereum', '0xABC', 'whale', 10)
    expect(mockApi.post).toHaveBeenCalledWith('/blockchain/watchlist/', {
      chain: 'ethereum', address: '0xABC', label: 'whale', threshold_pct: 10,
    })
  })

  it('addWatchedAddress omits optional fields when not given', async () => {
    mockApi.post.mockResolvedValue({ data: { id: 1 } })
    await blockchainService.addWatchedAddress('base', '0xABC')
    expect(mockApi.post).toHaveBeenCalledWith('/blockchain/watchlist/', { chain: 'base', address: '0xABC' })
  })

  it('removeWatchedAddress deletes by id', async () => {
    mockApi.delete.mockResolvedValue({ data: { id: 3, removed: true } })
    const r = await blockchainService.removeWatchedAddress(3)
    expect(mockApi.delete).toHaveBeenCalledWith('/blockchain/watchlist/3/')
    expect(r.removed).toBe(true)
  })

  it('getWhaleMovements forwards chain, min_usd and limit', async () => {
    mockApi.get.mockResolvedValue({ data: { count: 0, movements: [] } })
    await blockchainService.getWhaleMovements('ethereum', 1000000, 10)
    const url = mockApi.get.mock.calls[0][0] as string
    expect(url).toContain('/blockchain/movements/?')
    expect(url).toContain('chain=ethereum')
    expect(url).toContain('min_usd=1000000')
    expect(url).toContain('limit=10')
  })
})
