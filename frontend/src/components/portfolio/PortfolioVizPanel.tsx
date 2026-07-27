/**
 * components/portfolio/PortfolioVizPanel.tsx — Panel de visualizaciones de cartera.
 *
 * Obtiene los sparklines 7d de las posiciones abiertas y muestra dos análisis
 * con conmutador 3D/2D: matriz de correlación (diversificación) y mapa
 * riesgo/retorno. Se oculta con menos de 2 posiciones.
 */

import { lazy, useEffect, useMemo, useState } from 'react'
import { marketService } from '@/services/marketService'
import Viz3DSwitch from '@/components/viz3d/Viz3DSwitch'
import CorrelationHeatmap2D from './CorrelationHeatmap2D'
import RiskReturn2D from './RiskReturn2D'
import { buildCorrelation, buildRiskReturn } from './portfolioViz'
import type { Position } from '@/services/portfolioService'

const CorrelationMatrix3D = lazy(() => import('./CorrelationMatrix3D'))
const RiskReturn3D = lazy(() => import('./RiskReturn3D'))

export default function PortfolioVizPanel({ positions }: Readonly<{ positions: Position[] }>) {
  const [sparks, setSparks] = useState<Record<string, number[]>>({})
  const symbolsKey = useMemo(() => positions.map((p) => p.asset_symbol).sort().join(','), [positions])

  useEffect(() => {
    if (!symbolsKey) return
    let cancelled = false
    marketService.getSparklines(symbolsKey.split(','))
      .then((m) => { if (!cancelled) setSparks(m) })
      .catch(() => { /* sin sparklines */ })
    return () => { cancelled = true }
  }, [symbolsKey])

  const corr = useMemo(() => buildCorrelation(positions, sparks), [positions, sparks])
  const risk = useMemo(() => buildRiskReturn(positions, sparks), [positions, sparks])

  if (positions.length < 2) return null

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 mb-6">
      <Viz3DSwitch
        title="Correlación de la cartera"
        hint="Cómo se mueven juntos tus activos (7d) — clave para la diversificación"
        threeD={<CorrelationMatrix3D data={corr} />}
        twoD={<CorrelationHeatmap2D data={corr} />}
      />
      <Viz3DSwitch
        title="Riesgo / Retorno"
        hint="Volatilidad vs retorno 7d · tamaño = peso en la cartera"
        threeD={<RiskReturn3D points={risk} />}
        twoD={<RiskReturn2D points={risk} />}
      />
    </div>
  )
}
