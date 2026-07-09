/**
 * components/analysis/QuantTerminal.tsx — Terminal cuantitativa institucional.
 *
 * Fotografía cuantitativa densa del activo, estilo terminal profesional
 * (Bloomberg): volatilidad realizada anualizada, ATR, retornos multi-horizonte
 * con z-score, Sharpe/Sortino del activo, drawdown, posición en el rango,
 * beta/correlación frente a BTC, volumen relativo y clasificador de régimen.
 * Todo derivado del precio — sin opiniones, solo el estado cuantitativo AHORA.
 */

import { useEffect, useState } from 'react'
import { analysisService, type QuantSnapshot, type IntervalType } from '@/services/analysisService'

const INTERVALS: IntervalType[] = ['15m', '1h', '4h', '1d']

// ── Formateo monoespaciado ─────────────────────────────────────────

function n2(v: number | null | undefined, dp = 2): string {
  if (v == null) return '—'
  return v.toLocaleString('es-ES', { minimumFractionDigits: dp, maximumFractionDigits: dp })
}
function pct(v: number | null | undefined, dp = 2, sign = true): string {
  if (v == null) return '—'
  return `${sign && v >= 0 ? '+' : ''}${v.toFixed(dp)}%`
}
function price(v: number | null | undefined): string {
  if (v == null) return '—'
  const dp = v >= 100 ? 2 : v >= 1 ? 4 : 6
  return `$${v.toLocaleString('es-ES', { minimumFractionDigits: dp, maximumFractionDigits: dp })}`
}
function signColor(v: number | null | undefined): string {
  if (v == null) return 'text-slate-600'
  return v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-slate-300'
}

const BIAS: Record<string, { label: string; cls: string }> = {
  ALCISTA: { label: '▲ ALCISTA', cls: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' },
  BAJISTA: { label: '▼ BAJISTA', cls: 'text-red-400 bg-red-500/10 border-red-500/30' },
  NEUTRAL: { label: '→ NEUTRAL', cls: 'text-slate-300 bg-slate-700/30 border-slate-600/50' },
}
const VOL_REGIME: Record<string, string> = {
  ALTA: 'text-red-400', NORMAL: 'text-slate-300', BAJA: 'text-emerald-400', '—': 'text-slate-600',
}

// ── Piezas ──────────────────────────────────────────────────────────

function Cell({ label, children, hint }: Readonly<{ label: string; children: React.ReactNode; hint?: string }>) {
  return (
    <div className="min-w-0" title={hint}>
      <p className="text-[9px] uppercase tracking-wider text-slate-500 truncate">{label}</p>
      <p className="text-[13px] font-mono tabular-nums font-semibold truncate">{children}</p>
    </div>
  )
}

function Section({ title, children }: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <div className="border border-slate-800 rounded-lg bg-slate-900/40 p-3">
      <p className="text-[9px] uppercase tracking-[0.15em] text-amber-500/70 mb-2 font-semibold">{title}</p>
      {children}
    </div>
  )
}

function Spark({ data, up }: Readonly<{ data: number[]; up: boolean }>) {
  const w = 120, h = 30
  if (data.length < 2) return null
  const pts = data.map((v, i) => `${((i / (data.length - 1)) * w).toFixed(1)},${(h - v * h).toFixed(1)}`).join(' ')
  return (
    <svg width={w} height={h} className="shrink-0" aria-hidden>
      <polyline points={pts} fill="none" stroke={up ? '#34d399' : '#f87171'} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  )
}

/** Barra 0-100 con marcador de la posición actual en el rango de la ventana. */
function RangeBar({ rank }: Readonly<{ rank: number | null }>) {
  if (rank == null) return null
  const clamped = Math.max(0, Math.min(100, rank))
  return (
    <div className="relative h-1.5 rounded-full bg-gradient-to-r from-red-500/40 via-slate-600/40 to-emerald-500/40 mt-1">
      <div className="absolute top-1/2 -translate-y-1/2 w-1.5 h-3 rounded-full bg-white shadow" style={{ left: `calc(${clamped}% - 3px)` }} />
    </div>
  )
}

// ── Componente principal ────────────────────────────────────────────

