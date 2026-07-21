/**
 * components/news/GeoNews2D.tsx — Vista 2D del mapa de noticias (fallback del
 * globo): tarjetas por región con su categoría dominante y desglose.
 */

import { CATEGORY_COLORS, CATEGORY_NAMES } from '@/components/news/NewsGlobe3D'
import type { GlobeMarker } from '@/services/newsService'

export default function GeoNews2D({ markers, selected, onSelect }: Readonly<{
  markers: GlobeMarker[]; selected: string | null; onSelect: (region: string) => void
}>) {
  if (markers.length === 0) {
    return <p className="text-sm text-slate-500 py-8 text-center">Sin noticias con región identificable ahora mismo.</p>
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
      {markers.map((m) => {
        const color = CATEGORY_COLORS[m.top_category] ?? CATEGORY_COLORS.other
        const isSel = selected === m.region
        return (
          <button
            key={m.region}
            onClick={() => onSelect(m.region)}
            className={`text-left rounded-lg border p-3 transition-colors ${
              isSel ? 'border-blue-500 bg-blue-500/10' : 'border-slate-700 bg-slate-800/60 hover:border-slate-500'
            }`}
          >
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
              <span className="text-xs font-semibold text-white truncate">{m.name}</span>
            </div>
            <p className="text-[10px] text-slate-400 mt-1">
              {m.count} noticias · <span style={{ color }}>{CATEGORY_NAMES[m.top_category] ?? m.top_category}</span>
            </p>
          </button>
        )
      })}
    </div>
  )
}
