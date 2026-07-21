/**
 * components/portfolio/RiskPanel.tsx — Riesgo agregado del libro completo.
 *
 * Muestra la exposición firmada por activo sumando los tres libros (posiciones
 * manuales, paper trading y ejecución real), el VaR/CVaR 1 día por simulación
 * histórica y el stress testing con los peores movimientos realmente
 * observados. Solo aparece si hay exposición.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { portfolioService, type PortfolioRisk } from '@/services/portfolioService'
import { tradingService, type LiveRiskPolicy } from '@/services/tradingService'

function usd(n: number | undefined | null, sign = false): string {
  if (n == null) return '—'
  const s = sign && n > 0 ? '+' : ''
  return `${s}$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

const BOOK_LABEL: Record<string, string> = { manual: 'Manual', paper: 'Paper', live: 'Real' }

export default function RiskPanel() {
  const [risk, setRisk] = useState<PortfolioRisk | null>(null)
  const [policy, setPolicy] = useState<LiveRiskPolicy | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    portfolioService.getRisk()
      .then((r) => { if (!cancelled) setRisk(r) })
      .catch(() => { /* sin riesgo */ })
      .finally(() => { if (!cancelled) setLoading(false) })
    tradingService.getRiskPolicy()
      .then((p) => { if (!cancelled) setPolicy(p) })
      .catch(() => { /* sin política */ })
    return () => { cancelled = true }
  }, [])

  if (loading || !risk || risk.status === 'EMPTY') return null

  const v = risk.var
  const maxExp = Math.max(...risk.exposures.map((e) => Math.abs(e.net_usd)), 1)

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden mb-6">
      <div className="px-5 pt-4 pb-1 flex items-center gap-2 flex-wrap">
        <span>🛡</span>
        <h2 className="text-lg font-semibold text-white">Riesgo del libro completo</h2>
        <span className="text-[10px] text-slate-500">
          manual + paper + real · VaR histórico sobre datos propios
        </span>
      </div>

      <div className="p-5 pt-3 space-y-4">
        {/* KPIs de exposición */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-slate-900/40 rounded-lg p-3">
            <p className="text-[10px] text-slate-500 uppercase">Exposición bruta</p>
            <p className="text-lg font-bold font-mono text-white">{usd(risk.gross_usd)}</p>
          </div>
          <div className="bg-slate-900/40 rounded-lg p-3">
            <p className="text-[10px] text-slate-500 uppercase">Exposición neta</p>
            <p className={`text-lg font-bold font-mono ${risk.net_usd >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {usd(risk.net_usd, true)}
            </p>
          </div>
          <div className="bg-slate-900/40 rounded-lg p-3">
            <p className="text-[10px] text-slate-500 uppercase">Largo / Corto</p>
            <p className="text-sm font-bold font-mono">
              <span className="text-emerald-400">{usd(risk.long_usd)}</span>
              <span className="text-slate-600"> / </span>
              <span className="text-red-400">{usd(risk.short_usd)}</span>
            </p>
          </div>
          <div className="bg-slate-900/40 rounded-lg p-3">
            <p className="text-[10px] text-slate-500 uppercase">Concentración top</p>
            <p className={`text-lg font-bold font-mono ${(risk.top_concentration_pct ?? 0) >= 60 ? 'text-amber-300' : 'text-white'}`}>
              {(risk.top_concentration_pct ?? 0).toFixed(0)}%
            </p>
          </div>
        </div>

        {/* Controles activos del OMS cruzados con el uso actual del libro */}
        <OmsControls policy={policy} topConcentration={risk.top_concentration_pct ?? 0} />

        {/* VaR / CVaR */}
        {v?.status === 'OK' ? (
          <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-3">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
              <h3 className="text-xs font-semibold text-slate-300">Pérdida potencial en 1 día</h3>
              <span className="text-[10px] text-slate-500">simulación histórica · {v.days} días</span>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <RiskStat label="VaR 95%" value={usd(v.var95_usd)} hint="1 día de cada 20" />
              <RiskStat label="CVaR 95%" value={usd(v.cvar95_usd)} hint="media de la cola" />
              <RiskStat label="VaR 99%" value={usd(v.var99_usd)} hint="1 día de cada 100" />
              <RiskStat label="Peor día visto" value={usd(v.worst_day_usd)} hint="máx. histórico" strong />
            </div>
            <p className="text-[10px] text-slate-600 mt-2">
              El VaR 95% es la pérdida que se supera 1 día de cada 20 según tu histórico real; el
              CVaR es la pérdida MEDIA los días que se cruza ese umbral (la métrica de las colas).
            </p>
          </div>
        ) : (
          <p className="text-[11px] text-slate-500">
            VaR no disponible: se necesitan ≥ 60 días de histórico solapado
            {v?.days ? ` (hay ${v.days})` : ''}. Usa el backfill del histórico para tus activos.
          </p>
        )}

        {(risk.var_symbols_excluded?.length ?? 0) > 0 && (
          <p className="text-[10px] text-amber-300/80">
            Sin histórico suficiente para el VaR: {risk.var_symbols_excluded!.join(', ')} (cuentan en la exposición, no en el VaR).
          </p>
        )}

        {/* Exposición por activo */}
        <div>
          <p className="text-[10px] uppercase text-slate-500 mb-2">Exposición firmada por activo</p>
          <div className="space-y-1.5">
            {risk.exposures.map((e) => {
              const w = (Math.abs(e.net_usd) / maxExp) * 100
              const long = e.net_usd >= 0
              return (
                <div key={e.symbol} className="flex items-center gap-2 text-[11px]">
                  <span className="w-12 shrink-0 font-mono text-slate-300">{e.symbol}</span>
                  <div className="flex-1 h-4 bg-slate-900/40 rounded overflow-hidden flex items-center">
                    <div className={`h-full ${long ? 'bg-emerald-500/60' : 'bg-red-500/60'}`} style={{ width: `${w}%` }} />
                  </div>
                  <span className={`w-20 text-right font-mono ${long ? 'text-emerald-400' : 'text-red-400'}`}>
                    {usd(e.net_usd, true)}
                  </span>
                  <span className="w-28 shrink-0 text-right text-[9px] text-slate-600">
                    {Object.entries(e.by_book).filter(([, val]) => Math.abs(val) > 0.01)
                      .map(([b]) => BOOK_LABEL[b]).join('+')}
                    {!e.in_var && <span className="text-amber-400" title="Excluido del VaR (sin histórico)"> ⚠</span>}
                  </span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Stress testing */}
        {(risk.stress?.length ?? 0) > 0 && (
          <div>
            <p className="text-[10px] uppercase text-slate-500 mb-2">
              Stress: peor movimiento observado aplicado a tu cartera actual
            </p>
            <div className="grid grid-cols-3 gap-3">
              {risk.stress!.map((sc) => (
                <div key={sc.window_days} className="bg-slate-900/40 rounded-lg p-3 text-center">
                  <p className="text-[10px] text-slate-500 uppercase">{sc.window_days} día{sc.window_days > 1 ? 's' : ''}</p>
                  <p className={`text-base font-bold font-mono ${sc.impact_usd < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                    {usd(sc.impact_usd, true)}
                  </p>
                  <p className="text-[9px] text-slate-600">{sc.symbols_covered}/{sc.symbols_total} activos</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {risk.note && <p className="text-[10px] text-slate-600">{risk.note}</p>}
      </div>
    </div>
  )
}

function OmsControls({ policy, topConcentration }: Readonly<{
  policy: LiveRiskPolicy | null; topConcentration: number
}>) {
  const hasLoss = policy?.daily_loss_limit_usd != null
  const hasConc = policy?.max_concentration_pct != null
  if (!policy || (!hasLoss && !hasConc)) {
    return (
      <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 px-3 py-2 text-[11px] text-slate-400">
        <span className="text-slate-300 font-medium">Sin barreras de riesgo activas.</span>{' '}
        Fija un límite de pérdida diaria y de concentración en{' '}
        <Link to="/trading" className="text-blue-400 hover:text-blue-300">Trading</Link> para proteger la ejecución real.
      </div>
    )
  }
  const today = policy.realized_today_usd ?? 0
  // Uso de cada barrera: 0 = holgado, ≥1 = tocado.
  const lossUse = hasLoss ? Math.min(Math.max(-today / (policy.daily_loss_limit_usd || 1), 0), 1) : 0
  const concUse = hasConc ? Math.min(topConcentration / (policy.max_concentration_pct || 1), 1) : 0
  const tone = (u: number) => u >= 1 ? 'bg-red-500' : u >= 0.75 ? 'bg-amber-400' : 'bg-emerald-500'

  return (
    <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-3">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold text-slate-300">Barreras de riesgo activas (OMS)</h3>
        <Link to="/trading" className="text-[10px] text-blue-400 hover:text-blue-300">editar →</Link>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {hasLoss && (
          <div>
            <div className="flex items-center justify-between text-[10px] mb-1">
              <span className="text-slate-500 uppercase">Pérdida diaria</span>
              <span className="font-mono text-slate-300">
                {usd(today, true)} / −{usd(policy.daily_loss_limit_usd)}
              </span>
            </div>
            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
              <div className={`h-full ${tone(lossUse)}`} style={{ width: `${lossUse * 100}%` }} />
            </div>
          </div>
        )}
        {hasConc && (
          <div>
            <div className="flex items-center justify-between text-[10px] mb-1">
              <span className="text-slate-500 uppercase">Concentración máx.</span>
              <span className="font-mono text-slate-300">
                {topConcentration.toFixed(0)}% / {policy.max_concentration_pct}%
              </span>
            </div>
            <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
              <div className={`h-full ${tone(concUse)}`} style={{ width: `${concUse * 100}%` }} />
            </div>
          </div>
        )}
      </div>
      {(lossUse >= 1 || concUse >= 1) && (
        <p className="text-[10px] text-amber-300 mt-2">
          ⚠ Una barrera está tocada: las compras en real que la crucen se bloquean.
        </p>
      )}
    </div>
  )
}

function RiskStat({ label, value, hint, strong = false }: Readonly<{
  label: string; value: string; hint: string; strong?: boolean
}>) {
  return (
    <div>
      <p className="text-[10px] text-slate-500 uppercase">{label}</p>
      <p className={`font-bold font-mono ${strong ? 'text-base text-amber-300' : 'text-sm text-red-300'}`}>{value}</p>
      <p className="text-[9px] text-slate-600">{hint}</p>
    </div>
  )
}