export default function QuantTerminal({ symbol }: Readonly<{ symbol: string }>) {
  const [interval, setInterval] = useState<IntervalType>('1h')
  const [snap, setSnap] = useState<QuantSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(false)
    analysisService.getQuantSnapshot(symbol, interval)
      .then((s) => { if (!cancelled) { if (s.error) { setError(true); setSnap(null) } else setSnap(s) } })
      .catch(() => { if (!cancelled) setError(true) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol, interval])

  const bias = BIAS[snap?.bias ?? 'NEUTRAL'] ?? BIAS.NEUTRAL

  return (
    <div className="rounded-xl border border-amber-500/20 bg-slate-900 overflow-hidden">
      {/* Barra de mando estilo terminal */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-slate-800 bg-slate-950/60 flex-wrap">
        <span className="text-amber-400 font-mono text-xs font-bold tracking-widest">QNT▸</span>
        <span className="text-white font-mono text-sm font-bold">{symbol}</span>
        <span className="text-slate-500 font-mono text-xs">·{interval}</span>
        {snap && !error && (
          <>
            <span className="text-white font-mono text-sm font-bold tabular-nums">{price(snap.last_price)}</span>
            <span className={`text-[11px] font-mono font-semibold px-2 py-0.5 rounded border ${bias.cls}`}>{bias.label}</span>
            <span className="text-[10px] font-mono text-slate-400 truncate hidden sm:inline">{snap.regime.label}</span>
            <div className="ml-auto flex items-center gap-3">
              <Spark data={snap.spark} up={snap.bias !== 'BAJISTA'} />
            </div>
          </>
        )}
        <div className={`flex gap-0.5 bg-slate-900 rounded-md p-0.5 ${snap && !error ? '' : 'ml-auto'}`}>
          {INTERVALS.map((iv) => (
            <button
              key={iv}
              onClick={() => setInterval(iv)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium transition-colors ${
                interval === iv ? 'bg-amber-500/20 text-amber-300' : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {iv}
            </button>
          ))}
        </div>
      </div>

      {/* Cuerpo */}
      <div className="p-3">
        {loading && <p className="text-xs text-slate-500 font-mono py-6 text-center">Calculando estadística cuantitativa…</p>}
        {!loading && (error || !snap) && (
          <p className="text-xs text-amber-300/70 font-mono py-4 text-center">
            Sin datos de mercado suficientes para {symbol} en {interval}.
          </p>
        )}

        {!loading && snap && !error && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-2.5">
            {/* VOLATILIDAD */}
            <Section title="Volatilidad">
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <Cell label="σ anual" hint="Volatilidad realizada anualizada">
                  <span className="text-slate-200">{n2(snap.volatility.annualized_pct, 1)}%</span>
                </Cell>
                <Cell label="Régimen vol.">
                  <span className={VOL_REGIME[snap.volatility.regime] ?? 'text-slate-300'}>{snap.volatility.regime}</span>
                </Cell>
                <Cell label="ATR (14)" hint="Average True Range — rango real medio">
                  <span className="text-slate-200">{n2(snap.volatility.atr, 2)}</span>
                </Cell>
                <Cell label="ATR %">
                  <span className="text-slate-200">{n2(snap.volatility.atr_pct, 2)}%</span>
                </Cell>
              </div>
            </Section>

            {/* RETORNOS */}
            <Section title="Retornos">
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                {snap.returns.map((r) => (
                  <Cell key={r.h} label={`${r.h} vela${r.h > 1 ? 's' : ''}`}>
                    <span className={signColor(r.pct)}>{pct(r.pct)}</span>
                  </Cell>
                ))}
                <Cell label="Z última" hint="Cuántas σ se aleja el retorno de la última vela de su media">
                  <span className={Math.abs(snap.z_last_return ?? 0) >= 2 ? 'text-amber-400' : 'text-slate-300'}>
                    {snap.z_last_return == null ? '—' : `${snap.z_last_return >= 0 ? '+' : ''}${snap.z_last_return.toFixed(2)}σ`}
                  </span>
                </Cell>
              </div>
            </Section>

            {/* RIESGO */}
            <Section title="Riesgo (activo)">
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <Cell label="Sharpe" hint="Sharpe anualizado del propio activo (rf=0)">
                  <span className={signColor(snap.risk.sharpe)}>{n2(snap.risk.sharpe, 2)}</span>
                </Cell>
                <Cell label="Sortino" hint="Como Sharpe pero penaliza solo la volatilidad a la baja">
                  <span className={signColor(snap.risk.sortino)}>{n2(snap.risk.sortino, 2)}</span>
                </Cell>
                <Cell label="DD máx" hint="Máxima caída pico-a-valle en la ventana">
                  <span className="text-red-400">{pct(snap.risk.max_drawdown_pct, 1, false)}</span>
                </Cell>
                <Cell label="DD actual" hint="Caída actual respecto al máximo reciente">
                  <span className={snap.risk.current_drawdown_pct && snap.risk.current_drawdown_pct < -0.01 ? 'text-red-400' : 'text-emerald-400'}>
                    {pct(snap.risk.current_drawdown_pct, 1, false)}
                  </span>
                </Cell>
              </div>
            </Section>

            {/* RANGO */}
            <Section title="Rango de la ventana">
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <Cell label="Máx"><span className="text-slate-200">{price(snap.range.high)}</span></Cell>
                <Cell label="Mín"><span className="text-slate-200">{price(snap.range.low)}</span></Cell>
                <Cell label="a máx"><span className="text-red-400">{pct(snap.range.dist_to_high_pct, 2)}</span></Cell>
                <Cell label="a mín"><span className="text-emerald-400">{pct(snap.range.dist_to_low_pct, 2)}</span></Cell>
              </div>
              <div className="mt-2">
                <p className="text-[9px] uppercase tracking-wider text-slate-500">Posición · {n2(snap.range.pct_rank, 0)}%</p>
                <RangeBar rank={snap.range.pct_rank} />
              </div>
            </Section>

            {/* RÉGIMEN */}
            <Section title="Régimen de tendencia">
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <Cell label="ADX (14)" hint="Fuerza de la tendencia (>25 fuerte)">
                  <span className={
                    (snap.regime.adx ?? 0) >= 25 ? 'text-amber-300' : 'text-slate-400'
                  }>{n2(snap.regime.adx, 1)}</span>
                </Cell>
                <Cell label="Fuerza"><span className="text-slate-300 text-[11px]">{snap.regime.strength}</span></Cell>
                <Cell label="+DI / −DI">
                  <span className="text-emerald-400">{n2(snap.regime.plus_di, 0)}</span>
                  <span className="text-slate-600">/</span>
                  <span className="text-red-400">{n2(snap.regime.minus_di, 0)}</span>
                </Cell>
                <Cell label="P vs SMA20">
                  <span className={signColor(snap.regime.price_vs_sma20_pct)}>{pct(snap.regime.price_vs_sma20_pct, 2)}</span>
                </Cell>
              </div>
              <div className="mt-2">
                <p className="text-[9px] uppercase tracking-wider text-slate-500 mb-1">Confirmaciones alcistas · {snap.bull_confirmations}/5</p>
                <div className="flex gap-0.5">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <div key={i} className={`h-1.5 flex-1 rounded-full ${i < snap.bull_confirmations ? 'bg-emerald-500/70' : 'bg-slate-700'}`} />
                  ))}
                </div>
              </div>
            </Section>

            {/* MERCADO */}
            <Section title="Riesgo sistemático">
              <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                <Cell label="β vs BTC" hint="Sensibilidad de sus retornos a los de BTC (1 = se mueve igual)">
                  <span className="text-slate-200">{snap.symbol === 'BTC' ? '1.00*' : n2(snap.market.beta_btc, 2)}</span>
                </Cell>
                <Cell label="ρ vs BTC" hint="Correlación de retornos con BTC">
                  <span className="text-slate-200">{snap.symbol === 'BTC' ? '1.00*' : n2(snap.market.corr_btc, 2)}</span>
                </Cell>
                <Cell label="Vol. rel." hint="Volumen de la última vela frente a la media de las 20 previas">
                  <span className={(snap.volume.relative ?? 1) >= 1.5 ? 'text-amber-300' : 'text-slate-300'}>
                    {snap.volume.has_volume ? `${n2(snap.volume.relative, 2)}×` : '—'}
                  </span>
                </Cell>
                <Cell label="Vol. Z">
                  <span className="text-slate-300">{snap.volume.has_volume ? n2(snap.volume.z_score, 2) : '—'}</span>
                </Cell>
              </div>
            </Section>
          </div>
        )}

        {snap && !error && (
          <p className="text-[9px] text-slate-600 font-mono mt-2.5">
            {snap.candles} velas · fuente {snap.data_source ?? '—'}
            {snap.symbol === 'BTC' && ' · *BTC es la referencia'} · {snap.disclaimer}
          </p>
        )}
      </div>
    </div>
  )
}
