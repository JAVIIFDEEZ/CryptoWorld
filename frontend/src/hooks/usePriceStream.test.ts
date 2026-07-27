/**
 * usePriceStream.test.ts — Precios en tiempo real por WebSocket.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { priceStreamUrl, usePriceStream } from './usePriceStream'

class MockWebSocket {
  static last: MockWebSocket | null = null
  onopen: ((e: unknown) => void) | null = null
  onmessage: ((e: { data: string }) => void) | null = null
  onclose: ((e: unknown) => void) | null = null
  onerror: ((e: unknown) => void) | null = null
  readyState = 0
  url: string
  constructor(url: string) { this.url = url; MockWebSocket.last = this }
  close() { this.readyState = 3; this.onclose?.({}) }
}

describe('priceStreamUrl', () => {
  it('derives a ws/wss url ending in /ws/prices/', () => {
    const url = priceStreamUrl()
    expect(url).toMatch(/^wss?:\/\//)
    expect(url.endsWith('/ws/prices/')).toBe(true)
  })
})

describe('usePriceStream', () => {
  beforeEach(() => { MockWebSocket.last = null; vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket) })
  afterEach(() => { vi.unstubAllGlobals() })

  it('marks connected on open and applies price_update messages', async () => {
    const { result } = renderHook(() => usePriceStream())
    const ws = MockWebSocket.last!
    expect(ws).toBeTruthy()

    act(() => { ws.onopen?.({}) })
    await waitFor(() => expect(result.current.connected).toBe(true))

    act(() => {
      ws.onmessage?.({ data: JSON.stringify({ type: 'price_update', data: [
        { symbol: 'BTC', price: 60000, change: 1.5 },
        { symbol: 'ETH', price: 1600, change: -0.8 },
      ] }) })
    })
    await waitFor(() => expect(result.current.prices.BTC?.price).toBe(60000))
    expect(result.current.prices.ETH?.change).toBe(-0.8)
  })

  it('ignores non price_update messages', async () => {
    const { result } = renderHook(() => usePriceStream())
    const ws = MockWebSocket.last!
    act(() => { ws.onmessage?.({ data: JSON.stringify({ type: 'connected' }) }) })
    act(() => { ws.onmessage?.({ data: 'not-json' }) })
    expect(Object.keys(result.current.prices)).toHaveLength(0)
  })
})
