/**
 * components/learn/ChainDetailPanel.tsx — Ficha educativa de una blockchain.
 *
 * Muestra los datos de la cadena seleccionada en el grafo (capa, consenso, año,
 * resumen y hechos clave) y sus conexiones: en qué liquida y con qué cadenas
 * está puenteada, con el nombre del puente y una nota didáctica.
 */

import { chainById, connectionsOf, chainName, type ChainCategory } from '@/data/learnData'

const CATEGORY: Record<ChainCategory, { label: string; cls: string }> = {
  L1: { label: 'Layer 1', cls: 'text-sky-300 bg-sky-500/10 border-sky-500/30' },
  L2: { label: 'Layer 2', cls: 'text-violet-300 bg-violet-500/10 border-violet-500/30' },
  sidechain: { label: 'Sidechain', cls: 'text-amber-300 bg-amber-500/10 border-amber-500/30' },
}

export default function ChainDetailPanel({ selected }: Readonly<{ selected: string | null }>) {
  const chain = selected ? chainById(selected) : undefined

  if (!chain) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5 h-full flex flex-col items-center justify-center text-center">
        <span className="text-3xl mb-2">🪐</span>
        <p className="text-sm text-slate-300 font-medium">Explora el ecosistema</p>
        <p className="text-xs text-slate-500 mt-1">
          Pulsa una blockchain del grafo para ver su ficha: capa, consenso, datos clave y sus puentes con otras cadenas.
        </p>
      </div>
    )
  }

  const cat = CATEGORY[chain.category]
  const conns = connectionsOf(chain.id)

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden h-full">
      <div className="p-5" style={{ borderTop: `3px solid ${chain.color}` }}>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full flex items-center justify-center font-mono font-bold text-sm text-white shrink-0"
               style={{ backgroundColor: chain.color }}>
            {chain.symbol.slice(0, 3)}
          </div>
          <div className="min-w-0">
            <h3 className="text-lg font-bold text-white leading-tight">{chain.name}</h3>
            <p className="text-xs text-slate-500 font-mono">{chain.symbol} · desde {chain.launched}</p>
          </div>
          <span className={`ml-auto text-[10px] font-semibold px-2 py-0.5 rounded border ${cat.cls}`}>{cat.label}</span>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <span className="text-[10px] px-2 py-1 rounded-lg bg-slate-900/60 border border-slate-700 text-slate-300">
            ⚙ {chain.consensus}
          </span>
          {chain.settlesOn && (
            <span className="text-[10px] px-2 py-1 rounded-lg bg-teal-500/10 border border-teal-500/30 text-teal-300">
              liquida en {chainName(chain.settlesOn)}
            </span>
          )}
        </div>

        <p className="text-[13px] text-slate-300 leading-relaxed mt-3">{chain.summary}</p>

        <div className="mt-3">
          <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">Datos clave</p>
          <ul className="space-y-1.5">
            {chain.facts.map((f) => (
              <li key={f} className="text-xs text-slate-400 flex gap-2">
                <span className="text-slate-600 mt-0.5">▸</span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </div>

        {conns.length > 0 && (
          <div className="mt-4">
            <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1.5">
              Conexiones · {conns.length}
            </p>
            <div className="space-y-1.5">
              {conns.map((e, i) => {
                const other = e.from === chain.id ? e.to : e.from
                const settle = e.kind === 'settlement'
                return (
                  <div key={i} className="text-xs bg-slate-900/40 rounded-lg border border-slate-700/60 px-2.5 py-1.5">
                    <div className="flex items-center gap-2">
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${settle ? 'bg-teal-400' : 'bg-amber-400'}`} />
                      <span className="text-slate-200 font-medium">{chainName(other)}</span>
                      <span className="text-slate-500 text-[10px] ml-auto">{settle ? 'liquidación' : e.label}</span>
                    </div>
                    {e.note && <p className="text-[10px] text-slate-500 mt-1 leading-snug">{e.note}</p>}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
