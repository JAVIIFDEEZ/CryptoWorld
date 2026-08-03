/**
 * components/generator/CapacityCard.tsx — Capacidad y significancia del campeón.
 *
 * Dos preguntas que ningún backtest retail responde, juntas porque las dos
 * matizan el mismo titular:
 *
 *   · **¿Cuánto dinero admite este edge?** Todo backtest supone ejecución al
 *     precio observado, lo que deja de ser cierto cuando la estrategia gestiona
 *     dinero de verdad. Con Sharpe 3 sobre 10 000 € puede tener Sharpe 0 sobre
 *     10 millones sin que nada cambie salvo el tamaño.
 *   · **¿Es el Sharpe distinguible de cero?** «Sharpe 1.8» no es una afirmación
 *     completa: sobre 60 velas es compatible con que no haya edge en absoluto.
 */

import type { CapacityEstimate, Significance } from '@/services/strategyGeneratorService'

function money(usd: number): string {
  if (usd >= 1e9) return `${(usd / 1e9).toFixed(0)} MM$`
  if (usd >= 1e6) return `${(usd / 1e6).toFixed(0)} M$`
  if (usd >= 1e3) return `${(usd / 1e3).toFixed(0)} k$`
  return `${usd.toFixed(0)} $`
}

export default function CapacityCard({ capacity, significance }: Readonly<{
  capacity?: CapacityEstimate
  significance?: Significance
}>) {
  if (!capacity && !significance) return null

  const ci = significance?.confidence_interval
  const psr = significance?.probabilistic_sharpe
  const conclusive = significance?.significant ?? false
  const curve = capacity?.curve ?? []

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
        <h3 className="text-sm font-semibold text-white">
          Capacidad y significancia
          <span className="ml-2 text-[10px] font-normal text-slate-500">
            cuánto dinero admite y si el Sharpe es concluyente
          </span>
        </h3>
        {significance && (
          <span
            className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${
              conclusive
                ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
                : 'bg-amber-500/15 border-amber-500/30 text-amber-300'
            }`}
          >
            {conclusive ? 'estadísticamente concluyente' : 'podría ser ruido'}
          </span>
        )}
      </div>

      {/* Significancia: magnitud e incertidumbre juntas */}
      {ci?.sharpe != null && (
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3 text-[10px]">
          <div>
            <dt className="text-slate-500">Sharpe</dt>
            <dd className="text-white font-mono text-xs">{ci.sharpe.toFixed(2)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">
              Intervalo {ci.confidence ? `${(ci.confidence * 100).toFixed(0)}%` : ''}
            </dt>
            <dd className={`font-mono text-xs ${ci.excludes_zero ? 'text-emerald-300' : 'text-red-300'}`}>
              {ci.ci_lower?.toFixed(2)} … {ci.ci_upper?.toFixed(2)}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500" title="Probabilidad de que el Sharpe verdadero supere cero">
              PSR
            </dt>
            <dd className="text-white font-mono text-xs">
              {psr?.psr != null ? `${(psr.psr * 100).toFixed(0)}%` : '—'}
            </dd>
          </div>
          <div>
            <dt className="text-slate-500">Observaciones</dt>
            <dd className="text-slate-300 font-mono text-xs">
              {ci.observations}
              {psr?.min_track_record_length != null && !conclusive && (
                <span className="text-amber-300"> / {psr.min_track_record_length}</span>
              )}
            </dd>
          </div>
        </dl>
      )}

      {significance && (
        <p className="text-[10px] text-slate-500 mb-3 leading-relaxed">{significance.note}</p>
      )}

      {/* Capacidad: degradación del Sharpe al crecer el patrimonio */}
      {curve.length > 0 && (
        <div className="pt-3 border-t border-slate-700/60">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-[11px] text-white">Capacidad estimada</span>
            <span className={`font-mono text-xs ${capacity?.capacity_usd ? 'text-sky-300' : 'text-red-300'}`}>
              {capacity?.capacity_usd ? money(capacity.capacity_usd) : 'no sobrevive'}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-[10px] border-separate min-w-[380px]" style={{ borderSpacing: 2 }}>
              <thead>
                <tr className="text-slate-500">
                  <th className="text-left font-normal">Patrimonio</th>
                  <th className="font-normal">Participación</th>
                  <th className="font-normal">Impacto</th>
                  <th className="font-normal">Sharpe retenido</th>
                </tr>
              </thead>
              <tbody>
                {curve.map((row) => (
                  <tr key={row.aum_usd} className={row.feasible ? '' : 'opacity-40'}>
                    <td className="font-mono text-slate-300">{money(row.aum_usd)}</td>
                    <td className="font-mono text-center text-slate-400">
                      {row.participation_pct.toFixed(2)}%
                    </td>
                    <td className="font-mono text-center text-slate-400">
                      {row.impact_bps_per_order.toFixed(0)} bps
                    </td>
                    <td
                      className={`font-mono text-center ${
                        row.sharpe_retained_pct >= 50 ? 'text-emerald-300' : 'text-red-300'
                      }`}
                    >
                      {row.sharpe_retained_pct.toFixed(0)}%
                      {!row.feasible && (
                        <span className="ml-1 text-slate-500" title="Supera el límite de participación">
                          ⚠
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-[10px] text-slate-500 mt-2 leading-relaxed">{capacity?.note}</p>
        </div>
      )}
    </div>
  )
}
