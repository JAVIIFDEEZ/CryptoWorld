/**
 * components/analysis/tabs/BacktestTab.tsx — Simulación de estrategia vs Buy&Hold,
 * con realismo de ejecución (costes, rotación, motivos de salida).
 */

import type { BacktestResult, StrategyInfo } from '@/services/analysisService'
import { EmptyState, MetricCard } from '@/components/analysis/analysisShared'

const EXIT_REASON_LABEL: Record<string, string> = {
  signal: 'Señal', stop_loss: 'Stop-loss', take_profit: 'Take-profit',
  trailing_stop: 'Trailing', end_of_data: 'Fin de datos',
}

export default function BacktestTab({ data, strategies, selected }: { data: BacktestResult | null; strategies: StrategyInfo[]; selected: string }) {
  if (!data) {
    const desc = strategies.find((s) => s.key === selected)?.description
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
        title="Simulación de estrategia sobre histórico"
        description={desc ?? 'Selecciona una estrategia de trading y simula su rendimiento sobre datos históricos reales. Compara el resultado con la estrategia pasiva Buy & Hold.'}
      />
    )
  }

  const isPositive = data.total_return_pct >= 0
  const beatsBuyHold = data.total_return_pct > data.buy_hold_return_pct
  const alpha = data.total_return_pct - data.buy_hold_return_pct
  const maxAbs = Math.max(Math.abs(data.total_return_pct), Math.abs(data.buy_hold_return_pct), 1)

  return (
    <div className="space-y-4">
      {/* Descripción de estrategia */}
      <div className="bg-slate-900/50 rounded-lg p-3">
        <p className="text-xs text-slate-400 uppercase mb-1">{data.strategy}</p>
        <p className="text-xs text-slate-300">{data.description}</p>
      </div>

      {/* Periodo analizado */}
      {(data.start_date || data.candles_count) && (
        <div className="bg-blue-950/40 border border-blue-700/30 rounded-lg px-3 py-2 flex flex-wrap gap-x-5 gap-y-1">
          {data.start_date && data.end_date && (
            <span className="text-[11px]">
              <span className="text-slate-500 uppercase text-[10px] mr-1">Periodo:</span>
              <span className="text-slate-300 font-mono">{data.start_date}</span>
              <span className="mx-1 text-slate-600">→</span>
              <span className="text-slate-300 font-mono">{data.end_date}</span>
            </span>
          )}
          {data.candles_count && (
            <span className="text-[11px]">
              <span className="text-slate-500 uppercase text-[10px] mr-1">Velas:</span>
              <span className="text-slate-300">{data.candles_count.toLocaleString()}</span>
            </span>
          )}
          {data.interval && (
            <span className="text-[11px]">
              <span className="text-slate-500 uppercase text-[10px] mr-1">Intervalo:</span>
              <span className="text-slate-300">{data.interval}</span>
            </span>
          )}
        </div>
      )}

      {/* Comparativa visual retorno estrategia vs Buy & Hold */}
      <div className="space-y-2 bg-slate-900/30 rounded-lg p-3">
        <p className="text-[10px] text-slate-500 uppercase mb-3">Retorno — Estrategia vs Buy & Hold</p>
        {[
          { label: 'Estrategia', value: data.total_return_pct, color: isPositive ? 'bg-blue-600' : 'bg-red-700' },
          { label: 'Buy & Hold', value: data.buy_hold_return_pct, color: data.buy_hold_return_pct >= 0 ? 'bg-slate-500' : 'bg-red-900' },
        ].map(({ label, value, color }) => (
          <div key={label} className="flex items-center gap-2">
            <span className="text-[10px] text-slate-400 w-20 truncate">{label}</span>
            <div className="flex-1 h-6 bg-slate-700 rounded overflow-hidden">
              <div
                className={`h-full rounded flex items-center justify-end pr-2 transition-all ${color}`}
                style={{ width: `${Math.max((Math.abs(value) / maxAbs) * 100, 4)}%` }}
              >
                <span className="text-[10px] font-bold text-white whitespace-nowrap">
                  {value >= 0 ? '+' : ''}{value.toFixed(2)}%
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Alpha badge */}
      <div className={`flex items-center gap-2 rounded-lg px-3 py-2 ${beatsBuyHold ? 'bg-green-900/30 border border-green-700/30' : 'bg-red-900/20 border border-red-700/20'}`}>
        <svg className={`w-4 h-4 ${beatsBuyHold ? 'text-green-400' : 'text-red-400'}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d={beatsBuyHold ? 'M5 10l7-7m0 0l7 7m-7-7v18' : 'M19 14l-7 7m0 0l-7-7m7 7V3'} />
        </svg>
        <p className="text-xs text-slate-300">
          <span className={`font-bold ${beatsBuyHold ? 'text-green-400' : 'text-red-400'}`}>
            {beatsBuyHold ? 'Supera' : 'No supera'} al Buy & Hold
          </span>
          {' '}— Alpha:{' '}
          <span className={`font-mono font-medium ${alpha >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {alpha >= 0 ? '+' : ''}{alpha.toFixed(2)}%
          </span>
          <span className="text-slate-500 ml-1 text-[10px]">(retorno estrategia − retorno pasivo)</span>
        </p>
      </div>

      {/* Métricas */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Retorno total" value={`${isPositive ? '+' : ''}${data.total_return_pct.toFixed(2)}%`} color={isPositive ? 'text-green-400' : 'text-red-400'} />
        <MetricCard label="Buy & Hold" value={`${data.buy_hold_return_pct >= 0 ? '+' : ''}${data.buy_hold_return_pct.toFixed(2)}%`} color={data.buy_hold_return_pct >= 0 ? 'text-green-400' : 'text-red-400'} />
        <MetricCard label="Win Rate" value={`${data.win_rate_pct.toFixed(1)}%`} color="text-white" />
        <MetricCard label="Max Drawdown" value={`-${data.max_drawdown_pct.toFixed(2)}%`} color="text-red-400" />
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Total trades" value={String(data.total_trades)} color="text-white" />
        <MetricCard label="Cap. inicial" value={`$${data.initial_capital.toLocaleString()}`} color="text-slate-300" />
        <MetricCard label="Cap. final" value={`$${data.final_capital.toLocaleString()}`} color={isPositive ? 'text-green-400' : 'text-red-400'} />
        <MetricCard label="Avg Win / Avg Loss" value={`${data.avg_win_pct.toFixed(1)}% / ${data.avg_loss_pct.toFixed(1)}%`} color="text-slate-300" />
      </div>

      {/* Realismo de ejecución: coste, rotación y motivos de salida */}
      {(data.total_commission_pct != null || data.turnover != null || data.exit_reasons) && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard label="Coste en comisiones" value={`-${(data.total_commission_pct ?? 0).toFixed(2)}%`} color="text-amber-400" />
          <MetricCard label="Rotación (×capital)" value={`${(data.turnover ?? 0).toFixed(1)}×`} color="text-slate-300" />
          {data.exit_reasons && (
            <div className="col-span-2 bg-slate-900/40 rounded-lg p-3">
              <p className="text-[10px] text-slate-500 uppercase mb-1.5">Motivos de salida</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(data.exit_reasons).map(([reason, count]) => (
                  <span key={reason} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
                    {EXIT_REASON_LABEL[reason] ?? reason}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Últimas trades */}
      {data.trades.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 uppercase mb-2">Últimas operaciones</p>
          <div className="overflow-x-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-1.5 px-2 text-slate-500">#</th>
                  <th className="text-right py-1.5 px-2 text-slate-500">Entrada</th>
                  <th className="text-right py-1.5 px-2 text-slate-500">Salida</th>
                  <th className="text-right py-1.5 px-2 text-slate-500">P&L</th>
                  <th className="text-center py-1.5 px-2 text-slate-500">Resultado</th>
                </tr>
              </thead>
              <tbody>
                {data.trades.map((t, i) => (
                  <tr key={i} className="border-b border-slate-700/30">
                    <td className="py-1.5 px-2 text-slate-400">{i + 1}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-slate-300">${t.entry_price}</td>
                    <td className="py-1.5 px-2 text-right font-mono text-slate-300">${t.exit_price}</td>
                    <td className={`py-1.5 px-2 text-right font-mono font-medium ${t.pnl_pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct}%
                    </td>
                    <td className="py-1.5 px-2 text-center">
                      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] ${t.result === 'WIN' ? 'bg-green-600/30 text-green-300' : 'bg-red-600/30 text-red-300'}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${t.result === 'WIN' ? 'bg-green-400' : 'bg-red-400'}`} />
                        {t.result}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
