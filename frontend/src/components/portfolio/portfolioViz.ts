/**
 * components/portfolio/portfolioViz.ts — Cálculos de las visualizaciones de cartera.
 *
 * A partir de los sparklines 7d de cada posición abierta deriva: matriz de
 * correlación entre holdings (diversificación) y, por activo, retorno 7d,
 * volatilidad y peso en la cartera (riesgo/retorno). Cálculo en cliente, sin
 * backend.
 */

import type { Position } from '@/services/portfolioService'

export interface RiskReturnPoint {
  symbol: string
  ret: number      // retorno 7d (%)
  vol: number      // volatilidad (desv. típica de retornos, %)
  weight: number   // peso en la cartera (0..1)
  value: number    // valor de mercado (USD)
}

export interface CorrelationData {
  symbols: string[]
  matrix: number[][]   // NxN en [-1, 1]
}

function returns(spark: number[]): number[] {
  const r: number[] = []
  for (let i = 1; i < spark.length; i++) {
    if (spark[i - 1] > 0) r.push((spark[i] - spark[i - 1]) / spark[i - 1])
  }
  return r
}

function stdev(xs: number[]): number {
  if (xs.length < 2) return 0
  const m = xs.reduce((s, x) => s + x, 0) / xs.length
  return Math.sqrt(xs.reduce((s, x) => s + (x - m) ** 2, 0) / xs.length)
}

function pearson(a: number[], b: number[]): number {
  const n = Math.min(a.length, b.length)
  if (n < 3) return 0
  const x = a.slice(-n), y = b.slice(-n)
  const mx = x.reduce((s, v) => s + v, 0) / n
  const my = y.reduce((s, v) => s + v, 0) / n
  let num = 0, dx = 0, dy = 0
  for (let i = 0; i < n; i++) {
    num += (x[i] - mx) * (y[i] - my)
    dx += (x[i] - mx) ** 2
    dy += (y[i] - my) ** 2
  }
  const den = Math.sqrt(dx * dy)
  return den === 0 ? 0 : Math.max(-1, Math.min(1, num / den))
}

function value(p: Position): number {
  return (Number.parseFloat(p.current_price) || 0) * (Number.parseFloat(p.open_quantity) || 0)
}

/** Holdings con sparkline suficiente, ordenados por valor descendente y limitados. */
function eligible(positions: Position[], sparks: Record<string, number[]>, limit: number): Position[] {
  return [...positions]
    .filter((p) => (sparks[p.asset_symbol]?.length ?? 0) >= 4)
    .sort((a, b) => value(b) - value(a))
    .slice(0, limit)
}

export function buildCorrelation(positions: Position[], sparks: Record<string, number[]>, limit = 8): CorrelationData {
  const used = eligible(positions, sparks, limit)
  const symbols = used.map((p) => p.asset_symbol)
  const rets = used.map((p) => returns(sparks[p.asset_symbol]))
  const matrix = symbols.map((_, i) =>
    symbols.map((__, j) => (i === j ? 1 : pearson(rets[i], rets[j]))),
  )
  return { symbols, matrix }
}

export function buildRiskReturn(positions: Position[], sparks: Record<string, number[]>, limit = 12): RiskReturnPoint[] {
  const used = eligible(positions, sparks, limit)
  const total = used.reduce((s, p) => s + value(p), 0) || 1
  return used.map((p) => {
    const spark = sparks[p.asset_symbol]
    const rets = returns(spark)
    const ret = spark.length >= 2 && spark[0] > 0 ? (spark[spark.length - 1] - spark[0]) / spark[0] * 100 : 0
    return {
      symbol: p.asset_symbol,
      ret,
      vol: stdev(rets) * 100,
      weight: value(p) / total,
      value: value(p),
    }
  })
}

/** Color de correlación: azul (−1, diversifica) → gris (0) → rojo (+1, redundante). */
export function correlationColor(c: number): string {
  if (c >= 0) {
    const r = Math.round(90 + c * 130)
    return `rgb(${r}, ${Math.round(90 - c * 50)}, ${Math.round(95 - c * 50)})`
  }
  const b = Math.round(90 + -c * 140)
  return `rgb(${Math.round(70 - -c * 20)}, ${Math.round(110 + -c * 40)}, ${b})`
}
