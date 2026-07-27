/**
 * components/analysis/tabs/PredictTab.tsx — Pestaña de predicción ML.
 *
 * Estructura en capas para no abrumar: (1) el veredicto y la predicción en un
 * héroe único; (2) por qué el modelo decide esto (drivers); (3) secciones
 * plegables con la fiabilidad del modelo, el seguimiento en vivo y la
 * explicación de cómo funciona. La predicción puede ser NEUTRAL: dentro de la
 * banda 45–55% el modelo no proclama dirección (honestidad ante la moneda al
 * aire) y no se registra en el historial.
 */

import { useState, type ReactNode } from 'react'
import {
  analysisService,
  type PredictionResult,
  type PredictionTrackRecord,
} from '@/services/analysisService'
import { useEffect } from 'react'
import PredictionMonitoringPanel from '@/components/analysis/PredictionMonitoringPanel'
import { EmptyState, MetricCard } from '@/components/analysis/analysisShared'

// ── Ring de confianza (SVG) ───────────────────────────────────────
function ConfidenceRing({ value, neutral = false }: { value: number; neutral?: boolean }) {
  const pct = Math.round(value * 100)
  const r = 28, circ = 2 * Math.PI * r
  const offset = circ - (pct / 100) * circ
  const color = neutral ? '#94a3b8' : pct >= 70 ? '#22c55e' : pct >= 55 ? '#eab308' : '#ef4444'
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

// ── Sección plegable reutilizable ─────────────────────────────────
function Section({
  title, subtitle, defaultOpen = false, badge, children,
}: Readonly<{ title: string; subtitle?: string; defaultOpen?: boolean; badge?: ReactNode; children: ReactNode }>) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-slate-700 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left hover:bg-slate-700/30 transition-colors"
      >
        <span className="min-w-0">
          <span className="block text-xs font-semibold text-slate-200">{title}</span>
          {subtitle && <span className="block text-[10px] text-slate-500 truncate">{subtitle}</span>}
        </span>
        <span className="flex items-center gap-2 shrink-0">
          {badge}
          <svg className={`w-4 h-4 text-slate-500 transition-transform ${open ? 'rotate-180' : ''}`}
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </span>
      </button>
      {open && <div className="px-4 py-3 bg-slate-900/40 border-t border-slate-700 space-y-3">{children}</div>}
    </div>
  )
}

