/**
 * utils/format.ts — Formateo consistente de números financieros.
 *
 * Usa la convención de trading internacional (en-US): separador de
 * miles con coma y decimal con punto ($79,061.00). Es el formato que
 * usan Binance, CoinGecko o TradingView y el que aporta sensación de
 * producto serio. Combinar siempre con la utilidad Tailwind
 * `tabular-nums` para que las columnas de números alineen.
 *
 * Para volver al formato europeo basta con cambiar LOCALE a 'es-ES'.
 */

const LOCALE = 'en-US'

/** Monedas fiat soportadas (alineadas con preferred_currency del backend). */
export type FiatCurrency = 'usd' | 'eur' | 'gbp'

const CURRENCY_SYMBOLS: Record<FiatCurrency, string> = {
  usd: '$',
  eur: '€',
  gbp: '£',
}

function toNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'string' ? parseFloat(value) : value
  return Number.isFinite(n) ? n : null
}

/**
 * Precio con decimales adaptados a la magnitud:
 * precios grandes 2 decimales, pequeños hasta 6.
 *   79061    → "$79,061.00"
 *   1.43     → "$1.43"
 *   0.0352   → "$0.0352"
 *
 * Los valores del sistema están en USD; `currency` + `rate` permiten
 * mostrar en la moneda preferida del usuario (rate = unidades por USD).
 * Sin argumentos extra el comportamiento es idéntico al histórico (USD).
 */
export function formatPrice(
  value: number | string | null | undefined,
  currency: FiatCurrency = 'usd',
  rate = 1,
): string {
  const n = toNumber(value)
  if (n === null) return '—'
  const converted = n * rate
  const abs = Math.abs(converted)
  const decimals = abs >= 1 ? 2 : abs >= 0.01 ? 4 : 6
  return converted.toLocaleString(LOCALE, {
    style: 'currency',
    currency: currency.toUpperCase(),
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/**
 * Cifra grande en notación compacta: market cap, volumen.
 *   2_660_000_000_000 → "$2.66T"
 *   71_000_000_000    → "$71.0B"
 *   18_110_000_000    → "$18.11B"
 */
export function formatCompact(
  value: number | string | null | undefined,
  currency: FiatCurrency = 'usd',
  rate = 1,
): string {
  const n0 = toNumber(value)
  if (n0 === null) return '—'
  const n = n0 * rate
  const symbol = CURRENCY_SYMBOLS[currency]
  const abs = Math.abs(n)
  if (abs >= 1e12) return `${symbol}${(n / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `${symbol}${(n / 1e9).toFixed(abs >= 1e11 ? 1 : 2)}B`
  if (abs >= 1e6) return `${symbol}${(n / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `${symbol}${(n / 1e3).toFixed(1)}K`
  return `${symbol}${n.toFixed(2)}`
}

/**
 * Porcentaje con signo: "+2.34%" / "-1.20%".
 */
export function formatPercent(
  value: number | string | null | undefined,
  decimals = 2,
): string {
  const n = toNumber(value)
  if (n === null) return '—'
  const sign = n > 0 ? '+' : ''
  return `${sign}${n.toFixed(decimals)}%`
}

/**
 * Número entero con separador de miles: "1,583" / "704,910".
 */
export function formatNumber(
  value: number | string | null | undefined,
  decimals = 0,
): string {
  const n = toNumber(value)
  if (n === null) return '—'
  return n.toLocaleString(LOCALE, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}
