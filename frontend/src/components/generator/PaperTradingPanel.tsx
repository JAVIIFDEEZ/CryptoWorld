/**
 * components/generator/PaperTradingPanel.tsx — Carteras virtuales en vivo.
 *
 * Lista las carteras de paper trading del usuario: cada una sigue una estrategia
 * generada e invierte capital ficticio según sus señales, registrando el P&L
 * REALIZADO. Es la verificación hacia delante (forward test) del generador: lo
 * que el backtest promete sobre el pasado, esto lo comprueba en vivo y sin riesgo.
 *
 * Y es la pantalla desde la que se cruza al dinero real, así que tiene una
 * obligación extra: **enseñar por qué la puerta no se abre**. El backend responde
 * con un 409 que detalla cada requisito que falta y, cuando lo hay, el plazo
 * estimado. Ese detalle se descartaba en un `catch` vacío: el usuario pulsaba
 * «Activar», no ocurría nada y nadie le decía por qué. Un «no» sin explicación es
 * exactamente lo que empuja a buscar la forma de rodear la puerta.
 */

import { useCallback, useEffect, useState } from 'react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'
import {
  strategyGeneratorService,
  SIGNAL_BADGES,
  SIGNAL_LABELS,
  SIGNAL_STYLES,
  type LiveOrderAudit,
  type PaperAccount,
  type PaperAccountDetail,
} from '@/services/strategyGeneratorService'
import { tradingService, type ExchangeConnection } from '@/services/tradingService'

/** Lo que el 409 de la puerta de incubación trae dentro. */
export interface IncubationBlock {
  note: string
  missing: string[]
  days_remaining?: number
  trades_remaining?: number
  psr?: number | null
  min_psr?: number
  days_remaining_estimate?: number | null
  runway_beyond_horizon?: boolean
  observations?: number
  observations_required?: number
}

/**
 * Extrae el bloque de incubación de un error de axios.
 *
 * Devuelve siempre algo legible: si la respuesta no trae el detalle esperado —otro
 * 4xx, un 500, un corte de red— se produce un mensaje genérico en lugar de `null`.
 * Devolver `null` dejaría la interfaz igual que con el `catch` vacío que esto
 * sustituye, que es el defecto que se está corrigiendo.
 */
export function readIncubationBlock(err: unknown): IncubationBlock {
  const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data
  const inc = data?.incubation as Record<string, unknown> | undefined

  if (!inc) {
    const generico = typeof data?.error === 'string'
      ? data.error
      : 'No se pudo activar la ejecución real. Inténtalo de nuevo.'
    return { note: generico, missing: [] }
  }

  const est = (inc.statistical ?? {}) as Record<string, unknown>
  return {
    note: String(inc.note ?? 'La cartera todavía no puede operar en real.'),
    missing: Array.isArray(inc.missing) ? (inc.missing as string[]) : [],
    days_remaining: typeof inc.days_remaining === 'number' ? inc.days_remaining : undefined,
    trades_remaining: typeof inc.trades_remaining === 'number' ? inc.trades_remaining : undefined,
    psr: typeof est.psr === 'number' ? est.psr : null,
    min_psr: typeof est.min_psr === 'number' ? est.min_psr : undefined,
    days_remaining_estimate:
      typeof est.days_remaining_estimate === 'number' ? est.days_remaining_estimate : null,
    runway_beyond_horizon: Boolean(est.runway_beyond_horizon),
    observations: typeof est.observations === 'number' ? est.observations : undefined,
    observations_required:
      typeof est.observations_required === 'number' ? est.observations_required : undefined,
  }
}

/**
 * Etiqueta legible de cada requisito que falta.
 *
 * `statistical_edge` es el que de verdad importa y el que nadie entendería por su
 * nombre técnico, así que se traduce a lo que significa: la curva todavía no
 * demuestra que haya ventaja.
 */
