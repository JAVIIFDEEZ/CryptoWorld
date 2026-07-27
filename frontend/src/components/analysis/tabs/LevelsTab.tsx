/**
 * components/analysis/tabs/LevelsTab.tsx — Soportes/resistencias y divergencias.
 *
 * Escalera de niveles alrededor del precio actual (fuerza = nº de toques) y
 * divergencias RSI/precio recientes. La lectura combinada es lo accionable:
 * una divergencia bajista pegada a una resistencia fuerte pesa mucho más que
 * cualquiera de las dos señales por separado.
 */

import type { Divergence, PriceLevel, PriceStructure } from '@/services/analysisService'
import { EmptyState } from '@/components/analysis/analysisShared'

function fmtPrice(p: number): string {
  return p >= 1000 ? p.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : p.toLocaleString(undefined, { maximumFractionDigits: 6 })
}

function LevelRow({ lv, maxTouches }: { lv: PriceLevel; maxTouches: number }) {
  const isRes = lv.kind === 'resistance'
  const tone = isRes ? 'text-red-300' : 'text-green-300'
  const bar = isRes ? 'bg-red-500/70' : 'bg-green-500/70'
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className={`w-20 shrink-0 text-[10px] uppercase ${tone}`}>
        {isRes ? 'Resistencia' : 'Soporte'}
      </span>
      <span className="w-28 font-mono text-slate-200">${fmtPrice(lv.price)}</span>
      <span className={`w-16 font-mono text-[11px] ${lv.distance_pct >= 0 ? 'text-red-400' : 'text-green-400'}`}>
        {lv.distance_pct >= 0 ? '+' : ''}{lv.distance_pct.toFixed(2)}%
      </span>
      <div className="flex-1 bg-slate-700/60 rounded-full h-2">
        <div className={`h-2 rounded-full ${bar}`} style={{ width: `${(lv.touches / maxTouches) * 100}%` }} />
      </div>
      <span className="w-16 text-right text-[10px] text-slate-400">{lv.touches} toques</span>
    </div>
  )
}

function DivergenceCard({ d }: { d: Divergence }) {
  const bearish = d.type === 'bearish'
  return (
    <div className={`rounded-lg border p-3 ${bearish ? 'bg-red-500/10 border-red-500/30' : 'bg-green-500/10 border-green-500/30'}`}>
      <p className={`text-xs font-bold uppercase ${bearish ? 'text-red-300' : 'text-green-300'}`}>
        {bearish ? '▼ Divergencia bajista' : '▲ Divergencia alcista'}
      </p>
      <p className="text-[11px] text-slate-300 mt-1">{d.detail}</p>
      <p className="text-[10px] text-slate-500 font-mono mt-1.5">
        precio {fmtPrice(d.price_from)} → {fmtPrice(d.price_to)} · RSI {d.rsi_from.toFixed(0)} → {d.rsi_to.toFixed(0)}
      </p>
    </div>
  )
}

export default function LevelsTab({ data }: { data: PriceStructure | null }) {
  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        }
        title="Soportes, resistencias y divergencias"
        description="Detecta los niveles donde el precio reaccionó repetidamente (agrupación de pivotes: la fuerza es el número de toques) y las divergencias RSI/precio recientes, que anticipan pérdida de impulso."
      />
    )
  }

  // Escalera: resistencias de mayor a menor, precio actual, soportes
  const resistances = data.levels.filter((l) => l.kind === 'resistance').sort((a, b) => b.price - a.price)
  const supports = data.levels.filter((l) => l.kind === 'support').sort((a, b) => b.price - a.price)
  const maxTouches = Math.max(...data.levels.map((l) => l.touches), 1)

  return (
    <div className="space-y-4">
      {/* Rango inmediato */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-slate-900/40 rounded-lg border border-red-500/20 p-3">
          <p className="text-[10px] text-slate-500 uppercase">Resistencia más cercana</p>
          <p className="text-sm font-bold font-mono text-red-300">
            {data.nearest_resistance ? `$${fmtPrice(data.nearest_resistance.price)}` : '—'}
          </p>
          {data.nearest_resistance && (
            <p className="text-[10px] text-slate-500">a +{data.nearest_resistance.distance_pct.toFixed(2)}%</p>
          )}
        </div>
        <div className="bg-slate-900/40 rounded-lg border border-slate-600 p-3">
          <p className="text-[10px] text-slate-500 uppercase">Precio actual</p>
          <p className="text-sm font-bold font-mono text-white">${fmtPrice(data.last_price)}</p>
          <p className="text-[10px] text-slate-500">{data.interval} · {data.candles_analyzed} velas</p>
        </div>
        <div className="bg-slate-900/40 rounded-lg border border-green-500/20 p-3">
          <p className="text-[10px] text-slate-500 uppercase">Soporte más cercano</p>
          <p className="text-sm font-bold font-mono text-green-300">
            {data.nearest_support ? `$${fmtPrice(data.nearest_support.price)}` : '—'}
          </p>
          {data.nearest_support && (
            <p className="text-[10px] text-slate-500">a {data.nearest_support.distance_pct.toFixed(2)}%</p>
          )}
        </div>
      </div>

      {/* Escalera de niveles */}
      {data.levels.length > 0 ? (
        <div className="bg-slate-900/30 rounded-lg p-3 space-y-1.5">
          <p className="text-[10px] text-slate-500 uppercase mb-2">Niveles por fuerza (nº de toques)</p>
          {resistances.map((lv) => <LevelRow key={`r-${lv.price}`} lv={lv} maxTouches={maxTouches} />)}
          <div className="flex items-center gap-2 py-1">
            <div className="flex-1 border-t border-dashed border-slate-500" />
            <span className="text-[10px] text-slate-400 font-mono">${fmtPrice(data.last_price)} ahora</span>
            <div className="flex-1 border-t border-dashed border-slate-500" />
          </div>
          {supports.map((lv) => <LevelRow key={`s-${lv.price}`} lv={lv} maxTouches={maxTouches} />)}
        </div>
      ) : (
        <p className="text-sm text-slate-500">No se detectaron niveles claros en esta ventana.</p>
      )}

      {/* Divergencias */}
      {data.divergences.length > 0 ? (
        <div className="grid sm:grid-cols-2 gap-3">
          {data.divergences.map((d) => <DivergenceCard key={d.type} d={d} />)}
        </div>
      ) : (
        <p className="text-[11px] text-slate-500">
          Sin divergencias RSI/precio en los últimos pivotes: el impulso confirma el movimiento.
        </p>
      )}

      <p className="text-[10px] text-slate-600">{data.note}</p>
    </div>
  )
}
