/**
 * useCurrency.ts — Hook de moneda preferida + Context Provider.
 *
 * Todos los precios del backend llegan en USD. Este contexto centraliza:
 *   - La moneda preferida del usuario (sincronizada con /auth/me/ y
 *     persistida en localStorage para no parpadear al recargar).
 *   - Las tasas de cambio USD→EUR/GBP (GET /api/market/fx/).
 *   - Formateadores ya convertidos (formatPrice/formatCompact) que las
 *     páginas usan en lugar de los de utils/format.
 *
 * Mismo patrón que useAuth: React Context + Custom Hook.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { useAuth } from '@/hooks/useAuth'
import { authService } from '@/services/authService'
import { marketService } from '@/services/marketService'
import {
  formatPrice as basePrice,
  formatCompact as baseCompact,
  type FiatCurrency,
} from '@/utils/format'

const CURRENCY_KEY = 'cw_currency'

interface CurrencyContextType {
  /** Moneda activa ('usd' | 'eur' | 'gbp'). */
  currency: FiatCurrency
  /** Unidades de la moneda activa por 1 USD. */
  rate: number
  /** Cambia la moneda activa (la persistencia en backend la hace Ajustes). */
  setCurrency: (currency: FiatCurrency) => void
  /** Precio convertido a la moneda activa. */
  formatPrice: (value: number | string | null | undefined) => string
  /** Cifra compacta (market cap, volumen) convertida a la moneda activa. */
  formatCompact: (value: number | string | null | undefined) => string
}

const CurrencyContext = createContext<CurrencyContextType | undefined>(undefined)

function isFiatCurrency(value: string | null): value is FiatCurrency {
  return value === 'usd' || value === 'eur' || value === 'gbp'
}

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth()

  const [currency, setCurrencyState] = useState<FiatCurrency>(() => {
    const stored = localStorage.getItem(CURRENCY_KEY)
    return isFiatCurrency(stored) ? stored : 'usd'
  })
  const [rates, setRates] = useState<Record<string, number>>({ usd: 1 })

  // Tasas de cambio: una vez por sesión (cachés en memoria y Redis detrás)
  useEffect(() => {
    let cancelled = false
    marketService
      .getFxRates()
      .then((fx) => {
        if (!cancelled) setRates(fx.rates)
      })
      .catch(() => {
        // Sin tasas la app sigue en USD (rate 1): degradación silenciosa
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Sincronizar con la preferencia guardada en el backend al autenticarse
  useEffect(() => {
    if (!isAuthenticated) return
    let cancelled = false
    authService
      .me()
      .then((me) => {
        if (!cancelled && isFiatCurrency(me.preferred_currency)) {
          setCurrencyState(me.preferred_currency)
          localStorage.setItem(CURRENCY_KEY, me.preferred_currency)
        }
      })
      .catch(() => {
        // Mantener la última moneda conocida (localStorage)
      })
    return () => {
      cancelled = true
    }
  }, [isAuthenticated])

  const setCurrency = useCallback((next: FiatCurrency) => {
    setCurrencyState(next)
    localStorage.setItem(CURRENCY_KEY, next)
  }, [])

  const rate = rates[currency] ?? 1

  const formatPrice = useCallback(
    (value: number | string | null | undefined) => basePrice(value, currency, rate),
    [currency, rate],
  )
  const formatCompact = useCallback(
    (value: number | string | null | undefined) => baseCompact(value, currency, rate),
    [currency, rate],
  )

  const value = useMemo(
    () => ({ currency, rate, setCurrency, formatPrice, formatCompact }),
    [currency, rate, setCurrency, formatPrice, formatCompact],
  )

  return React.createElement(CurrencyContext.Provider, { value }, children)
}

/**
 * useCurrency — Acceder a la moneda activa y sus formateadores.
 * Lanza un error claro si se usa fuera del CurrencyProvider.
 */
export function useCurrency(): CurrencyContextType {
  const context = useContext(CurrencyContext)
  if (context === undefined) {
    throw new Error('useCurrency debe usarse dentro de un CurrencyProvider')
  }
  return context
}
