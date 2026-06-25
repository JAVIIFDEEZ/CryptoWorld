/**
 * components/analysis/tabs/SignalsTab.tsx — Pestaña de señales multi-indicador.
 */

import type { SignalsResult } from '@/services/analysisService'
import InfoTooltip from '@/components/ui/InfoTooltip'
import IndicatorsRadar from '@/components/analysis/IndicatorsRadar'
import {
  EmptyState, indicatorDescription, signalBg, signalColor, signalDot, signalLabel,
} from '@/components/analysis/analysisShared'

export default function SignalsTab({ data }: { data: SignalsResult | null }) {
  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        }
        title="Panel de señales multi-indicador"
        description="Analiza simultáneamente RSI, MACD, Bollinger, ADX y más. Cada indicador emite una señal (Compra / Neutral / Venta) y el sistema calcula un veredicto global por consenso ponderado."
      />
    )
  }

  const { indicators, summary } = data
  const maxScore = summary.total * 2
  const buyPct  = summary.total > 0 ? (summary.buy_count  / summary.total) * 100 : 0
  const neutPct = summary.total > 0 ? (summary.neutral_count / summary.total) * 100 : 0
  const sellPct = summary.total > 0 ? (summary.sell_count / summary.total) * 100 : 0

  return (
    <div className="space-y-4">
      {/* Veredicto con medidor visual */}
      <div className={`rounded-xl border p-4 ${signalBg(summary.verdict)}`}>
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">Veredicto Global</p>
            <p className={`text-2xl font-bold ${signalColor(summary.verdict)}`}>
              {signalLabel(summary.verdict)}
            </p>
            <p className="text-[11px] text-slate-500 mt-0.5">
              Score {summary.score > 0 ? '+' : ''}{summary.score} de {maxScore} máximo
            </p>
          </div>
          {/* Contadores en badges */}
          <div className="flex gap-2 flex-wrap">
            <span className="bg-green-600/30 text-green-300 text-[11px] font-medium px-2 py-1 rounded-lg">
              ▲ {summary.buy_count} compra
            </span>
            <span className="bg-yellow-600/30 text-yellow-300 text-[11px] font-medium px-2 py-1 rounded-lg">
              — {summary.neutral_count} neutral
            </span>
            <span className="bg-red-600/30 text-red-300 text-[11px] font-medium px-2 py-1 rounded-lg">
              ▼ {summary.sell_count} venta
            </span>
          </div>
        </div>

        {/* Barra de sentimiento */}
        <div className="mt-3 space-y-1">
          <div className="flex h-3 rounded-full overflow-hidden gap-0.5 bg-slate-700">
            {buyPct > 0 && (
              <div className="bg-green-500 h-full transition-all" style={{ width: `${buyPct}%` }} title={`Compra: ${summary.buy_count}`} />
            )}
            {neutPct > 0 && (
              <div className="bg-yellow-500 h-full transition-all" style={{ width: `${neutPct}%` }} title={`Neutral: ${summary.neutral_count}`} />
            )}
            {sellPct > 0 && (
              <div className="bg-red-500 h-full transition-all" style={{ width: `${sellPct}%` }} title={`Venta: ${summary.sell_count}`} />
            )}
          </div>
          <p className="text-[10px] text-slate-500 italic">
            Score ponderado: señales fuertes ×2, señales normales ×1. Rango: −{maxScore} (bajista extremo) a +{maxScore} (alcista extremo).
          </p>
        </div>
      </div>

      {/* Radar de consenso */}
      <IndicatorsRadar indicators={indicators} />

      {/* Tabla de indicadores */}
      <div>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-slate-700">
              <th className="text-left text-slate-500 uppercase py-2 px-2">Indicador</th>
              <th className="text-right text-slate-500 uppercase py-2 px-2">Valor</th>
              <th className="text-center text-slate-500 uppercase py-2 px-2">Señal</th>
            </tr>
          </thead>
          <tbody>
            {indicators.map((ind, i) => {
              const desc = indicatorDescription(ind.name)
              return (
                <tr key={i} className="border-b border-slate-700/40 hover:bg-slate-700/30">
                  <td className="py-2 px-2 text-slate-200">
                    <span className="inline-flex items-center gap-1.5">
                      {ind.name}
                      {desc && <InfoTooltip text={desc} />}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right font-mono text-slate-300 tabular-nums">
                    {typeof ind.value === 'number' ? ind.value.toFixed(4) : ind.value}
                  </td>
                  <td className="py-2 px-2 text-center">
                    <span className="inline-flex items-center justify-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full shrink-0 ${signalDot(ind.signal)}`} />
                      <span className={`${signalColor(ind.signal)} font-medium`}>
                        {signalLabel(ind.signal)}
                      </span>
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
