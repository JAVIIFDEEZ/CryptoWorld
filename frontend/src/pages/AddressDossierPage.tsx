/**
 * pages/AddressDossierPage.tsx — Dossier forense de una dirección (imprimible).
 *
 * Documento de auditoría con estética de papel que reúne las herramientas
 * forenses orientadas a direcciones: veredicto global, puntuación de riesgo,
 * huella conductual, aprobaciones ERC-20 vivas, entidad probable y patrones de
 * flujo. Ruta protegida sin AppShell: imprime limpio a PDF con el botón.
 */

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { blockchainService, type AddressDossier } from '@/services/blockchainService'

function short(a?: string | null): string {
  if (!a) return '—'
  return a.length > 16 ? `${a.slice(0, 8)}…${a.slice(-6)}` : a
}

const BAND_COLOR: Record<string, string> = {
  'CRÍTICO': 'text-red-700',
  'ELEVADO': 'text-amber-700',
  'MODERADO': 'text-yellow-700',
  'LIMPIO': 'text-emerald-700',
}

const SEV_ICON: Record<string, string> = { high: '🔴', medium: '🟠', info: '🔵' }

function Section({ title, children }: Readonly<{ title: string; children: React.ReactNode }>) {
  return (
    <section className="mb-5 break-inside-avoid">
      <h2 className="text-[11px] font-bold uppercase tracking-widest text-slate-500 border-b border-slate-300 pb-1 mb-2">
        {title}
      </h2>
      {children}
    </section>
  )
}

/** Documento puro: recibe el dossier ya cargado (testeable sin red). */
export function AddressDossierDocument({ d }: Readonly<{ d: AddressDossier }>) {
  const v = d.verdict
  const s = d.sections
  const fp = s.fingerprint?.fingerprint
  const risk = s.risk

  return (
    <article className="bg-white text-slate-900 rounded-xl shadow-2xl max-w-3xl mx-auto p-8 print:shadow-none print:rounded-none">
      <header className="border-b-2 border-slate-900 pb-4 mb-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-slate-500">Dossier forense · CryptoWorld</p>
            <h1 className="text-lg font-bold mt-1 font-mono break-all">{d.address}</h1>
            <p className="text-xs text-slate-600 mt-1">Red: {d.chain}</p>
          </div>
          <div className="text-right shrink-0">
            <p className={`text-2xl font-bold ${BAND_COLOR[v.band]}`}>{v.band}</p>
            <p className="text-[11px] text-slate-500 font-mono">{v.overall_score}/100</p>
          </div>
        </div>
        <p className="text-[11px] text-slate-600 mt-2">{v.headline}</p>
      </header>

      {/* Hallazgos clave */}
      <Section title="Hallazgos clave">
        {v.key_findings.length === 0 ? (
          <p className="text-xs text-slate-500">Sin hallazgos destacables en la muestra analizada.</p>
        ) : (
          <ul className="space-y-1 text-[12px]">
            {v.key_findings.map((f, i) => (
              <li key={i} className="flex items-start gap-2">
                <span>{SEV_ICON[f.severity]}</span>
                <span>{f.text}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      {/* Riesgo */}
      <Section title="Puntuación de riesgo">
        {risk && risk.available !== false && risk.score != null ? (
          <div className="text-[12px] space-y-1">
            <p>
              Banda <span className="font-bold">{risk.band}</span> · {risk.score}/100 ·{' '}
              {risk.flagged_counterparties} contraparte(s) señaladas de {risk.counterparties_analyzed} analizadas
            </p>
            {risk.factors?.slice(0, 4).map((f, i) => (
              <p key={i} className="text-slate-600">+{f.weight} · {f.detail}</p>
            ))}
          </div>
        ) : <p className="text-xs text-slate-500">Sección no disponible.</p>}
      </Section>

      {/* Conducta */}
      <Section title="Huella conductual">
        {fp?.available ? (
          <p className="text-[12px]">
            Arquetipo <span className="font-bold">{fp.archetype}</span> · {fp.sample_txs} tx en {fp.span_days} días ·{' '}
            {fp.txs_per_week} tx/semana · {fp.unique_counterparties} contrapartes ·{' '}
            última actividad hace {Math.round(fp.days_since_last ?? 0)} días
          </p>
        ) : <p className="text-xs text-slate-500">Actividad insuficiente o no disponible.</p>}
      </Section>

      {/* Aprobaciones */}
      <Section title="Aprobaciones ERC-20 vivas">
        {s.approvals?.available === false ? (
          <p className="text-xs text-slate-500">Sección no disponible.</p>
        ) : (s.approvals?.total ?? 0) === 0 ? (
          <p className="text-[12px] text-emerald-700">Sin aprobaciones activas.</p>
        ) : (
          <div className="text-[12px]">
            <p className="mb-1">{s.approvals.total} activas · {s.approvals.unlimited} ilimitadas · peor: <span className="font-bold">{s.approvals.worst}</span></p>
            <ul className="space-y-0.5">
              {s.approvals.approvals?.slice(0, 6).map((a, i) => (
                <li key={i} className="text-slate-600">
                  [{a.risk}] {a.token_symbol} → {short(a.spender)}{a.is_unlimited ? ' (∞)' : ''}
                </li>
              ))}
            </ul>
          </div>
        )}
      </Section>

      {/* Entidad + flujos */}
      <Section title="Entidad y flujos">
        <div className="text-[12px] space-y-1">
          {s.entity?.available === false ? null : (
            <p>Entidad probable: <span className="font-bold">{s.entity?.entity_size ?? 1}</span> direcciones vinculadas por co-movimiento ({s.entity?.neighbors_scanned ?? 0} vecinos escaneados).</p>
          )}
          {s.flow?.patterns && s.flow.patterns.length > 0 ? (
            <ul className="space-y-0.5">
              {s.flow.patterns.map((p, i) => (
                <li key={i} className="text-slate-600">
                  {p.type === 'fan_out' ? `Fan-out (${p.counterparties} contrapartes)` : `Peel chain (${p.depth} saltos)`}: {p.note}
                </li>
              ))}
            </ul>
          ) : <p className="text-slate-600">Sin patrones de flujo destacables.</p>}
        </div>
      </Section>

      <footer className="border-t border-slate-300 pt-3 text-[9px] text-slate-500 leading-relaxed">
        <p>{d.note}</p>
        <p className="font-mono mt-1">Dirección {d.address} · red {d.chain} · impreso {new Date().toLocaleString('es-ES')}</p>
      </footer>
    </article>
  )
}

export default function AddressDossierPage() {
  const { chain, address } = useParams<{ chain: string; address: string }>()
  const [dossier, setDossier] = useState<AddressDossier | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    if (!chain || !address) return
    blockchainService.addressDossier(chain, address)
      .then((d) => { if (!cancelled) { if (d.error) setError(d.error); else setDossier(d) } })
      .catch(() => { if (!cancelled) setError('No se pudo cargar el dossier.') })
    return () => { cancelled = true }
  }, [chain, address])

  return (
    <div className="min-h-screen bg-slate-900 py-8 px-4 print:bg-white print:p-0">
      <div className="max-w-3xl mx-auto flex items-center justify-between mb-4 print:hidden">
        <Link to="/blockchain" className="text-sm text-slate-400 hover:text-white">← Volver a Blockchain</Link>
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
      {!error && !dossier && <p className="text-center text-slate-500 text-sm py-12">Generando el dossier forense… (agrega 5 análisis, puede tardar unos segundos)</p>}
      {dossier && <AddressDossierDocument d={dossier} />}
    </div>
  )
}
