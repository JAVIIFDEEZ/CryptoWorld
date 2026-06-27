/**
 * hooks/useWallet.ts — Conexión de wallet on-chain (EIP-1193, sin dependencias).
 *
 * Usa el proveedor inyectado por el navegador (window.ethereum: MetaMask, Rabby,
 * Coinbase Wallet…) directamente, sin librerías pesadas. Expone la dirección
 * conectada y la red, y mapea el chainId a los slugs soportados por el explorador
 * on-chain para cargar la cartera del usuario con un clic.
 */

import { useCallback, useEffect, useState } from 'react'

interface Eip1193Provider {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>
  on?: (event: string, handler: (...args: unknown[]) => void) => void
  removeListener?: (event: string, handler: (...args: unknown[]) => void) => void
}

declare global {
  interface Window {
    ethereum?: Eip1193Provider
  }
}

// chainId (decimal) → slug de red soportada por el explorador (Blockscout).
const CHAIN_ID_TO_SLUG: Record<number, string> = {
  1: 'ethereum',
  10: 'optimism',
  100: 'gnosis',
  8453: 'base',
  42161: 'arbitrum',
}

export function chainSlugFromId(chainId: number | null): string | null {
  return chainId != null ? (CHAIN_ID_TO_SLUG[chainId] ?? null) : null
}

function parseChainId(hex: unknown): number | null {
  if (typeof hex === 'string') {
    const n = Number.parseInt(hex, 16)
    return Number.isFinite(n) ? n : null
  }
  if (typeof hex === 'number') return hex
  return null
}

export interface WalletState {
  available: boolean
  address: string | null
  chainId: number | null
  chainSlug: string | null
  connecting: boolean
  error: string | null
  connect: () => Promise<void>
  disconnect: () => void
}

export function useWallet(): WalletState {
  const provider = typeof window !== 'undefined' ? window.ethereum : undefined
  const available = !!provider
  const [address, setAddress] = useState<string | null>(null)
  const [chainId, setChainId] = useState<number | null>(null)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const connect = useCallback(async () => {
    if (!provider) { setError('No hay ninguna wallet instalada en el navegador.'); return }
    setConnecting(true); setError(null)
    try {
      const accounts = await provider.request({ method: 'eth_requestAccounts' }) as string[]
      setAddress(accounts?.[0] ?? null)
      const cid = await provider.request({ method: 'eth_chainId' })
      setChainId(parseChainId(cid))
    } catch (e: unknown) {
      const msg = (e as { message?: string })?.message ?? 'No se pudo conectar la wallet.'
      setError(msg)
    } finally {
      setConnecting(false)
    }
  }, [provider])

  const disconnect = useCallback(() => {
    setAddress(null)
    setChainId(null)
    setError(null)
  }, [])

  // Sincroniza con cambios de cuenta/red en la wallet.
  useEffect(() => {
    if (!provider?.on) return
    const onAccounts = (...args: unknown[]) => {
      const accs = args[0] as string[]
      setAddress(accs?.[0] ?? null)
    }
    const onChain = (...args: unknown[]) => setChainId(parseChainId(args[0]))
    provider.on('accountsChanged', onAccounts)
    provider.on('chainChanged', onChain)
    return () => {
      provider.removeListener?.('accountsChanged', onAccounts)
      provider.removeListener?.('chainChanged', onChain)
    }
  }, [provider])

  return {
    available,
    address,
    chainId,
    chainSlug: chainSlugFromId(chainId),
    connecting,
    error,
    connect,
    disconnect,
  }
}
