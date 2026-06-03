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

function toNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'string' ? parseFloat(value) : value
  return Number.isFinite(n) ? n : null
}

/**
 * Precio en USD con decimales adaptados a la magnitud:
 * precios grandes 2 decimales, pequeños hasta 6.
 *   79061    → "$79,061.00"
 *   1.43     → "$1.43"
 *   0.0352   → "$0.0352"
 */
export function formatPrice(value: number | string | null | undefined): string {
  const n = toNumber(value)
  if (n === null) return '—'
  const abs = Math.abs(n)
  const decimals = abs >= 1 ? 2 : abs >= 0.01 ? 4 : 6
  return n.toLocaleString(LOCALE, {
    style: 'currency',
    currency: 'USD',
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
export function formatCompact(value: number | string | null | undefined): string {
  const n = toNumber(value)
  if (n === null) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e12) return `$${(n / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(abs >= 1e11 ? 1 : 2)}B`
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `$${(n / 1e3).toFixed(1)}K`
  return `$${n.toFixed(2)}`
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