export function missingLabel(key: string): string {
  switch (key) {
    case 'min_days':
      return 'tiempo en simulado'
    case 'min_trades':
      return 'operaciones'
    case 'not_decayed':
      return 'la estrategia se ha degradado'
    case 'profitable':
      return 'P&L positivo'
    case 'statistical_edge':
      return 'evidencia de que hay ventaja'
    default:
      return key
  }
}

/**
 * El plazo, en una frase corta.
 *
 * Nunca devuelve un número absurdo: cuando el historial necesario pasa del
 * horizonte, el backend no publica cifra y aquí se dice lo que de verdad implica —
 * que lo que falta es un Sharpe mayor, no esperar más.
 */
export function runwayText(b: IncubationBlock): string | null {
  if (b.observations != null && b.observations_required != null
      && b.observations < b.observations_required) {
    return `Faltan ${b.observations_required - b.observations} días de curva para poder evaluarlo.`
  }
  if (b.days_remaining_estimate != null && b.days_remaining_estimate > 0) {
    return `Al ritmo actual faltarían unos ${b.days_remaining_estimate} días más.`
  }
  if (b.runway_beyond_horizon) {
    return 'A este ritmo no converge: lo que lo cambiaría es un Sharpe mayor, no esperar más.'
  }
  return null
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
  const [blocked, setBlocked] = useState<IncubationBlock | null>(null)

  async function enableLive() {
    if (!liveConnId) return
    setBusy(true)
    setBlocked(null)
    try {
      await strategyGeneratorService.setPaperLive(account.id, {
        enable: true, connection_id: Number(liveConnId), cap_usd: Number.parseFloat(liveCap) || 100,
      })
      setShowLive(false)
      onChange()
    } catch (err) {
      // El 409 de la puerta de incubación trae EXACTAMENTE lo que falta y el plazo
      // estimado. Descartarlo —como se hacía— dejaba al usuario pulsando un botón
      // que no hacía nada ni decía por qué, y un «no» sin explicación es lo que
      // empuja a buscar la forma de saltarse la puerta.
      setBlocked(readIncubationBlock(err))
    } finally { setBusy(false) }
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
          <span
            title={SIGNAL_LABELS[account.last_signal] ?? SIGNAL_LABELS.HOLD}
            className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${SIGNAL_STYLES[account.last_signal] ?? SIGNAL_STYLES.HOLD}`}
          >
            {SIGNAL_BADGES[account.last_signal] ?? SIGNAL_BADGES.HOLD}
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
            {blocked && (
              <div className="rounded border border-amber-500/40 bg-amber-500/10 p-2">
                <p className="text-[10px] font-medium text-amber-300">
                  La puerta de incubación no se ha abierto
                </p>
                {blocked.missing.length > 0 && (
                  <p className="mt-0.5 text-[10px] text-amber-200/90">
                    Falta: {blocked.missing.map(missingLabel).join(' · ')}
                  </p>
                )}
                {blocked.psr != null && blocked.min_psr != null && (
                  <p className="mt-0.5 font-mono text-[10px] text-amber-200/80">
                    probabilidad de ventaja {(blocked.psr * 100).toFixed(0)} % · hace falta{' '}
                    {(blocked.min_psr * 100).toFixed(0)} %
                  </p>
                )}
                {runwayText(blocked) && (
                  <p className="mt-0.5 text-[10px] text-amber-200/90">{runwayText(blocked)}</p>
                )}
                <p className="mt-1 text-[9px] leading-relaxed text-slate-400">{blocked.note}</p>
              </div>
            )}
            <p className="text-[9px] text-slate-500">
              Espeja las señales de esta cartera en tu exchange con tope de nocional por orden.
              Cualquier error del broker desactiva la ejecución (kill-switch).
              Activar exige evidencia de que la estrategia tiene ventaja, no solo tiempo
              en simulado.
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
                <span
                  title={SIGNAL_LABELS[t.side]}
                  className={`font-bold px-1 rounded border ${SIGNAL_STYLES[t.side]}`}
                >
                  {SIGNAL_BADGES[t.side]}
                </span>
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
