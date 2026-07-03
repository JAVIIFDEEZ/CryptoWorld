/**
 * components/analysis/tabs/PredictTab.tsx — Pestaña de predicción ML de dirección
 * (con veredicto honesto, explicabilidad local, historial real y drift).
 */

import { useEffect, useState } from 'react'
import {
  analysisService,
  type PredictionResult,
  type PredictionTrackRecord,
} from '@/services/analysisService'
import PredictionMonitoringPanel from '@/components/analysis/PredictionMonitoringPanel'
import { EmptyState, MetricCard } from '@/components/analysis/analysisShared'

// ── Ring de confianza (SVG) ───────────────────────────────────────
function ConfidenceRing({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const r = 28, circ = 2 * Math.PI * r
  const offset = circ - (pct / 100) * circ
  const color = pct >= 70 ? '#22c55e' : pct >= 50 ? '#eab308' : '#ef4444'
  return (
    <div className="relative inline-flex items-center justify-center shrink-0">
      <svg width="72" height="72" className="-rotate-90">
        <circle cx="36" cy="36" r={r} fill="none" stroke="#334155" strokeWidth="6" />
        <circle cx="36" cy="36" r={r} fill="none" stroke={color} strokeWidth="6"
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
      </svg>
      <span className="absolute text-sm font-bold font-mono text-white">{pct}%</span>
    </div>
  )
}

const VERDICT_STYLE: Record<string, { chip: string; label: string }> = {
  EDGE: { chip: 'bg-green-500/15 text-green-300 border-green-500/30', label: 'Ventaja detectada' },
  WEAK: { chip: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30', label: 'Señal débil' },
  NO_EDGE: { chip: 'bg-red-500/15 text-red-300 border-red-500/30', label: 'Sin ventaja fiable' },
}

function PredictionVerdict({ data }: { data: PredictionResult }) {
  const v = VERDICT_STYLE[data.verdict ?? 'NO_EDGE']
  return (
    <div className={`rounded-lg border p-3 ${v.chip}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-bold uppercase tracking-wide">{v.label}</span>
        {data.n_oos !== undefined && (
          <span className="text-[11px] opacity-80">· {data.n_oos} muestras OOS en {data.n_splits} tramos</span>
        )}
      </div>
      {data.verdict_text && <p className="text-[11px] mt-1 text-slate-300">{data.verdict_text}</p>}
    </div>
  )
}

function PredictionTrackRecordPanel() {
  const [tr, setTr] = useState<PredictionTrackRecord | null>(null)
  useEffect(() => { analysisService.getPredictionTrackRecord().then(setTr).catch(() => { /* sin historial */ }) }, [])
  if (!tr || tr.resolved === 0) {
    return (
      <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-3 text-[11px] text-slate-400">
        <span className="text-slate-300 font-medium">Registro automático:</span> esta predicción se ha guardado y se
        verificará cuando transcurra el horizonte. Vuelve para ver el acierto real
        {tr && tr.pending > 0 ? ` (${tr.pending} pendientes).` : '.'}
      </div>
    )
  }
  const acc = tr.accuracy ?? 0
  const tone = acc >= 0.55 ? 'text-green-400' : acc >= 0.5 ? 'text-yellow-400' : 'text-red-400'
  return (
    <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-3">
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <h4 className="text-xs font-semibold text-slate-300">Historial real de aciertos</h4>
        <span className="text-[10px] text-slate-500">{tr.resolved} verificadas · {tr.pending} pendientes</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className={`text-2xl font-bold font-mono ${tone}`}>{(acc * 100).toFixed(1)}%</span>
        <span className="text-[11px] text-slate-500">{tr.correct}/{tr.resolved} aciertos en vivo</span>
      </div>
      {Object.keys(tr.by_verdict).length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {Object.entries(tr.by_verdict).map(([v, s]) => (
            <span key={v} className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
              {v}: {(s.accuracy * 100).toFixed(0)}% <span className="text-slate-500">({s.n})</span>
            </span>
          ))}
        </div>
      )}
      <p className="text-[10px] text-slate-600 mt-2">Rendimiento real verificado a posteriori, no el backtest. Por veredicto del modelo: ¿acierta más cuando dice tener edge?</p>
    </div>
  )
}

function PredictionDrivers({ data }: { data: PredictionResult }) {
  const drivers = data.drivers ?? []
  if (drivers.length === 0) return null
  const max = Math.max(...drivers.map((d) => Math.abs(d.contribution)), 1e-6)
  return (
    <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-3">
      <h4 className="text-xs font-semibold text-slate-300 mb-1">Por qué esta predicción</h4>
      <p className="text-[10px] text-slate-500 mb-2">
        Contribución de cada señal a la probabilidad alcista de ESTA vela (atribución por oclusión).
        Verde = empuja a subida; rojo = a bajada.
      </p>
      <div className="space-y-1.5">
        {drivers.map((d) => {
          const pos = d.contribution >= 0
          const w = Math.min((Math.abs(d.contribution) / max) * 100, 100)
          return (
            <div key={d.feature} className="flex items-center gap-2">
              <span className="text-[11px] text-slate-300 w-28 truncate" title={d.feature}>{d.feature}</span>
              <div className="flex-1 flex items-center">
                <div className="w-1/2 flex justify-end">
                  {!pos && <div className="bg-red-500/80 h-2 rounded-l-full" style={{ width: `${w}%` }} />}
                </div>
                <div className="w-px h-3 bg-slate-600" />
                <div className="w-1/2">
                  {pos && <div className="bg-green-500/80 h-2 rounded-r-full" style={{ width: `${w}%` }} />}
                </div>
              </div>
              <span className={`text-[10px] font-mono w-14 text-right ${pos ? 'text-green-400' : 'text-red-400'}`}>
                {pos ? '+' : ''}{(d.contribution * 100).toFixed(1)}%
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function PredictTab({ data }: { data: PredictionResult | null }) {
  const [showHow, setShowHow] = useState(false)

  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        }
        title="Predicción ML de dirección de precio"
        description="Ensemble (Random Forest + Gradient Boosting + Regresión logística) con indicadores técnicos como features. Predice si el precio subirá o bajará en las próximas N velas, validado walk-forward (out-of-sample) con probabilidad calibrada."
      />
    )
  }

  if (data.prediction === 'INSUFFICIENT_DATA') {
    return <div className="text-yellow-400 text-sm">{data.message}</div>
  }

  const isBullish = data.prediction === 'ALCISTA'

  return (
    <div className="space-y-4">
      {/* Disclaimer prominente */}
      <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg px-3 py-2 flex items-start gap-2">
        <svg className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <p className="text-[11px] text-amber-300/80">
          {data.disclaimer ?? 'Esta predicción es orientativa. El modelo ML no garantiza resultados futuros. No constituye asesoramiento financiero.'}
        </p>
      </div>

      {/* Predicción principal con ring */}
      <div className={`rounded-xl border p-5 ${isBullish ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30'}`}>
        <div className="flex items-center gap-5">
          <ConfidenceRing value={data.confidence} />
          <div className="flex-1">
            <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">
              Predicción — {data.horizon} velas adelante
            </p>
            <p className={`text-3xl font-bold ${isBullish ? 'text-green-400' : 'text-red-400'}`}>
              {isBullish ? '▲ ALCISTA' : '▼ BAJISTA'}
            </p>
            <div className="flex flex-wrap gap-4 mt-2">
              <div>
                <p className="text-[10px] text-slate-500 uppercase">
                  Confianza {data.calibrated && <span className="text-emerald-400 normal-case">· calibrada</span>}
                </p>
                <p className="text-sm font-bold font-mono text-white">
                  {(data.confidence * 100).toFixed(1)}%
                  {data.brier_score != null && (
                    <span className="text-slate-500 font-normal ml-1" title="Brier score: calidad de calibración (0 = perfecto)">Brier {data.brier_score.toFixed(3)}</span>
                  )}
                </p>
              </div>
              {data.oos_accuracy !== undefined && (
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Precisión OOS (walk-forward)</p>
                  <p className="text-sm font-bold font-mono text-white">
                    {(data.oos_accuracy * 100).toFixed(1)}%
                    {data.cv_std !== undefined && (
                      <span className="text-slate-500 font-normal ml-1">± {(data.cv_std * 100).toFixed(1)}%</span>
                    )}
                  </p>
                </div>
              )}
              {data.model && (
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Modelo</p>
                  <p className="text-sm font-mono text-slate-300">
                    {data.model}
                    {data.elapsed_ms != null && (
                      <span className="text-slate-500 ml-1" title="Tiempo de entrenamiento + validación">
                        · {(data.elapsed_ms / 1000).toFixed(1)}s
                      </span>
                    )}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Veredicto honesto: ¿hay edge fuera de muestra? */}
      {data.verdict && <PredictionVerdict data={data} />}

      {/* Métricas fuera de muestra (lo que realmente importa) */}
      {data.oos_accuracy !== undefined && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard label="Edge sobre el azar" value={`${(data.edge ?? 0) >= 0 ? '+' : ''}${((data.edge ?? 0) * 100).toFixed(1)}%`}
            color={(data.edge ?? 0) >= 0.04 ? 'text-green-400' : (data.edge ?? 0) >= 0.01 ? 'text-yellow-400' : 'text-red-400'} />
          <MetricCard label="Línea base (mayoría)" value={`${((data.baseline_accuracy ?? 0) * 100).toFixed(1)}%`} color="text-slate-300" />
          <MetricCard label="AUC" value={data.auc != null ? data.auc.toFixed(3) : '—'}
            color={(data.auc ?? 0) >= 0.55 ? 'text-green-400' : 'text-slate-300'} />
          <MetricCard label="F1 (subida)" value={data.f1_up != null ? data.f1_up.toFixed(2) : '—'} color="text-slate-300" />
        </div>
      )}

      {/* Explicabilidad local: por qué el modelo decide ESTA vela */}
      {data.drivers && data.drivers.length > 0 && <PredictionDrivers data={data} />}

      {/* Historial real verificado (bucle de mejora continua) */}
      <PredictionTrackRecordPanel />

      {/* Monitorización de drift: prometido OOS vs realizado en vivo */}
      <PredictionMonitoringPanel />

      {/* ¿Cómo funciona? — colapsable */}
      <div className="border border-slate-700 rounded-lg overflow-hidden">
        <button
          onClick={() => setShowHow(!showHow)}
          className="w-full flex items-center justify-between px-4 py-2.5 text-xs text-slate-300 hover:bg-slate-700/30 transition-colors"
        >
          <span className="font-medium">¿Cómo funciona este modelo?</span>
          <svg className={`w-4 h-4 text-slate-500 transition-transform ${showHow ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {showHow && (
          <div className="px-4 py-3 bg-slate-900/40 border-t border-slate-700 space-y-2 text-[11px] text-slate-400 leading-relaxed">
            <p><span className="text-slate-300 font-medium">Algoritmo:</span> ensemble por votación blanda de Random Forest, Gradient Boosting y regresión logística. Combina familias de modelos con sesgos distintos para reducir overfitting y mejorar la generalización.</p>
            <p><span className="text-slate-300 font-medium">Explicabilidad local:</span> para cada predicción se mide, por oclusión, cuánto aporta cada señal a la probabilidad de subida de esa vela concreta (panel «Por qué esta predicción»).</p>
            <p><span className="text-slate-300 font-medium">Monitorización de drift:</span> se compara la precisión prometida fuera de muestra con la realizada en vivo; si cae de forma sostenida, el panel avisa para reoptimizar.</p>
            <p><span className="text-slate-300 font-medium">Features:</span> Indicadores técnicos calculados sobre las últimas N velas: RSI, MACD, Bollinger, ATR, ADX, EMA, volumen relativo y variaciones de precio.</p>
            <p><span className="text-slate-300 font-medium">Target:</span> Variable binaria — ¿sube o baja el precio en las próximas {data.horizon} velas?</p>
            <p><span className="text-slate-300 font-medium">Validación walk-forward:</span> se entrena en el pasado y se valida en el futuro (TimeSeriesSplit), nunca al revés — así la precisión OOS es honesta, sin fuga del futuro. El <span className="text-slate-300">edge</span> es la ventaja sobre predecir siempre la clase mayoritaria: si es ~0, no hay señal real aunque la precisión parezca alta.</p>
            <p><span className="text-slate-300 font-medium">Probabilidad calibrada:</span> la confianza se calibra (Platt) para que un 70% signifique de verdad ~70% de acierto, no el voto crudo del bosque (que suele estar sobreconfiado). El Brier score mide esa calidad de calibración.</p>
          </div>
        )}
      </div>

      {/* Feature importances */}
      {data.features_importance && data.features_importance.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 uppercase mb-2">Variables más influyentes</p>
          <div className="space-y-1.5">
            {data.features_importance.map((fi) => (
              <div key={fi.feature} className="flex items-center gap-2">
                <span className="text-[11px] text-slate-300 w-28 truncate" title={fi.feature}>{fi.feature}</span>
                <div className="flex-1 bg-slate-700 rounded-full h-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full transition-all"
                    style={{ width: `${Math.min(fi.importance * 100 / (data.features_importance![0]?.importance || 1), 100)}%` }}
                  />
                </div>
                <span className="text-[10px] font-mono text-slate-400 w-12 text-right">
                  {(fi.importance * 100).toFixed(1)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
