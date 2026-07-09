/**
 * components/learn/LessonReader.tsx — Lector de una lección en modal.
 *
 * Presenta el contenido de una lección (secciones + términos clave) en una capa
 * superpuesta, cerrable con Escape o clic fuera. Navegación entre lecciones con
 * anterior/siguiente para leer el temario del tirón.
 */

import { useEffect } from 'react'
import { LESSONS, type Lesson } from '@/data/learnData'

const LEVEL_CLS: Record<string, string> = {
  'Básico': 'text-emerald-300 bg-emerald-500/10 border-emerald-500/30',
  'Intermedio': 'text-amber-300 bg-amber-500/10 border-amber-500/30',
  'Avanzado': 'text-red-300 bg-red-500/10 border-red-500/30',
}

export default function LessonReader({ lesson, onNavigate, onClose }: Readonly<{
  lesson: Lesson
  onNavigate: (id: string) => void
  onClose: () => void
}>) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const idx = LESSONS.findIndex((l) => l.id === lesson.id)
  const prev = idx > 0 ? LESSONS[idx - 1] : null
  const next = idx < LESSONS.length - 1 ? LESSONS[idx + 1] : null

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[88vh] flex flex-col bg-slate-800 border border-slate-600 rounded-2xl shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Cabecera */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-start gap-3">
          <span className="text-2xl">{lesson.icon}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-lg font-bold text-white">{lesson.title}</h2>
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${LEVEL_CLS[lesson.level]}`}>{lesson.level}</span>
              <span className="text-[10px] text-slate-500">· {lesson.minutes} min de lectura</span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">{lesson.summary}</p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors shrink-0" aria-label="Cerrar">
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Cuerpo con scroll */}
        <div className="px-6 py-5 overflow-y-auto space-y-5">
          {lesson.sections.map((s) => (
            <div key={s.heading}>
              <h3 className="text-sm font-semibold text-white mb-1.5">{s.heading}</h3>
              <p className="text-[13px] text-slate-300 leading-relaxed">{s.body}</p>
            </div>
          ))}

          {lesson.keyTerms && lesson.keyTerms.length > 0 && (
            <div className="bg-slate-900/50 rounded-xl border border-slate-700/60 p-4">
              <p className="text-[10px] uppercase tracking-wider text-blue-300/80 mb-2 font-semibold">Términos clave</p>
              <dl className="space-y-2">
                {lesson.keyTerms.map((t) => (
                  <div key={t.term} className="text-xs">
                    <dt className="text-slate-200 font-medium inline">{t.term}: </dt>
                    <dd className="text-slate-400 inline">{t.def}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>

        {/* Navegación entre lecciones */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-slate-700 bg-slate-900/40 gap-2">
          <button
            onClick={() => prev && onNavigate(prev.id)}
            disabled={!prev}
            className="text-xs px-3 py-1.5 rounded-lg text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed truncate max-w-[45%]"
          >
            {prev ? `← ${prev.title}` : ''}
          </button>
          <span className="text-[10px] text-slate-600 shrink-0">{idx + 1} / {LESSONS.length}</span>
          <button
            onClick={() => next && onNavigate(next.id)}
            disabled={!next}
            className="text-xs px-3 py-1.5 rounded-lg text-slate-300 hover:bg-slate-700 transition-colors disabled:opacity-30 disabled:cursor-not-allowed truncate max-w-[45%] text-right"
          >
            {next ? `${next.title} →` : ''}
          </button>
        </div>
      </div>
    </div>
  )
}
