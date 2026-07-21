/**
 * pages/LearnPage.tsx — Academia CryptoWorld (módulo de aprendizaje).
 *
 * Reúne el material educativo del sistema: un grafo interactivo (3D/2D) de las
 * blockchains y sus puentes, una ficha por cadena, un temario de lecciones con
 * lector integrado y un glosario. Pensado para que alguien entienda el terreno
 * antes de operar en él.
 */

import { lazy, Suspense, useMemo, useState } from 'react'
import Viz3DSwitch from '@/components/viz3d/Viz3DSwitch'
import BlockchainGraph2D from '@/components/learn/BlockchainGraph2D'
import ChainDetailPanel from '@/components/learn/ChainDetailPanel'
import LessonReader from '@/components/learn/LessonReader'
import { LESSONS, GLOSSARY, CHAINS, BRIDGES, type Lesson } from '@/data/learnData'

const BlockchainGraph3D = lazy(() => import('@/components/learn/BlockchainGraph3D'))

const LEVEL_DOT: Record<string, string> = {
  'Básico': 'bg-emerald-400', 'Intermedio': 'bg-amber-400', 'Avanzado': 'bg-red-400',
}

function GraphLegend() {
  return (
    <div className="flex items-center gap-4 flex-wrap text-[10px] text-slate-400">
      <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 bg-teal-400 inline-block" /> liquidación (L2→base)</span>
      <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 bg-amber-400 inline-block" style={{ borderTop: '1px dashed' }} /> puente cross-chain</span>
      <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full bg-sky-400 inline-block" /> tamaño = ecosistema</span>
    </div>
  )
}

export default function LearnPage() {
  const [selected, setSelected] = useState<string | null>(null)
  const [openLesson, setOpenLesson] = useState<string | null>(null)

  const lesson: Lesson | null = useMemo(
    () => (openLesson ? LESSONS.find((l) => l.id === openLesson) ?? null : null),
    [openLesson],
  )

  const select = (id: string) => setSelected(id || null)

  return (
    <section className="space-y-6">
      <header>
        <div className="flex items-center gap-2">
          <span className="text-2xl">🎓</span>
          <h1 className="text-2xl font-bold text-white">Academia CryptoWorld</h1>
        </div>
        <p className="text-slate-400 text-sm mt-1">
          Aprende cómo funciona el ecosistema: explora el grafo de blockchains y sus puentes, y estudia el temario.
        </p>
      </header>

      {/* Grafo + ficha */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-2">
          <Viz3DSwitch
            title="Mapa de blockchains y puentes"
            hint="Las L2 se apilan sobre la cadena en la que liquidan; las líneas son conexiones entre cadenas."
            threeD={
              <Suspense fallback={<div className="h-[460px] rounded-xl bg-slate-900/60 animate-pulse" />}>
                <BlockchainGraph3D selected={selected} onSelect={select} />
              </Suspense>
            }
            twoD={<BlockchainGraph2D selected={selected} onSelect={select} />}
          />
          <GraphLegend />
        </div>
        <ChainDetailPanel selected={selected} />
      </div>

      {/* Temario */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <h2 className="text-lg font-semibold text-white">Temario</h2>
          <span className="text-xs text-slate-500">{LESSONS.length} lecciones · de cero a DeFi</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {LESSONS.map((l) => (
            <button
              key={l.id}
              onClick={() => setOpenLesson(l.id)}
              className="text-left bg-slate-800 hover:bg-slate-700/60 border border-slate-700 hover:border-slate-600 rounded-xl p-4 transition-colors group"
            >
              <div className="flex items-center justify-between">
                <span className="text-2xl">{l.icon}</span>
                <span className="flex items-center gap-1 text-[10px] text-slate-500">
                  <span className={`w-1.5 h-1.5 rounded-full ${LEVEL_DOT[l.level]}`} />
                  {l.level}
                </span>
              </div>
              <p className="text-sm font-semibold text-white mt-2 group-hover:text-blue-300 transition-colors">{l.title}</p>
              <p className="text-[11px] text-slate-400 mt-1 leading-snug line-clamp-2">{l.summary}</p>
              <p className="text-[10px] text-slate-600 mt-2">{l.minutes} min →</p>
            </button>
          ))}
        </div>
      </div>

      {/* Glosario */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-3">Glosario</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {GLOSSARY.map((g) => (
            <div key={g.term} className="bg-slate-800/60 border border-slate-700/60 rounded-lg p-3">
              <p className="text-xs font-semibold text-blue-300">{g.term}</p>
              <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">{g.def}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Pie de datos del grafo */}
      <p className="text-[10px] text-slate-600">
        Grafo con {CHAINS.length} blockchains y {BRIDGES.length} puentes cross-chain (más las liquidaciones L2→base).
        Contenido educativo; no constituye consejo financiero.
      </p>

      {lesson && (
        <LessonReader lesson={lesson} onNavigate={setOpenLesson} onClose={() => setOpenLesson(null)} />
      )}
    </section>
  )
}
