/**
 * components/blockchain/blockchainViz.ts — Datos del comparador multi-cadena.
 *
 * Toma los stats (heterogéneos) de varias cadenas y construye una matriz
 * cadena × métrica normalizada por métrica (min-max), para que valores de
 * unidades muy distintas (USD, recuentos, %) sean comparables visualmente.
 */

import type { MultiChainStatItem } from '@/services/blockchainService'

export interface CompareData {
  chains: string[]
  metrics: { key: string; label: string; unit: string }[]
  norm: (number | null)[][]   // [chain][metric] en [0,1]
  raw: (number | null)[][]    // valor original
}

function toNumber(v: number | string | null): number | null {
  if (v === null || v === undefined) return null
  const n = typeof v === 'string' ? Number.parseFloat(v) : v
  return Number.isFinite(n) ? n : null
}

/**
 * Selecciona las métricas numéricas presentes en al menos la mitad de las
 * cadenas (hasta `maxMetrics`) y normaliza cada una a [0,1] entre cadenas.
 */
export function buildComparison(
  statsByChain: Record<string, MultiChainStatItem[]>,
  maxMetrics = 6,
): CompareData {
  const chains = Object.keys(statsByChain)
  if (chains.length < 2) return { chains, metrics: [], norm: [], raw: [] }

  // Contar métricas numéricas por clave
  const meta = new Map<string, { label: string; unit: string; count: number }>()
  for (const chain of chains) {
    for (const s of statsByChain[chain]) {
      if (toNumber(s.value) === null) continue
      const m = meta.get(s.key)
      if (m) m.count += 1
      else meta.set(s.key, { label: s.label, unit: s.unit, count: 1 })
    }
  }

  const metrics = [...meta.entries()]
    .filter(([, m]) => m.count >= Math.ceil(chains.length / 2))
    .sort((a, b) => b[1].count - a[1].count)
    .slice(0, maxMetrics)
    .map(([key, m]) => ({ key, label: m.label, unit: m.unit }))

  const lookup = (chain: string, key: string): number | null => {
    const item = statsByChain[chain].find((s) => s.key === key)
    return item ? toNumber(item.value) : null
  }

  const raw = chains.map((c) => metrics.map((m) => lookup(c, m.key)))

  const norm = metrics.map((_, j) => {
    const col = raw.map((row) => row[j]).filter((v): v is number => v !== null)
    const min = col.length ? Math.min(...col) : 0
    const max = col.length ? Math.max(...col) : 1
    const range = max - min || 1
    return raw.map((row) => (row[j] === null ? null : (row[j]! - min) / range))
  })

  // Transponer norm a [chain][metric]
  const normByChain = chains.map((_, i) => metrics.map((__, j) => norm[j][i]))
  return { chains, metrics, norm: normByChain, raw }
}

export const METRIC_PALETTE = ['#3b82f6', '#22c55e', '#eab308', '#a855f7', '#ec4899', '#14b8a6']
