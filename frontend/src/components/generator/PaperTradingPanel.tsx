/**
 * components/generator/PaperTradingPanel.tsx — Carteras virtuales en vivo.
 *
 * Lista las carteras de paper trading del usuario: cada una sigue una estrategia
 * generada e invierte capital ficticio según sus señales, registrando el P&L
 * REALIZADO. Es la verificación hacia delante (forward test) del generador: lo
 * que el backtest promete sobre el pasado, esto lo comprueba en vivo y sin riesgo.
 */

import { useCallback, useEffect, useState } from 'react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'
import {
  strategyGeneratorService,
  type PaperAccount,
  type PaperAccountDetail,
} from '@/services/strategyGeneratorService'

const SIGNAL_STYLE: Record<string, string> = {
  BUY: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  SELL: 'bg-red-500/15 text-red-400 border-red-500/30',
  HOLD: 'bg-slate-700/40 text-slate-400 border-slate-600/40',
}

function pnlTone(v: number): string {
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300'
}

export default function PaperTradingPanel({ refreshKey = 0 }: Readonly<{ refreshKey?: number }>) {
  const [accounts, setAccounts] = useState<PaperAccount[]>([])
  const [loading, setLoading] = useState(true)

  const reload = useCallback(() => {
    strategyGeneratorService.listPaperAccounts()
      .then(setAccounts)
      .catch(() => { /* sin carteras */ })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { reload() }, [reload, refreshKey])

  if (loading || accounts.length === 0) return null

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
        </span>
        <h3 className="text-sm font-semibold text-white">Paper trading</h3>
        <span className="text-[11px] text-slate-500">carteras virtuales que siguen tus estrategias en vivo</span>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {accounts.map((a) => <PaperCard key={a.id} account={a} onChange={reload} />)}
      </div>
      <p className="text-[10px] text-slate-600 mt-3">
        Capital ficticio invertido según las señales de cada estrategia (con comisión y slippage).
        El P&L realizado se actualiza automáticamente al cierre de cada vela. No es asesoramiento financiero.
      </p>
    </div>
  )
}