function PredictionTrackRecordPanel() {
  const [tr, setTr] = useState<PredictionTrackRecord | null>(null)
  useEffect(() => { analysisService.getPredictionTrackRecord().then(setTr).catch(() => { /* sin historial */ }) }, [])
  if (!tr || tr.resolved === 0) {
    return (
      <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-3 text-[11px] text-slate-400">
        <span className="text-slate-300 font-medium">Registro automático:</span> cada predicción direccional se guarda
        y se verifica cuando transcurre el horizonte. Vuelve para ver el acierto real
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
        Qué señales empujan la probabilidad de subida de ESTA vela (verde) y cuáles la frenan (rojo).
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

// ── Héroe: predicción + veredicto en un solo bloque ──────────────
function PredictionHero({ data }: { data: PredictionResult }) {
  const isNeutral = data.prediction === 'NEUTRAL'
  const isBullish = data.prediction === 'ALCISTA'
  const v = VERDICT_STYLE[data.verdict ?? 'NO_EDGE']
  const frame = isNeutral
    ? 'bg-slate-700/20 border-slate-600/50'
    : isBullish ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30'
  const headline = isNeutral ? '→ NEUTRAL' : isBullish ? '▲ ALCISTA' : '▼ BAJISTA'
  const headlineColor = isNeutral ? 'text-slate-300' : isBullish ? 'text-green-400' : 'text-red-400'

  return (
    <div className={`rounded-xl border p-5 ${frame}`}>
      <div className="flex items-center gap-5 flex-wrap">
        <ConfidenceRing value={data.confidence} neutral={isNeutral} />
        <div className="flex-1 min-w-[220px]">
          <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">
            Predicción — {data.horizon} velas adelante
          </p>
          <p className={`text-3xl font-bold ${headlineColor}`}>{headline}</p>
          {isNeutral ? (
            <p className="text-[11px] text-slate-400 mt-1 max-w-md">
              La probabilidad calibrada ({((data.prob_up ?? 0.5) * 100).toFixed(1)}% de subida) está a menos de
              {' '}{((data.neutral_band ?? 0.05) * 100).toFixed(0)} puntos del 50%: el modelo no ve dirección clara
              y no cuenta esta predicción en el historial.
            </p>
          ) : (
            <div className="flex flex-wrap gap-4 mt-2">
              <div>
                <p className="text-[10px] text-slate-500 uppercase">
                  Confianza {data.calibrated && <span className="text-emerald-400 normal-case">· calibrada</span>}
                </p>
                <p className="text-sm font-bold font-mono text-white">{(data.confidence * 100).toFixed(1)}%</p>
              </div>
              <div>
                <p className="text-[10px] text-slate-500 uppercase">Prob. de subida</p>
                <p className="text-sm font-bold font-mono text-white">{((data.prob_up ?? 0) * 100).toFixed(1)}%</p>
              </div>
              {data.oos_accuracy !== undefined && (
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Acierto validado (OOS)</p>
                  <p className="text-sm font-bold font-mono text-white">{(data.oos_accuracy * 100).toFixed(1)}%</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Veredicto de fiabilidad integrado: la primera pregunta es «¿me fío?» */}
      {data.verdict && (
        <div className={`mt-4 rounded-lg border p-3 ${v.chip}`}>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-bold uppercase tracking-wide">{v.label}</span>
            {data.n_oos !== undefined && (
              <span className="text-[11px] opacity-80">· validado sobre {data.n_oos} muestras fuera de muestra</span>
            )}
          </div>
          {data.verdict_text && <p className="text-[11px] mt-1 text-slate-300">{data.verdict_text}</p>}
        </div>
      )}

      <p className="text-[10px] text-slate-500 mt-3">
        ⚠ {data.disclaimer ?? 'Predicción estadística evaluada fuera de muestra. No constituye consejo financiero.'}
      </p>
    </div>
  )
}

// ── Fiabilidad del modelo (métricas + variables) ──────────────────
function ReliabilitySection({ data }: { data: PredictionResult }) {
  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <MetricCard label="Edge sobre el azar" value={`${(data.edge ?? 0) >= 0 ? '+' : ''}${((data.edge ?? 0) * 100).toFixed(1)}%`}
          color={(data.edge ?? 0) >= 0.04 ? 'text-green-400' : (data.edge ?? 0) >= 0.01 ? 'text-yellow-400' : 'text-red-400'} />
        <MetricCard label="Línea base (mayoría)" value={`${((data.baseline_accuracy ?? 0) * 100).toFixed(1)}%`} color="text-slate-300" />
        <MetricCard label="AUC" value={data.auc != null ? data.auc.toFixed(3) : '—'}
          color={(data.auc ?? 0) >= 0.55 ? 'text-green-400' : 'text-slate-300'} />
        <MetricCard label="Brier (calibración)" value={data.brier_score != null ? data.brier_score.toFixed(3) : '—'} color="text-slate-300" />
      </div>
      <p className="text-[10px] text-slate-500">
        El <span className="text-slate-300">edge</span> es lo único que importa: cuánto acierta el modelo POR ENCIMA
        de predecir siempre la clase mayoritaria. La precisión OOS ({((data.oos_accuracy ?? 0) * 100).toFixed(1)}%
        {data.cv_std !== undefined && <> ± {(data.cv_std * 100).toFixed(1)}%</>}) sin la línea base
        ({((data.baseline_accuracy ?? 0) * 100).toFixed(1)}%) engaña. El Brier mide si la confianza mostrada es
        una probabilidad realista (0 = perfecta).
      </p>
      {data.model && (
        <p className="text-[10px] text-slate-500">
          Modelo: <span className="text-slate-300 font-mono">{data.model}</span>
          {data.elapsed_ms != null && <span className="ml-1">· entrenado y validado en {(data.elapsed_ms / 1000).toFixed(1)}s</span>}
          {data.n_train != null && <span className="ml-1">· {data.n_train} velas de entrenamiento</span>}
        </p>
      )}
      {data.features_importance && data.features_importance.length > 0 && (
        <div>
          <p className="text-xs text-slate-400 uppercase mb-2">Variables más influyentes (global)</p>
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
    </>
  )
}

export default function PredictTab({ data }: { data: PredictionResult | null }) {
  if (!data) {
    return (
      <EmptyState
        icon={
          <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        }
        title="Predicción ML de dirección de precio"
        description="Ensemble (Random Forest + Gradient Boosting + Regresión logística) validado walk-forward con probabilidad calibrada. Predice si el precio subirá o bajará en las próximas N velas — o dice NEUTRAL si no ve dirección clara."
      />
    )
  }

  if (data.prediction === 'INSUFFICIENT_DATA') {
    return <div className="text-yellow-400 text-sm">{data.message}</div>
  }

  const edge = data.edge ?? 0
  const edgeBadge = (
    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${edge >= 0.04 ? 'bg-green-500/15 text-green-300' : edge >= 0.01 ? 'bg-yellow-500/15 text-yellow-300' : 'bg-red-500/15 text-red-300'}`}>
      edge {edge >= 0 ? '+' : ''}{(edge * 100).toFixed(1)}%
    </span>
  )

  return (
    <div className="space-y-4">
      {/* 1 · Qué dice el modelo y cuánto fiarse (todo en un bloque) */}
      <PredictionHero data={data} />

      {/* 2 · Por qué lo dice (explicación local de esta vela) */}
      <PredictionDrivers data={data} />

      {/* 3 · Detalle plegable: fiabilidad, seguimiento en vivo y funcionamiento */}
      <Section
        title="Fiabilidad del modelo"
        subtitle="Métricas fuera de muestra, calibración y variables influyentes"
        badge={edgeBadge}
      >
        <ReliabilitySection data={data} />
      </Section>

      <Section
        title="Seguimiento en vivo"
        subtitle="Aciertos reales verificados a posteriori y monitorización de drift"
      >
        <PredictionTrackRecordPanel />
        <PredictionMonitoringPanel />
      </Section>

      <Section
        title="¿Cómo funciona este modelo?"
        subtitle="Algoritmo, features, validación walk-forward y calibración"
      >
        <div className="space-y-2 text-[11px] text-slate-400 leading-relaxed">
          <p><span className="text-slate-300 font-medium">Algoritmo:</span> ensemble por votación blanda de Random Forest, Gradient Boosting y regresión logística. Combina familias de modelos con sesgos distintos para reducir overfitting.</p>
          <p><span className="text-slate-300 font-medium">Target:</span> ¿sube o baja el precio en las próximas {data.horizon} velas? Si la probabilidad calibrada queda entre el 45% y el 55%, la respuesta honesta es NEUTRAL y no cuenta en el historial.</p>
          <p><span className="text-slate-300 font-medium">Validación walk-forward:</span> se entrena en el pasado y se valida en el futuro (TimeSeriesSplit), nunca al revés. El edge es la ventaja sobre predecir siempre la clase mayoritaria: si es ~0, no hay señal real aunque la precisión parezca alta.</p>
          <p><span className="text-slate-300 font-medium">Probabilidad calibrada:</span> la confianza pasa por una calibración de Platt aprendida SOLO con datos fuera de muestra, para que un 70% signifique de verdad ~70% de acierto. El Brier score mide esa calidad.</p>
          <p><span className="text-slate-300 font-medium">Explicabilidad:</span> el panel «Por qué esta predicción» mide, por oclusión, cuánto aporta cada señal a la decisión de ESTA vela; «Variables más influyentes» es el peso global de cada señal en el modelo.</p>
          <p><span className="text-slate-300 font-medium">Mejora continua:</span> cada predicción direccional se registra y se verifica al vencer su horizonte; la monitorización de drift avisa si el acierto en vivo cae por debajo de lo prometido fuera de muestra.</p>
        </div>
      </Section>
    </div>
  )
}
