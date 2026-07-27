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
  type LiveOrderAudit,
  type PaperAccount,
  type PaperAccountDetail,
} from '@/services/strategyGeneratorService'
import { tradingService, type ExchangeConnection } from '@/services/tradingService'

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
  const [connections, setConnections] = useState<ExchangeConnection[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    tradingService.listConnections().then(setConnections).catch(() => { /* sin conexiones */ })
  }, [refreshKey])

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
        {accounts.map((a) => <PaperCard key={a.id} account={a} connections={connections} onChange={reload} />)}
      </div>
      <p className="text-[10px] text-slate-600 mt-3">
        Capital ficticio invertido según las señales de cada estrategia (con comisión y slippage).
        El P&L realizado se actualiza automáticamente al cierre de cada vela. No es asesoramiento financiero.
      </p>
    </div>
  )
}

function PaperCard({ account, connections, onChange }: Readonly<{
  account: PaperAccount; connections: ExchangeConnection[]; onChange: () => void
}>) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<PaperAccountDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [showLive, setShowLive] = useState(false)
  const [liveAudit, setLiveAudit] = useState<LiveOrderAudit | null>(null)
  const [liveConnId, setLiveConnId] = useState<number | ''>('')
  const [liveCap, setLiveCap] = useState('100')

  async function enableLive() {
    if (!liveConnId) return
    setBusy(true)
    try {
      await strategyGeneratorService.setPaperLive(account.id, {
        enable: true, connection_id: Number(liveConnId), cap_usd: Number.parseFloat(liveCap) || 100,
      })
      setShowLive(false)
      onChange()
    } catch { /* ignora */ } finally { setBusy(false) }
  }

  async function disableLive() {
    setBusy(true)
    try {
      await strategyGeneratorService.setPaperLive(account.id, { enable: false })
      onChange()
    } catch { /* ignora */ } finally { setBusy(false) }
  }

  async function toggleDetail() {
    const next = !open
    setOpen(next)
    if (next && !detail) {
      try { setDetail(await strategyGeneratorService.getPaperAccount(account.id)) } catch { /* ignora */ }
      // Auditoría de órdenes reales (solo si la cartera llegó a operar en real)
      try {
        const audit = await strategyGeneratorService.getPaperLiveOrders(account.id)
        if (audit.orders.length > 0) setLiveAudit(audit)
      } catch { /* sin auditoría */ }
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
          {account.live_enabled && (
            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${
              account.live_is_testnet
                ? 'bg-sky-500/15 text-sky-300 border-sky-500/40'
                : 'bg-red-500/20 text-red-300 border-red-500/40 animate-pulse'
            }`} title={`Ejecución real activa · tope $${account.live_cap_usd} por orden`}>
              {account.live_is_testnet ? '⚡ LIVE testnet' : '⚡ LIVE REAL'}
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

      {(account.live_discrepancy ?? 0) !== 0 && account.live_discrepancy != null && (
        <p className="text-[10px] text-amber-300 mt-1.5"
           title="La reconciliación periódica comparó la posición esperada con el balance real del exchange">
          ⚠ Reconciliación: el exchange difiere en {account.live_discrepancy > 0 ? '+' : ''}
          {account.live_discrepancy.toLocaleString(undefined, { maximumFractionDigits: 8 })} {account.asset_symbol}
        </p>
      )}
      {account.live_error && (
        <p className="text-[10px] text-red-300 mt-1.5" title={account.live_error}>
          ⛔ {account.live_error}
        </p>
      )}

      {account.is_active && (
        account.live_enabled ? (
          <button onClick={disableLive} disabled={busy}
            className="mt-1.5 w-full text-[11px] font-medium rounded-md py-1.5 border bg-red-600/15 text-red-300 border-red-500/40 hover:bg-red-600/25 transition-colors disabled:opacity-50">
            ⏹ Parar ejecución real
          </button>
        ) : showLive ? (
          <div className="mt-1.5 bg-slate-800/80 border border-slate-600 rounded-md p-2 space-y-1.5">
            <select value={liveConnId} onChange={(e) => setLiveConnId(e.target.value ? Number(e.target.value) : '')}
              className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200">
              <option value="">Elige conexión…</option>
              {connections.map((c) => (
                <option key={c.id} value={c.id}>{c.exchange}{c.label ? ` · ${c.label}` : ''} ({c.is_testnet ? 'testnet' : 'REAL'})</option>
              ))}
            </select>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] text-slate-500">tope $</span>
              <input type="number" min={10} max={10000} value={liveCap} onChange={(e) => setLiveCap(e.target.value)}
                className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-[11px] text-slate-200 font-mono" />
              <button onClick={enableLive} disabled={busy || !liveConnId}
                className="text-[11px] px-2.5 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-50">
                Activar
              </button>
              <button onClick={() => setShowLive(false)} className="text-[11px] text-slate-500 hover:text-slate-300">✕</button>
            </div>
            <p className="text-[9px] text-slate-500">
              Espeja las señales de esta cartera en tu exchange con tope de nocional por orden.
              Cualquier error del broker desactiva la ejecución (kill-switch).
            </p>
          </div>
        ) : (
          <button onClick={() => setShowLive(true)} disabled={connections.length === 0}
            title={connections.length === 0 ? 'Conecta un exchange en Trading primero' : 'Ejecutar las señales en tu exchange con tope'}
            className="mt-1.5 w-full text-[11px] font-medium rounded-md py-1.5 border bg-slate-800 text-slate-400 border-slate-600 hover:text-slate-200 transition-colors disabled:opacity-40">
            ⚡ Operar en real (con tope)
          </button>
        )
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

          {/* Auditoría de órdenes reales (promoción) */}
          {liveAudit && (
            <div className="mt-2 border-t border-slate-700/50 pt-2">
              <div className="flex items-center justify-between text-[10px] mb-1">
                <span className="text-slate-500 uppercase">Órdenes reales</span>
                <span>
                  <span className="text-slate-500">P&L real{liveAudit.pnl_is_estimate ? ' (est.)' : ''} </span>
                  <span className={`font-mono font-bold ${pnlTone(liveAudit.live_realized_pnl_usd)}`}>
                    ${liveAudit.live_realized_pnl_usd.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </span>
                  <span className="text-slate-600"> · paper ${liveAudit.paper_realized_pnl_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                </span>
              </div>
              {(liveAudit.slippage?.n_filled ?? 0) > 0 && (
                <p className="text-[10px] text-slate-500 mb-1">
                  Slippage real medio{' '}
                  <span className={`font-mono ${(liveAudit.slippage!.avg_slippage_bps ?? 0) > liveAudit.slippage!.modeled_slippage_bps ? 'text-amber-300' : 'text-emerald-400'}`}>
                    {liveAudit.slippage!.avg_slippage_bps?.toFixed(1)} bps
                  </span>
                  <span className="text-slate-600"> vs {liveAudit.slippage!.modeled_slippage_bps} bps del modelo · {liveAudit.slippage!.n_filled} ejecuciones</span>
                  {(liveAudit.blocked_orders ?? 0) > 0 && (
                    <span className="text-amber-300"> · {liveAudit.blocked_orders} bloqueadas por límite diario</span>
                  )}
                </p>
              )}
              <div className="max-h-32 overflow-y-auto space-y-1">
                {liveAudit.orders.map((o) => (
                  <div key={o.id} className="flex items-center gap-2 text-[10px]">
                    <span className={`font-bold px-1 rounded border text-[9px] ${o.side === 'buy' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' : 'bg-red-500/15 text-red-300 border-red-500/30'}`}>
                      {o.side.toUpperCase()}
                    </span>
                    <span className="text-slate-300 font-mono">{o.amount.toLocaleString(undefined, { maximumFractionDigits: 6 })}</span>
                    <span className="text-slate-500 font-mono">@ {(o.fill_price ?? o.ref_price).toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                    <span className={`text-[9px] px-1 rounded ${o.is_testnet ? 'text-sky-300' : 'text-red-300'}`}>{o.is_testnet ? 'testnet' : 'REAL'}</span>
                    {o.status === 'failed'
                      ? <span className="ml-auto text-red-400" title={o.error ?? ''}>✕ fallida</span>
                      : o.status === 'blocked'
                        ? <span className="ml-auto text-amber-300" title={o.error ?? ''}>⛔ bloqueada</span>
                        : <span className="ml-auto text-slate-600">{new Date(o.created_at).toLocaleDateString()}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
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
            contentStyle={{ background: 'rgb(var(--c-slate-900))', border: '1px solid rgb(var(--c-slate-700))', borderRadius: 8, fontSize: 11 }}
            labelFormatter={(l) => new Date(l as string).toLocaleString()}
            formatter={(v) => [`$${typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 0 }) : v}`, 'patrimonio']}
          />
          <Area type="monotone" dataKey="equity" stroke={stroke} strokeWidth={1.5} fill="url(#eqfill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