function PaperCard({ account, onChange }: Readonly<{ account: PaperAccount; onChange: () => void }>) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<PaperAccountDetail | null>(null)
  const [busy, setBusy] = useState(false)

  async function toggleDetail() {
    const next = !open
    setOpen(next)
    if (next && !detail) {
      try { setDetail(await strategyGeneratorService.getPaperAccount(account.id)) } catch { /* ignora */ }
    }
  }

  async function stop() {
    setBusy(true)
    try {
      await strategyGeneratorService.stopPaperAccount(account.id)
      onChange()
    } catch { /* ignora */ } finally { setBusy(false) }
  }

  const ret = account.total_return_pct
  return (
    <div className={`rounded-lg border p-3 ${account.is_active ? 'bg-slate-900/60 border-slate-700/60' : 'bg-slate-900/30 border-slate-800 opacity-70'}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[10px] text-emerald-300 font-semibold">{account.asset_symbol} · {account.interval}</span>
        <div className="flex items-center gap-1">
          {account.decayed && (
            <span className="text-[9px] font-bold px-1.5 py-0.5 rounded border bg-amber-500/15 text-amber-300 border-amber-500/40"
              title="Estrategia degradada en vivo: se ha disparado la reoptimización del activo">
              ⚠ decaída
            </span>
          )}
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${SIGNAL_STYLE[account.last_signal] ?? SIGNAL_STYLE.HOLD}`}>
            {account.last_signal}
          </span>
        </div>
      </div>
      <p className="text-[11px] text-slate-300 font-mono line-clamp-1 leading-snug" title={account.strategy_name ?? ''}>
        {account.strategy_name ?? `#${account.strategy_id}`}
      </p>

      <div className="flex items-baseline gap-2 mt-2">
        <span className={`text-xl font-bold font-mono ${pnlTone(ret)}`}>{ret >= 0 ? '+' : ''}{ret.toFixed(2)}%</span>
        <span className="text-[10px] text-slate-500">${account.equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
      </div>

      <div className="grid grid-cols-3 gap-1 mt-2 text-[10px]">
        <div>
          <p className="text-slate-500 uppercase">P&L real.</p>
          <p className={`font-mono ${pnlTone(account.realized_pnl)}`}>${account.realized_pnl.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
        </div>
        <div>
          <p className="text-slate-500 uppercase">Ops.</p>
          <p className="font-mono text-slate-300">{account.trades_count}</p>
        </div>
        <div>
          <p className="text-slate-500 uppercase">Aciertos</p>
          <p className="font-mono text-slate-300">{account.win_rate != null ? `${(account.win_rate * 100).toFixed(0)}%` : '—'}</p>
        </div>
      </div>

      {account.in_position && (
        <p className="text-[10px] text-amber-300/80 mt-1.5">
          En posición · entrada ${account.entry_price?.toLocaleString(undefined, { maximumFractionDigits: 2 })}
        </p>
      )}

      <div className="flex gap-1.5 mt-2">
        <button onClick={toggleDetail}
          className="flex-1 text-[10px] text-slate-300 bg-slate-800 border border-slate-600 rounded-md py-1 hover:text-white transition-colors">
          {open ? 'Ocultar' : 'Operaciones'}
        </button>
        {account.is_active && (
          <button onClick={stop} disabled={busy}
            className="text-[10px] text-red-300 bg-red-600/15 border border-red-500/40 rounded-md px-2 py-1 hover:bg-red-600/25 transition-colors disabled:opacity-50">
            Detener
          </button>
        )}
      </div>

      {open && detail && (
        <div className="mt-2 border-t border-slate-700/50 pt-2">
          {detail.equity_curve.length >= 2 && <EquityCurve points={detail.equity_curve} initial={detail.initial_capital} />}
          <div className="flex justify-between text-[10px] text-slate-500 mt-1.5 mb-1">
            <span>Operaciones</span>
            <span>Drawdown máx. actual <span className="text-amber-300 font-mono">{detail.drawdown_pct.toFixed(1)}%</span></span>
          </div>
          <div className="max-h-36 overflow-y-auto space-y-1">
            {detail.trades.length === 0 && <p className="text-[10px] text-slate-500">Aún sin operaciones.</p>}
            {detail.trades.map((t) => (
              <div key={t.id} className="flex items-center gap-2 text-[10px]">
                <span className={`font-bold px-1 rounded border ${SIGNAL_STYLE[t.side]}`}>{t.side}</span>
                <span className="text-slate-400 font-mono">${t.price.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                {t.pnl_pct != null && (
                  <span className={`font-mono ml-auto ${pnlTone(t.pnl_pct)}`}>{t.pnl_pct >= 0 ? '+' : ''}{t.pnl_pct.toFixed(2)}%</span>
                )}
                <span className="text-slate-600 shrink-0">{new Date(t.created_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function EquityCurve({ points, initial }: Readonly<{ points: { t: string; equity: number }[]; initial: number }>) {
  const data = points.map((p) => ({ t: p.t, equity: p.equity }))
  const last = data[data.length - 1]?.equity ?? initial
  const up = last >= initial
  const stroke = up ? '#22c55e' : '#ef4444'
  return (
    <div className="mb-1">
      <p className="text-[10px] text-slate-500 mb-0.5">Curva de equity (patrimonio en el tiempo)</p>
      <ResponsiveContainer width="100%" height={90}>
        <AreaChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 0 }}>
          <defs>
            <linearGradient id="eqfill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis domain={['dataMin', 'dataMax']} hide />
          <Tooltip
            contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 8, fontSize: 11 }}
            labelFormatter={(l) => new Date(l as string).toLocaleString()}
            formatter={(v) => [`$${typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : v}`, 'patrimonio']}
          />
          <Area type="monotone" dataKey="equity" stroke={stroke} strokeWidth={1.5} fill="url(#eqfill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
