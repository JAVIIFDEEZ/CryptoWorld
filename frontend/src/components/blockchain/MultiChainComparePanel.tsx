/**
 * components/blockchain/MultiChainComparePanel.tsx — Comparador de cadenas.
 *
 * Obtiene en paralelo los stats de un conjunto curado de blockchains y los
 * compara con un conmutador 3D/2D. Resiliente: ignora las cadenas que fallen.
 */

import { lazy, useEffect, useMemo, useState } from 'react'
import { blockchainService, MULTICHAIN_SYMBOLS, type MultiChainStatItem } from '@/services/blockchainService'
import Viz3DSwitch from '@/components/viz3d/Viz3DSwitch'
import MultiChainBars2D from './MultiChainBars2D'
import { buildComparison } from './blockchainViz'

const MultiChainBars3D = lazy(() => import('./MultiChainBars3D'))

// Subconjunto curado (cadenas con stats ricos y comparables) para no saturar la API.
const COMPARE_CHAINS = MULTICHAIN_SYMBOLS.slice(0, 6)

export default function MultiChainComparePanel() {
  const [statsByChain, setStatsByChain] = useState<Record<string, MultiChainStatItem[]>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const results = await Promise.allSettled(
        COMPARE_CHAINS.map((c) => blockchainService.getMultiChainStats(c)),
      )
      if (cancelled) return
      const map: Record<string, MultiChainStatItem[]> = {}
      results.forEach((r, i) => {
        if (r.status === 'fulfilled' && r.value && !r.value.error && r.value.stats?.length) {
          map[COMPARE_CHAINS[i]] = r.value.stats
        }
      })
      if (Object.keys(map).length < 2) setError('No se pudieron comparar suficientes cadenas.')
      setStatsByChain(map)
      setLoading(false)
    })()
    return () => { cancelled = true }
  }, [])

  const data = useMemo(() => buildComparison(statsByChain), [statsByChain])

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-10 flex items-center justify-center gap-3">
        <div className="w-6 h-6 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
        <span className="text-slate-400 text-sm">Comparando cadenas…</span>
      </div>
    )
  }
  if (error && data.chains.length < 2) {
    return <div className="bg-slate-800 rounded-xl border border-slate-700 p-6 text-slate-500 text-sm text-center">{error}</div>
  }

  return (
    <Viz3DSwitch
      title="Comparador de blockchains"
      hint={`${data.chains.length} cadenas × ${data.metrics.length} métricas · valores normalizados por métrica`}
      threeD={<MultiChainBars3D data={data} />}
      twoD={<MultiChainBars2D data={data} />}
    />
  )
}
