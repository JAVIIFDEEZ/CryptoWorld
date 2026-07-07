/**
 * components/analysis/ConfluencePanel.tsx — Motor de confluencia 360°.
 *
 * Fusiona en un solo veredicto las cuatro fuentes del sistema (técnica, ML,
 * on-chain y noticias) con pesos APRENDIDOS del acierto histórico real de
 * cada una. Muestra el score fusionado, el acuerdo entre fuentes y el
 * desglose por fuente: su lectura, su peso y si ese peso es aprendido
 * (con acierto y muestra) o a priori (arranque en frío).
 */

import { useEffect, useState } from 'react'
import { analysisService, type ConfluenceReading } from '@/services/analysisService'

const SOURCE_META: Record<string, { name: string; icon: string }> = {
  technical: { name: 'Técnica', icon: '📊' },
  ml: { name: 'Predicción ML', icon: '🤖' },
  onchain: { name: 'On-chain', icon: '⛓' },
  news: { name: 'Noticias', icon: '📰' },
}

const VERDICT_STYLE: Record<string, { frame: string; label: string; color: string }> = {
  CONFLUENCIA_ALCISTA: { frame: 'bg-green-500/10 border-green-500/30', label: '▲ CONFLUENCIA ALCISTA', color: 'text-green-400' },
  CONFLUENCIA_BAJISTA: { frame: 'bg-red-500/10 border-red-500/30', label: '▼ CONFLUENCIA BAJISTA', color: 'text-red-400' },
  MIXTO: { frame: 'bg-amber-500/10 border-amber-500/30', label: '⇄ FUENTES DIVIDIDAS', color: 'text-amber-300' },
  NEUTRAL: { frame: 'bg-slate-700/20 border-slate-600/50', label: '→ NEUTRAL', color: 'text-slate-300' },
  INSUFICIENTE: { frame: 'bg-slate-700/20 border-slate-600/50', label: '· INSUFICIENTE', color: 'text-slate-400' },
}

function ScoreBar({ score }: Readonly<{ score: number | null }>) {
  if (score === null) return <div className="flex-1 h-2 rounded-full bg-slate-700/40" />
  const pct = Math.min(Math.abs(score), 1) * 50
  const pos = score >= 0
  return (
    <div className="flex-1 flex items-center">
      <div className="w-1/2 flex justify-end">
        {!pos && <div className="bg-red-500/80 h-2 rounded-l-full" style={{ width: `${pct * 2}%` }} />}
      </div>
      <div className="w-px h-3 bg-slate-600" />
      <div className="w-1/2">
        {pos && <div className="bg-green-500/80 h-2 rounded-r-full" style={{ width: `${pct * 2}%` }} />}
      </div>
    </div>
  )
}

