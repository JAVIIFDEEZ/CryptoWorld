/**
 * components/generator/Generator3DPanel.tsx — Visualizaciones 3D del generador.
 *
 * Pestañas entre las tres vistas WebGL (universo de robustez, paisaje evolutivo
 * y ADN de la estrategia). Cada lienzo se carga con React.lazy, de modo que
 * three.js solo entra en el bundle al abrir esta página, sin penalizar al resto
 * de la app.
 */

import { lazy, Suspense, useMemo, useState } from 'react'
import type { Candidate, GenerationHistoryPoint, StrategySpec } from '@/services/strategyGeneratorService'
import { isWebGLAvailable } from '@/lib/webgl'
import { Universe2D, Landscape2D, Dna2D } from './Generator2DFallback'

const RobustnessUniverse3D = lazy(() => import('./RobustnessUniverse3D'))
const EvolutionLandscape3D = lazy(() => import('./EvolutionLandscape3D'))
const StrategyDNAHelix3D = lazy(() => import('./StrategyDNAHelix3D'))

type Tab = 'universe' | 'landscape' | 'dna'

const TABS: { id: Tab; label: string; hint: string }[] = [
  { id: 'universe', label: 'Universo de robustez', hint: 'Cada estrategia en el espacio PBO · eficiencia · Sharpe OOS' },
  { id: 'landscape', label: 'Paisaje evolutivo', hint: 'El fitness sube generación a generación' },
  { id: 'dna', label: 'ADN de la ganadora', hint: 'Los bloques de la mejor estrategia como doble hélice' },
]

function CanvasFallback() {
  return (
    <div className="h-[420px] rounded-xl border border-slate-700/70 bg-slate-900/60 flex flex-col items-center justify-center gap-3">
      <div className="w-8 h-8 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
      <p className="text-slate-500 text-xs">Cargando motor 3D…</p>
    </div>
  )
}

interface Props {
  candidates: Candidate[]
  history: GenerationHistoryPoint[]
  winnerSpec: StrategySpec | null
}

export default function Generator3DPanel({ candidates, history, winnerSpec }: Readonly<Props>) {
  const [tab, setTab] = useState<Tab>('universe')
  const active = TABS.find((t) => t.id === tab)!
  const webgl = useMemo(() => isWebGLAvailable(), [])

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      <div className="px-4 pt-4 pb-3 border-b border-slate-700">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-base">✨</span>
          <h3 className="text-sm font-semibold text-white">Visualización {webgl ? '3D' : '(2D)'}</h3>
        </div>
        <p className="text-xs text-slate-500">{active.hint}</p>
      </div>

      <div className="flex gap-1 px-4 pt-3 flex-wrap" role="tablist" aria-label="Visualizaciones del generador">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setTab(t.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              tab === t.id ? 'bg-blue-600 text-white' : 'bg-slate-900 text-slate-400 hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="p-4">
        {webgl ? (
          <Suspense fallback={<CanvasFallback />}>
            {tab === 'universe' && <RobustnessUniverse3D candidates={candidates} />}
            {tab === 'landscape' && <EvolutionLandscape3D history={history} />}
            {tab === 'dna' && <StrategyDNAHelix3D spec={winnerSpec} />}
          </Suspense>
        ) : (
          <>
            {tab === 'universe' && <Universe2D candidates={candidates} />}
            {tab === 'landscape' && <Landscape2D history={history} />}
            {tab === 'dna' && <Dna2D spec={winnerSpec} />}
          </>
        )}
      </div>
    </div>
  )
}
