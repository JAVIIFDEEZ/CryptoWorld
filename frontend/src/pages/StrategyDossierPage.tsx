/**
 * pages/StrategyDossierPage.tsx — Dossier de auditoría de una estrategia.
 *
 * Documento imprimible (estética de papel, deliberadamente claro incluso en la
 * app oscura) que reúne toda la evidencia de una estrategia guardada: identidad
 * + ADN, robustez original del gating, validación holdout, análisis fresco
 * (equity y matriz walk-forward sobre datos actuales) y track record real.
 * Ruta sin AppShell: imprime limpio con el botón (⌘P → PDF).
 */

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  strategyGeneratorService,
  type StrategyDossier,
  type SpecCondition,
} from '@/services/strategyGeneratorService'

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('es-ES', { dateStyle: 'medium', timeStyle: 'short' })
}

function condLabel(c: SpecCondition): string {
  if (c.type === 'threshold') {
    const p = c.params?.window ? `(${c.params.window})` : ''
    return `${c.indicator}${p} ${c.op === 'lt' ? '<' : '>'} ${c.threshold}`
  }
  const a = c.a ? `${c.a.indicator}(${c.a.params?.window ?? ''})` : '?'
  const b = c.b ? `${c.b.indicator}(${c.b.params?.window ?? ''})` : '?'
  return `${a} ${c.op === 'cross_above' ? 'cruza ↑' : 'cruza ↓'} ${b}`
}