export default function ConfluencePanel({ symbol }: Readonly<{ symbol: string }>) {
  const [data, setData] = useState<ConfluenceReading | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true); setError(false); setData(null)
    analysisService.getConfluence(symbol)
      .then((r) => { if (!cancelled) setData(r.error ? null : r) })
      .catch(() => { if (!cancelled) setError(true) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [symbol])

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
        <div className="flex items-center gap-3 text-sm text-slate-400">
          <div className="w-5 h-5 border-2 border-slate-600 border-t-blue-400 rounded-full animate-spin" />
          Fusionando técnica, ML, on-chain y noticias…
        </div>
      </div>
    )
  }
  if (error || !data) return null   // sin confluencia no se ocupa espacio

  const v = VERDICT_STYLE[data.verdict] ?? VERDICT_STYLE.NEUTRAL

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
      <div className="px-5 pt-4 pb-1 flex items-center gap-2">
        <span>🎯</span>
        <h2 className="text-lg font-semibold text-white">Confluencia 360°</h2>
        <span className="text-[10px] text-slate-500">
          técnica + ML + on-chain + noticias · pesos aprendidos del acierto real
        </span>
      </div>

      <div className="p-5 pt-3 space-y-4">
        {/* Veredicto fusionado */}
        <div className={`rounded-xl border p-4 ${v.frame}`}>
          <div className="flex items-center gap-4 flex-wrap">
            <p className={`text-2xl font-bold ${v.color}`}>{v.label}</p>
            {data.verdict !== 'INSUFICIENTE' && (
              <>
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Score fusionado</p>
                  <p className="text-sm font-bold font-mono text-white">
                    {data.score >= 0 ? '+' : ''}{data.score.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Acuerdo</p>
                  <p className="text-sm font-bold font-mono text-white">{data.agreement_pct.toFixed(0)}%</p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Fuentes</p>
                  <p className="text-sm font-bold font-mono text-white">{data.sources_available}/4</p>
                </div>
              </>
            )}
          </div>
          {data.verdict_text && <p className="text-[11px] text-slate-400 mt-2">{data.verdict_text}</p>}
        </div>

        {/* Desglose por fuente */}
        <div className="space-y-2">
          {Object.entries(data.sources).map(([key, src]) => {
            const meta = SOURCE_META[key] ?? { name: key, icon: '·' }
            return (
              <div key={key} className="flex items-center gap-3">
                <span className="w-32 shrink-0 text-[11px] text-slate-300 truncate">
                  {meta.icon} {meta.name}
                </span>
                <ScoreBar score={src.available ? src.score : null} />
                <span className={`w-14 text-right text-[11px] font-mono ${
                  !src.available ? 'text-slate-600'
                    : (src.score ?? 0) > 0 ? 'text-green-400'
                      : (src.score ?? 0) < 0 ? 'text-red-400' : 'text-slate-400'
                }`}>
                  {src.available && src.score !== null ? `${src.score >= 0 ? '+' : ''}${src.score.toFixed(2)}` : '—'}
                </span>
                <span
                  className={`w-28 shrink-0 text-right text-[10px] font-mono ${
                    src.weight_mode === 'aprendido_activo' ? 'text-emerald-400'
                      : src.weight_mode === 'aprendido_global' ? 'text-teal-400' : 'text-slate-500'
                  }`}
                  title={src.weight_mode === 'a_priori'
                    ? `Peso a priori (muestra insuficiente: ${src.sample} lecturas verificadas)`
                    : `Peso aprendido ${src.weight_mode === 'aprendido_activo' ? 'sobre ESTE activo' : 'del acierto global de la fuente'}: ${(100 * (src.hit_rate ?? 0)).toFixed(0)}% de acierto en ${src.sample} lecturas verificadas`}
                >
                  peso {(src.weight * 100).toFixed(0)}%
                  {src.weight_mode === 'aprendido_activo' ? ' ✓✓' : src.weight_mode === 'aprendido_global' ? ' ✓' : ''}
                </span>
              </div>
            )
          })}
        </div>

        {/* Track record del propio motor (acierto verificado a posteriori) */}
        {data.track_record && data.track_record.overall.n > 0 && (
          <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 px-3 py-2 flex items-center gap-3 flex-wrap">
            <span className="text-[10px] uppercase text-slate-500">Acierto del motor</span>
            <span className={`text-sm font-bold font-mono ${
              (data.track_record.overall.hit_rate ?? 0) >= 0.55 ? 'text-green-400'
                : (data.track_record.overall.hit_rate ?? 0) >= 0.5 ? 'text-yellow-400' : 'text-red-400'
            }`}>
              {(100 * (data.track_record.overall.hit_rate ?? 0)).toFixed(0)}%
            </span>
            <span className="text-[10px] text-slate-500">
              en {data.track_record.overall.n} lecturas verificadas · retorno medio en la dirección de la lectura{' '}
              {(data.track_record.overall.avg_signed_return_pct ?? 0) >= 0 ? '+' : ''}
              {(data.track_record.overall.avg_signed_return_pct ?? 0).toFixed(2)}%
            </span>
            {Object.entries(data.track_record.by_verdict).map(([verd, st]) => (
              <span key={verd} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-400">
                {verd.replace('CONFLUENCIA_', '')}: {(100 * (st.hit_rate ?? 0)).toFixed(0)}% ({st.n})
              </span>
            ))}
          </div>
        )}

        {/* Detalles de cada fuente (una línea honesta por fuente) */}
        <div className="space-y-0.5">
          {Object.entries(data.sources).map(([key, src]) => (
            <p key={key} className="text-[10px] text-slate-500 truncate">
              <span className="text-slate-400">{SOURCE_META[key]?.name ?? key}:</span> {src.detail}
            </p>
          ))}
        </div>

        <p className="text-[10px] text-slate-600">{data.note}</p>
      </div>
    </div>
  )
}
