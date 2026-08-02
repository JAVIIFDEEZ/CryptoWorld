/**
 * tradingService.test.ts — Contrato del servicio de trading real.
 *
 * El foco está en la idempotencia: la orden manual mueve dinero real, así que
 * cada intento debe llevar un `client_order_id` propio y un reintento
 * deliberado debe poder reutilizar el del intento original.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import apiClient from '@/services/api'
import { tradingService } from './tradingService'

vi.mock('@/services/api', () => ({
  default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

const mockApi = apiClient as unknown as {
  get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn>; delete: ReturnType<typeof vi.fn>
}

const okResponse = {
  data: { order: { id: '1', symbol: 'BTC/USDT', side: 'buy' }, is_testnet: true },
}

beforeEach(() => {
  mockApi.get.mockReset(); mockApi.post.mockReset(); mockApi.delete.mockReset()
})

function lastBody(): Record<string, unknown> {
  return mockApi.post.mock.calls[mockApi.post.mock.calls.length - 1][1]
}

describe('tradingService.placeOrder', () => {
  it('envía la orden al endpoint de la conexión con sus campos', async () => {
    mockApi.post.mockResolvedValue(okResponse)

    await tradingService.placeOrder(7, {
      symbol: 'BTC/USDT', side: 'buy', type: 'market', amount: 0.5,
    })

    expect(mockApi.post).toHaveBeenCalledWith(
      '/trading/connections/7/orders/', expect.objectContaining({
        symbol: 'BTC/USDT', side: 'buy', type: 'market', amount: 0.5,
      }),
    )
  })

  it('adjunta un client_order_id aunque quien llama no lo pase', async () => {
    mockApi.post.mockResolvedValue(okResponse)

    await tradingService.placeOrder(1, {
      symbol: 'BTC/USDT', side: 'buy', type: 'market', amount: 1,
    })

    const body = lastBody()
    expect(typeof body.client_order_id).toBe('string')
    expect((body.client_order_id as string).length).toBeGreaterThan(8)
  })

  it('da un identificador distinto a cada intento nuevo', async () => {
    mockApi.post.mockResolvedValue(okResponse)
    const payload = { symbol: 'BTC/USDT', side: 'buy' as const, type: 'market' as const, amount: 1 }

    await tradingService.placeOrder(1, payload)
    const first = lastBody().client_order_id
    await tradingService.placeOrder(1, payload)
    const second = lastBody().client_order_id

    expect(first).not.toBe(second)
  })

  it('respeta el client_order_id explícito para reintentar el mismo intento', async () => {
    mockApi.post.mockResolvedValue(okResponse)

    await tradingService.placeOrder(1, {
      symbol: 'BTC/USDT', side: 'buy', type: 'market', amount: 1,
      client_order_id: 'reintento-fijo',
    })

    expect(lastBody().client_order_id).toBe('reintento-fijo')
  })

  it('incluye el precio solo en las órdenes limit', async () => {
    mockApi.post.mockResolvedValue(okResponse)

    await tradingService.placeOrder(1, {
      symbol: 'BTC/USDT', side: 'sell', type: 'limit', amount: 2, price: 65000,
    })

    expect(lastBody().price).toBe(65000)
  })
})
