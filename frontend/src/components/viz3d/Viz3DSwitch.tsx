/**
 * components/viz3d/Viz3DSwitch.tsx — Tarjeta con conmutador 3D/2D reutilizable.
 *
 * Patrón común de todas las visualizaciones 3D de la app: cabecera con título,
 * un toggle 3D/2D y el lienzo. Si el navegador no soporta WebGL, fuerza la vista
 * 2D y deshabilita el 3D. El contenido 3D suele venir de un componente cargado
 * con React.lazy, así que se envuelve en Suspense.
 */

import { Suspense, useMemo, useState, type ReactNode } from 'react'
import { isWebGLAvailable } from '@/lib/webgl'

interface Props {
  title: string
  hint?: string
  threeD: ReactNode
  twoD: ReactNode
  /** Arrancar en 3D si hay WebGL (por defecto sí). */
  default3D?: boolean
  /** Acciones extra a la derecha de la cabecera (selectores, etc.). */
  actions?: ReactNode
}

function CanvasFallback() {
  return (
    <div className="h-[420px] rounded-xl border border-slate-700/70 bg-slate-900/60 flex flex-col items-center justify-center gap-3">
      <div className="w-8 h-8 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
      <p className="text-slate-500 text-xs">Cargando motor 3D…</p>
    </div>
  )
}

export default function Viz3DSwitch({ title, hint, threeD, twoD, default3D = true, actions }: Readonly<Props>) {
  const webgl = useMemo(() => isWebGLAvailable(), [])
  const [mode, setMode] = useState<'3d' | '2d'>(webgl && default3D ? '3d' : '2d')

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 px-4 pt-4 pb-3 border-b border-slate-700">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-base">✨</span>
            <h3 className="text-sm font-semibold text-white">{title}</h3>
          </div>
          {hint && <p className="text-xs text-slate-500 mt-0.5">{hint}</p>}
        </div>
        {actions}
        <div className="flex gap-0.5 bg-slate-900 rounded-md p-0.5" role="tablist" aria-label="Modo de visualización">
          {(['3d', '2d'] as const).map((m) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              disabled={m === '3d' && !webgl}
              onClick={() => setMode(m)}
              title={m === '3d' && !webgl ? 'Tu navegador no soporta WebGL' : undefined}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
                mode === m ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              {m.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4">
        {mode === '3d' ? <Suspense fallback={<CanvasFallback />}>{threeD}</Suspense> : twoD}
      </div>
    </div>
  )
}
