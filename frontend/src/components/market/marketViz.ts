/**
 * components/market/marketViz.ts — Datos compartidos de las visualizaciones de mercado.
 *
 * Normaliza la lista de activos + sparklines 7d en "cuerpos" que consumen tanto
 * el universo 3D como el treemap 2D, para una sola fuente de verdad.
 */

import type { CryptoAsset } from '@/services/analysisService'

export interface MarketBody {
  symbol: string
  name: string
  logo: string | null
  price: number
  marketCap: number
  change: number       // variación 24h (%)
  volume: number
  volatility: number   // desviación típica de los retornos del sparkline 7d (%)
}

function num(v: string | null | undefined): number {
  if (!v) return 0
  const n = Number.parseFloat(v)
  return Number.isFinite(n) ? n : 0
}

/** Volatilidad = desviación típica de los retornos por punto del sparkline (%). */
function volatilityFromSpark(spark: number[] | undefined): number {
  if (!spark || spark.length < 3) return 0
  const rets: number[] = []
  for (let i = 1; i < spark.length; i++) {
    if (spark[i - 1] > 0) rets.push((spark[i] - spark[i - 1]) / spark[i - 1])
  }
  if (rets.length < 2) return 0
  const mean = rets.reduce((s, r) => s + r, 0) / rets.length
  const variance = rets.reduce((s, r) => s + (r - mean) ** 2, 0) / rets.length
  return Math.sqrt(variance) * 100
}

/**
 * Construye los cuerpos de mercado ordenados por capitalización descendente y
 * recortados a `limit` (rendimiento: el 3D pinta una esfera por cuerpo).
 */
export function buildMarketBodies(
  assets: CryptoAsset[],
  sparks: Record<string, number[]>,
  limit = 30,
): MarketBody[] {
  return [...assets]
    .sort((a, b) => num(b.market_cap) - num(a.market_cap))
    .slice(0, limit)
    .map((a) => ({
      symbol: a.symbol,
      name: a.name,
      logo: a.logo_url,
      price: num(a.current_price),
      marketCap: num(a.market_cap),
      change: num(a.price_change_24h),
      volume: num(a.volume_24h),
      volatility: volatilityFromSpark(sparks[a.symbol]),
    }))
    .filter((b) => b.marketCap > 0)
}

/** Color rojo→gris→verde según la variación 24h (saturando a ±10%). */
export function changeColor(change: number): string {
  const t = Math.max(-1, Math.min(1, change / 10))
  if (t >= 0) {
    // gris → verde
    const g = Math.round(110 + t * 100)
    return `rgb(${Math.round(70 - t * 30)}, ${g}, ${Math.round(90 + t * 40)})`
  }
  const r = Math.round(110 + -t * 120)
  return `rgb(${r}, ${Math.round(70 - -t * 20)}, ${Math.round(85 - -t * 20)})`
}
