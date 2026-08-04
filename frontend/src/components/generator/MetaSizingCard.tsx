/**
 * components/generator/MetaSizingCard.tsx — Dirección y tamaño, separados.
 *
 * Todo backtest retail opera cada señal con el mismo tamaño, lo que equivale a
 * afirmar que todas las señales de una estrategia valen lo mismo. No lo valen:
 * la misma regla de entrada acierta mucho más en unos contextos que en otros.
 *
 * El meta-modelo aprende justamente eso —cuándo acierta la señal, no hacia dónde
 * va el mercado— y su probabilidad se convierte en la fracción de capital. Tiene
 * un modo de fallo deliberadamente benigno: solo puede encoger la apuesta, nunca
 * invertirla. Equivocarse cuesta operar de menos.
 *
 * Cuando NO aporta, esta tarjeta lo dice igual de claro. Un filtro sin edge
 * medible añade ruido con apariencia de sofisticación, y ese es exactamente el
 * adorno que un motor institucional no se puede permitir.
 */

import type { MetaSizing } from '@/services/strategyGeneratorService'

const REASONS: Record<string, string> = {
  insufficient_events: 'Pocas señales para entrenar',
  unlabelable: 'Histórico insuficiente para etiquetar',
  no_edge: 'El meta-modelo no supera al primario',
  short_holdout: 'Tramo reservado demasiado corto',
  incompatible_sizing: 'El spec ya dimensiona por riesgo',
  disabled: 'Overlay desactivado',
}

function pct(v: number | undefined, digits = 0): string {
  return v == null ? '—' : `${(v * 100).toFixed(digits)}%`
}

export default function MetaSizingCard({ meta }: Readonly<{ meta?: MetaSizing }>) {
  if (!meta) return null

  const model = meta.meta_model
  const oos = meta.out_of_sample
  const applied = meta.applied

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <h3 className="text-sm font-semibold text-white">
          Tamaño por convicción
          <span className="ml-2 text-[10px] font-normal text-slate-500">
            el spec decide dónde entrar; el meta-modelo, cuánto
          </span>
        </h3>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${
            applied
              ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
              : 'bg-slate-500/15 border-slate-500/30 text-slate-400'
          }`}
        >
          {applied ? 'aporta' : (REASONS[meta.reason ?? ''] ?? 'no aplicable')}
        </span>
      </div>

      {/* Lo que aprende el meta-modelo: acierto del primario vs. filtrado */}
      {model?.primary_hit_rate != null && (
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3 text-[10px]">
          <div>
            <dt className="text-slate-500" title="Aciertos operando TODAS las señales">
              Acierto del primario
            </dt>
            <dd className="text-slate-300 font-mono text-xs">{pct(model.primary_hit_rate)}</dd>
          </div>
          <div>
            <dt className="text-slate-500" title="Aciertos cuando el meta-modelo da luz verde">
              Filtrando
            </dt>
            <dd className={`font-mono text-xs ${applied ? 'text-emerald-300' : 'text-slate-300'}`}>
              {pct(model.meta_precision)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Señales operadas</dt>
            <dd className="text-slate-300 font-mono text-xs">
              {model.signals_taken_pct != null ? `${model.signals_taken_pct.toFixed(0)}%` : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Eventos</dt>
            <dd className="text-slate-300 font-mono text-xs">
              {model.n_train ?? '—'}
              <span className="text-slate-600"> · </span>
              {model.n_test ?? '—'}
              <span className="ml-1 text-slate-600">train·test</span>
            </dd>
          </div>
        </dl>
      )}

      {/* Traducción económica, en el tramo que el modelo no vio al entrenar */}
      {oos && (
        <div className="pt-3 border-t border-slate-700/60">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-[11px] text-white">Efecto fuera de muestra</span>
            <span className="text-[10px] text-slate-500">
              {oos.candles} velas desde la {oos.from_bar}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[10px] border-separate min-w-[340px]" style={{ borderSpacing: 2 }}>
              <thead>
                <tr className="text-slate-500">
                  <th className="text-left font-normal" />
                  <th className="font-normal">Sharpe</th>
                  <th className="font-normal">Retorno</th>
                  <th className="font-normal">Caída máx.</th>
                  <th className="font-normal">Exposición</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="text-slate-400">Tamaño plano</td>
                  <td className="font-mono text-center text-slate-300">{oos.sharpe_flat.toFixed(2)}</td>
                  <td className="font-mono text-center text-slate-300">{oos.return_flat_pct.toFixed(1)}%</td>
                  <td className="font-mono text-center text-slate-300">{oos.max_drawdown_flat_pct.toFixed(1)}%</td>
                  <td className="font-mono text-center text-slate-300">{oos.exposure_flat_pct.toFixed(0)}%</td>
                </tr>
                <tr>
                  <td className="text-white">Por convicción</td>
                  <td className={`font-mono text-center ${meta.improves ? 'text-emerald-300' : 'text-amber-300'}`}>
                    {oos.sharpe_conviction.toFixed(2)}
                  </td>
                  <td className="font-mono text-center text-slate-300">{oos.return_conviction_pct.toFixed(1)}%</td>
                  <td className="font-mono text-center text-emerald-300">
                    {oos.max_drawdown_conviction_pct.toFixed(1)}%
                  </td>
                  <td className="font-mono text-center text-slate-300">
                    {oos.exposure_conviction_pct.toFixed(0)}%
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {meta.sizing && (
            <p className="text-[10px] text-slate-500 mt-2">
              Tamaño medio {meta.sizing.mean_size_pct.toFixed(0)}% del capital ·{' '}
              {meta.sizing.signals_taken} de {meta.sizing.signals_total} señales superan el suelo
              de convicción ({pct(meta.sizing.floor)}).
            </p>
          )}
        </div>
      )}

      <p className="text-[10px] text-slate-500 mt-3 leading-relaxed">{meta.note}</p>
    </div>
  )
}
