/**
 * useWallet.test.ts — Conexión de wallet EIP-1193 (sin dependencias).
 */

import { describe, it, expect, vi, afterEach } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { chainSlugFromId, useWallet } from './useWallet'

describe('chainSlugFromId', () => {
  it('maps known chain ids to slugs', () => {
    expect(chainSlugFromId(1)).toBe('ethereum')
    expect(chainSlugFromId(8453)).toBe('base')
    expect(chainSlugFromId(10)).toBe('optimism')
    expect(chainSlugFromId(42161)).toBe('arbitrum')
    expect(chainSlugFromId(100)).toBe('gnosis')
  })

  it('returns null for unknown or missing ids', () => {
    expect(chainSlugFromId(999)).toBeNull()
    expect(chainSlugFromId(null)).toBeNull()
  })
})

describe('useWallet', () => {
  afterEach(() => { delete (window as { ethereum?: unknown }).ethereum })

  it('reports unavailable when no provider is injected', () => {
    const { result } = renderHook(() => useWallet())
    expect(result.current.available).toBe(false)
  })

  it('connects, exposes address and resolves the chain slug', async () => {
    ;(window as { ethereum?: unknown }).ethereum = {
      request: vi.fn(async ({ method }: { method: string }) => {
        if (method === 'eth_requestAccounts') return ['0xAbC0000000000000000000000000000000000001']
        if (method === 'eth_chainId') return '0x2105' // 8453 = Base
        return null
      }),
      on: vi.fn(),
      removeListener: vi.fn(),
    }
    const { result } = renderHook(() => useWallet())
    expect(result.current.available).toBe(true)
    await act(async () => { await result.current.connect() })
    await waitFor(() => expect(result.current.address).toBe('0xAbC0000000000000000000000000000000000001'))
    expect(result.current.chainId).toBe(8453)
    expect(result.current.chainSlug).toBe('base')
    act(() => result.current.disconnect())
    expect(result.current.address).toBeNull()
  })
})