function EquityLine({ data }: Readonly<{ data: number[] }>) {
  if (data.length < 2) return null
  const W = 560, H = 120, PAD = 6
  const min = Math.min(...data), max = Math.max(...data)
  const range = max - min || 1
  const pts = data.map((v, i) => {
    const x = PAD + (i / (data.length - 1)) * (W - PAD * 2)
    const y = H - PAD - ((v - min) / range) * (H - PAD * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const up = data[data.length - 1] >= data[0]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Curva de equity reciente">
      <line x1={PAD} x2={W - PAD} y1={H - PAD} y2={H - PAD} stroke="#cbd5e1" strokeWidth={1} />
      <polyline points={pts} fill="none" stroke={up ? '#059669' : '#dc2626'} strokeWidth={2} strokeLinejoin="round" />
    </svg>
  )
}

function Check({ ok }: Readonly<{ ok: boolean }>) {
  return <span className={ok ? 'text-emerald-700' : 'text-red-700'}>{ok ? '✓' : '✗'}</span>
}

function Section({ title, children }: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <section className="mb-6 break-inside-avoid">
      <h2 className="text-[11px] font-bold uppercase tracking-widest text-slate-500 border-b border-slate-300 pb-1 mb-3">
        {title}
      </h2>
      {children}
    </section>
  )
}

const CHECK_LABELS: Record<string, string> = {
  min_trades: 'Nº mínimo de operaciones',
  no_lookahead: 'Sin sesgo de anticipación (lookahead)',
  wf_efficiency: 'Eficiencia walk-forward',
  pbo: 'Probabilidad de sobreajuste (PBO)',
  mc_p5_positive: 'Percentil 5 Monte Carlo positivo',
}

/** Documento puro: recibe el dossier ya cargado (testeable sin red). */
export function DossierDocument({ d }: Readonly<{ d: StrategyDossier }>) {
  const id = d.identity
  const m = d.stored_evidence.robustness_metrics
  const h = d.stored_evidence.holdout_metrics
  const checks = d.stored_evidence.gating_checks
  const fresh = d.fresh_analysis
  const wf = fresh.walk_forward_matrix

  return (
    <article className="bg-white text-slate-900 rounded-xl shadow-2xl max-w-3xl mx-auto p-8 print:shadow-none print:rounded-none">
      {/* Cabecera del documento */}
      <header className="border-b-2 border-slate-900 pb-4 mb-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-slate-500">Dossier de estrategia · CryptoWorld</p>
            <h1 className="text-xl font-bold mt-1">{id.description}</h1>
            <p className="text-xs text-slate-600 mt-1 font-mono">
              {id.asset_symbol} · {id.interval} · spec #{id.spec_hash}
            </p>
          </div>
          <div className="text-right text-[10px] text-slate-500 shrink-0">
            <p>Generada: {fmtDate(id.generated_at)}</p>
            <p>Estado: <span className="font-semibold text-slate-700">{id.status}</span></p>
            {id.fitness != null && <p>Fitness: <span className="font-mono font-semibold text-slate-700">{id.fitness.toFixed(3)}</span></p>}
          </div>
        </div>
      </header>

      {/* ADN */}
      <Section title="ADN de la estrategia">
        <div className="grid grid-cols-2 gap-4 text-xs">
          {(['entry', 'exit'] as const).map((side) => (
            <div key={side} className="border border-slate-300 rounded-lg p-3">
              <p className="font-bold text-[10px] uppercase tracking-wide mb-2 text-slate-600">
                {side === 'entry' ? '▶ Entrada' : '◀ Salida'} · {id.spec[side].combine}
              </p>
              <ul className="space-y-1 font-mono text-[11px]">
                {id.spec[side].conditions.map((c, i) => <li key={i}>{condLabel(c)}</li>)}
              </ul>
            </div>
          ))}
        </div>
      </Section>

      {/* Evidencia original */}
      <Section title="Evidencia de robustez (original de la generación)">
        {m ? (
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 text-center mb-3">
            {[
              ['Sharpe', m.sharpe?.toFixed(2)],
              ['Sharpe OOS', m.mean_oos_sharpe?.toFixed(2)],
              ['PBO', m.pbo != null ? `${Math.round(m.pbo * 100)}%` : '—'],
              ['Efic. WF', m.wf_efficiency?.toFixed(2)],
              ['Operaciones', m.n_trades],
              ['Multi-activo', m.cross_consistency != null ? `${Math.round(m.cross_consistency * 100)}%` : '—'],
            ].map(([label, value]) => (
              <div key={label as string} className="border border-slate-200 rounded p-2">
                <p className="text-sm font-bold font-mono">{value ?? '—'}</p>
                <p className="text-[9px] text-slate-500">{label}</p>
              </div>
            ))}
          </div>
        ) : <p className="text-xs text-slate-500">Sin métricas almacenadas.</p>}
        {checks && (
          <ul className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px]">
            {Object.entries(checks).map(([k, v]) => (
              <li key={k} className="flex items-center justify-between border-b border-dotted border-slate-300 py-0.5">
                <span>{CHECK_LABELS[k] ?? k}</span> <Check ok={!!v} />
              </li>
            ))}
          </ul>
        )}
        {h && (
          <p className="text-[11px] mt-3">
            <span className="font-semibold">Validación holdout (datos jamás vistos): </span>
            retorno <span className={`font-mono ${h.return_pct >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>{h.return_pct >= 0 ? '+' : ''}{h.return_pct}%</span>
            {' · '}Sharpe <span className="font-mono">{h.sharpe}</span>
            {' · '}drawdown <span className="font-mono">{h.max_drawdown_pct}%</span>
            {' · '}{h.n_trades} operaciones
          </p>
        )}
      </Section>

      {/* Estado actual */}
      <Section title="Análisis fresco (datos actuales)">
        {fresh.available && fresh.equity ? (
          <>
            <div className="flex items-center gap-4 text-[11px] mb-2">
              <span>
                Equity últimas {fresh.candles} velas:{' '}
                <span className={`font-mono font-semibold ${fresh.equity.total_return_pct >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                  {fresh.equity.total_return_pct >= 0 ? '+' : ''}{fresh.equity.total_return_pct}%
                </span>
              </span>
              <span className="text-slate-500">drawdown {fresh.equity.max_drawdown_pct}% · {fresh.equity.n_trades} ops · fuente {fresh.data_source}</span>
            </div>
            <EquityLine data={fresh.equity.equity} />
            {wf && (
              <p className="text-[11px] mt-2">
                <span className="font-semibold">Estabilidad walk-forward actual: </span>
                {wf.positive_folds}/{wf.total_folds} tramos positivos ({Math.round(wf.stability_score * 100)}%)
                {' — '}
                <span className={wf.stability_score >= 0.7 ? 'text-emerald-700' : 'text-amber-700'}>
                  {wf.stability_score >= 0.7 ? 'estable' : 'vigilar degradación'}
                </span>
              </p>
            )}
          </>
        ) : (
          <p className="text-xs text-slate-500">{fresh.note ?? 'No disponible.'}</p>
        )}
      </Section>

      {/* Track record */}
      <Section title="Track record real (paper trading del usuario)">
        {d.track_record.accounts.length === 0 ? (
          <p className="text-xs text-slate-500">Sin carteras siguiendo esta estrategia todavía.</p>
        ) : (
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-left text-[9px] uppercase text-slate-500 border-b border-slate-300">
                <th className="py-1">Inicio</th><th>Capital</th><th>Equity</th>
                <th>Retorno</th><th>P&L realizado</th><th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {d.track_record.accounts.map((a) => (
                <tr key={a.account_id} className="border-b border-dotted border-slate-200">
                  <td className="py-1">{fmtDate(a.started_at)}</td>
                  <td className="font-mono">${a.initial_capital.toLocaleString('es-ES')}</td>
                  <td className="font-mono">${a.equity.toLocaleString('es-ES')}</td>
                  <td className={`font-mono ${(a.total_return_pct ?? 0) >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>
                    {a.total_return_pct != null ? `${a.total_return_pct >= 0 ? '+' : ''}${a.total_return_pct}%` : '—'}
                  </td>
                  <td className="font-mono">${a.realized_pnl.toLocaleString('es-ES')}</td>
                  <td>
                    {a.decayed ? '⚠ decaída' : a.is_active ? (a.live_enabled ? '🔴 real' : '▶ activa') : '⏸ parada'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      {/* Pie de auditoría */}
      <footer className="border-t border-slate-300 pt-3 text-[9px] text-slate-500 leading-relaxed">
        <p>{d.note}</p>
        <p className="font-mono mt-1">Identidad del documento: spec #{id.spec_hash} · estrategia {id.strategy_id} · impreso {new Date().toLocaleString('es-ES')}</p>
      </footer>
    </article>
  )
}

export default function StrategyDossierPage() {
  const { id } = useParams<{ id: string }>()
  const [dossier, setDossier] = useState<StrategyDossier | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    if (!id) return
    strategyGeneratorService.getDossier(Number(id))
      .then((d) => { if (!cancelled) setDossier(d) })
      .catch(() => { if (!cancelled) setError('No se pudo cargar el dossier.') })
    return () => { cancelled = true }
  }, [id])

  return (
    <div className="min-h-screen bg-slate-900 py-8 px-4 print:bg-white print:p-0">
      {/* Barra de acciones (no se imprime) */}
      <div className="max-w-3xl mx-auto flex items-center justify-between mb-4 print:hidden">
        <Link to="/strategies" className="text-sm text-slate-400 hover:text-white">← Volver al generador</Link>
        {dossier && (
          <button
            onClick={() => window.print()}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium"
          >
            🖨 Imprimir / PDF
          </button>
        )}
      </div>

      {error && <p className="text-center text-red-400 text-sm py-12">{error}</p>}
      {!error && !dossier && <p className="text-center text-slate-500 text-sm py-12">Preparando el dossier…</p>}
      {dossier && <DossierDocument d={dossier} />}
    </div>
  )
}
