/**
 * components/generator/VariantsCard.tsx — Las que no encabezan el libro.
 *
 * El ranking es un libro **decorrelacionado**: entre estrategias que explotan la
 * misma fuente de retorno solo una lo encabeza, porque cinco formas del mismo
 * edge no diversifican nada.
 *
 * Eso no las invalida. Cada variante superó **exactamente los mismos controles**
 * que la cabeza de libro —gating, holdout, CPCV, cascada de retests— y se
 * calculó entera. Lo que la aparta es correlacionar, no fallar. Y entre dos
 * estrategias del mismo edge, cuál prefiere uno depende de su caída máxima, su
 * número de operaciones o su rotación: es una decisión del usuario, no un
 * descarte que el motor deba hacer en silencio.
 *
 * Antes desaparecían dejando una línea de texto con su hash.
 */

import type { StrategyVariant } from '@/services/strategyGeneratorService'

export default function VariantsCard({ variants, championDesc }: Readonly<{
  variants?: StrategyVariant[]
  championDesc?: string
}>) {
  if (!variants || variants.length === 0) return null

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-1">
        <h3 className="text-sm font-semibold text-white">
          Variantes del mismo edge
          <span className="ml-2 text-[10px] font-normal text-slate-500">
            validadas igual, apartadas del libro por correlacionar
          </span>
        </h3>
        <span className="text-[10px] px-2 py-0.5 rounded-full border font-medium bg-sky-500/15 border-sky-500/30 text-sky-300">
          {variants.length} {variants.length === 1 ? 'variante' : 'variantes'}
        </span>
      </div>

      {championDesc && (
        <p className="text-[10px] text-slate-500 mb-3 truncate" title={championDesc}>
          Correlacionan con: {championDesc}
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-[10px] border-separate min-w-[520px]" style={{ borderSpacing: 2 }}>
          <thead>
            <tr className="text-slate-500">
              <th className="text-left font-normal">Estrategia</th>
              <th className="font-normal" title="Correlación con la cabeza de libro">ρ</th>
              <th className="font-normal">Sharpe</th>
              <th className="font-normal">Caída máx.</th>
              <th className="font-normal">Trades</th>
              <th className="font-normal">Holdout</th>
            </tr>
          </thead>
          <tbody>
            {variants.map((v) => {
              const m = v.gating.metrics
              const h = v.holdout_validation
              return (
                <tr key={v.spec_hash}>
                  <td className="text-slate-300 max-w-[240px] truncate" title={v.description}>
                    {v.description}
                  </td>
                  <td className="font-mono text-center text-amber-300">
                    {v.correlation_with_parent?.toFixed(2)}
                  </td>
                  <td className="font-mono text-center text-slate-300">{m.sharpe?.toFixed(2)}</td>
                  <td className="font-mono text-center text-slate-400">
                    −{m.max_drawdown_pct?.toFixed(1)}%
                  </td>
                  <td className="font-mono text-center text-slate-400">{m.n_trades}</td>
                  <td className={`font-mono text-center ${h.return_pct >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                    {h.return_pct >= 0 ? '+' : ''}{h.return_pct?.toFixed(1)}%
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <p className="text-[10px] text-slate-500 mt-2 leading-relaxed">
        Correlacionar con la cabeza de libro no es un fallo: significa que explotan
        el mismo edge. Si alguna te encaja mejor por caída máxima o por número de
        operaciones, ya está validada — no hay que volver a calcular nada.
      </p>
    </div>
  )
}
