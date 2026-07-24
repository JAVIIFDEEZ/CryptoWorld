/**
 * QuantAlertsPanel.tsx — Panel de alertas cuantitativas (motor multi-métrica).
 *
 * Constructor de reglas sobre cualquier métrica del sistema (técnica,
 * confluencia 360°, on-chain, riesgo de cartera) con disparo por flanco y
 * cooldown, lista de reglas activas con toggle/borrado, y feed de disparos
 * recientes. Encapsulado: se monta en la página de Alertas junto a las de
 * precio.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  quantAlertsService, OPERATOR_LABELS,
  type QuantAlert, type QuantMetric, type QuantFiring, type QuantOperator,
} from '../../services/quantAlertsService'

const TIMEFRAMES = ['1h', '4h', '1d'] as const

const CATEGORY_LABELS: Record<string, string> = {
  tecnica: 'Técnica', precio: 'Precio', confluencia: 'Confluencia 360°',
  onchain: 'On-chain', riesgo: 'Riesgo de cartera',
}

export default function QuantAlertsPanel() {
  const [metrics, setMetrics] = useState<QuantMetric[]>([])
  const [alerts, setAlerts] = useState<QuantAlert[]>([])
  const [firings, setFirings] = useState<QuantFiring[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Formulario
  const [metricKey, setMetricKey] = useState('')
  const [operator, setOperator] = useState<QuantOperator>('gt')
  const [threshold, setThreshold] = useState('')
  const [assetSymbol, setAssetSymbol] = useState('')
  const [timeframe, setTimeframe] = useState<string>('1h')
  const [cooldown, setCooldown] = useState('60')
  const [submitting, setSubmitting] = useState(false)

  const selectedMetric = useMemo(
    () => metrics.find((m) => m.key === metricKey),
    [metrics, metricKey],
  )
  const needsAsset = selectedMetric?.scope === 'asset'
  const isTechnical = selectedMetric?.category === 'tecnica'

  const reload = useCallback(async () => {
    try {
      const [{ alerts: list, metrics: cat }, fires] = await Promise.all([
        quantAlertsService.list(true),
        quantAlertsService.firings(15),
      ])
      setAlerts(list)
      if (cat) setMetrics(cat)
      setFirings(fires)
      setError(null)
    } catch {
      setError('No se pudieron cargar las alertas cuantitativas.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { reload() }, [reload])

  const grouped = useMemo(() => {
    const g: Record<string, QuantMetric[]> = {}
    for (const m of metrics) (g[m.category] ||= []).push(m)
    return g
  }, [metrics])

  const canSubmit = metricKey !== '' && threshold !== '' &&
    (!needsAsset || assetSymbol.trim() !== '')

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setSubmitting(true)
    setError(null)
    try {
      await quantAlertsService.create({
        metric: metricKey,
        operator,
        threshold: Number(threshold),
        asset_symbol: needsAsset ? assetSymbol.trim().toUpperCase() : undefined,
        timeframe: isTechnical ? timeframe : undefined,
        cooldown_minutes: Number(cooldown) || 60,
      })
      setThreshold(''); setAssetSymbol('')
      await reload()
    } catch (err) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg || 'No se pudo crear la alerta.')
    } finally {
      setSubmitting(false)
    }
  }

  async function toggle(a: QuantAlert) {
    await quantAlertsService.update(a.id, { is_active: !a.is_active })
    reload()
  }
  async function remove(id: number) {
    await quantAlertsService.remove(id)
    reload()
  }

  if (loading) {
    return <div className="text-sm text-slate-500 py-6">Cargando alertas cuantitativas…</div>
  }

  return (
    <section className="space-y-5">
      <header>
        <h2 className="text-lg font-bold text-white">Alertas cuantitativas</h2>
        <p className="text-sm text-slate-400">
          Reglas sobre cualquier métrica — técnica, confluencia 360°, on-chain o
          riesgo de cartera. Disparo por flanco con cooldown: se re-arman solas,
          sin spam.
        </p>
      </header>

      {error && (
        <div className="text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* Constructor de reglas */}
      <form onSubmit={submit} className="bg-slate-800/60 border border-slate-700 rounded-xl p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-xs text-slate-400 space-y-1">
            <span>Métrica</span>
            <select
              value={metricKey}
              onChange={(e) => setMetricKey(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-white"
            >
              <option value="">Elige una métrica…</option>
              {Object.entries(grouped).map(([cat, ms]) => (
                <optgroup key={cat} label={CATEGORY_LABELS[cat] ?? cat}>
                  {ms.map((m) => (
                    <option key={m.key} value={m.key}>{m.label}{m.unit ? ` (${m.unit})` : ''}</option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>

          <label className="text-xs text-slate-400 space-y-1">
            <span>Condición</span>
            <select
              value={operator}
              onChange={(e) => setOperator(e.target.value as QuantOperator)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-white"
            >
              {(Object.keys(OPERATOR_LABELS) as QuantOperator[]).map((op) => (
                <option key={op} value={op}>{OPERATOR_LABELS[op]}</option>
              ))}
            </select>
          </label>

          {needsAsset && (
            <label className="text-xs text-slate-400 space-y-1">
              <span>Activo</span>
              <input
                value={assetSymbol}
                onChange={(e) => setAssetSymbol(e.target.value.toUpperCase())}
                placeholder="BTC"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-white uppercase"
              />
            </label>
          )}

          {isTechnical && (
            <label className="text-xs text-slate-400 space-y-1">
              <span>Marco temporal</span>
              <select
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-white"
              >
                {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
              </select>
            </label>
          )}

          <label className="text-xs text-slate-400 space-y-1">
            <span>Umbral{selectedMetric?.unit ? ` (${selectedMetric.unit})` : ''}</span>
            <input
              type="number" step="any"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              placeholder="70"
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-white"
            />
          </label>

          <label className="text-xs text-slate-400 space-y-1">
            <span>Cooldown (min)</span>
            <input
              type="number" min="0"
              value={cooldown}
              onChange={(e) => setCooldown(e.target.value)}
              className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-sm text-white"
            />
          </label>
        </div>

        {selectedMetric?.hint && (
          <p className="text-[11px] text-slate-500">{selectedMetric.hint}</p>
        )}

        <button
          type="submit"
          disabled={!canSubmit || submitting}
          className="text-sm px-4 py-1.5 rounded-lg bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors font-medium"
        >
          {submitting ? 'Creando…' : 'Crear alerta'}
        </button>
      </form>

      {/* Reglas activas */}
      <div className="space-y-2">
        <h3 className="text-sm font-semibold text-slate-300">Reglas ({alerts.length})</h3>
        {alerts.length === 0 && (
          <p className="text-sm text-slate-500">Aún no tienes alertas cuantitativas.</p>
        )}
        {alerts.map((a) => (
          <div key={a.id} className="flex items-center justify-between bg-slate-800/40 border border-slate-700 rounded-lg px-3 py-2">
            <div className="min-w-0">
              <div className="text-sm text-white truncate">
                <span className="font-mono text-slate-300">{a.asset_symbol ?? 'CARTERA'}</span>
                {' · '}{a.metric_label}
                {a.scope === 'asset' && a.metric.match(/rsi|adx|stoch|macd|vol|atr|range/) ? ` (${a.timeframe})` : ''}
                {' '}{OPERATOR_LABELS[a.operator].match(/[≥<]|↑|↓|alza|baja/)?.[0] ?? a.operator}{' '}
                <span className="font-mono">{a.threshold}{a.metric_unit}</span>
              </div>
              <div className="text-[11px] text-slate-500">
                {a.last_value != null ? `último: ${a.last_value}${a.metric_unit}` : 'sin lectura aún'}
                {a.last_fired_at ? ` · disparada ${new Date(a.last_fired_at).toLocaleString()}` : ''}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => toggle(a)}
                className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                  a.is_active
                    ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-300'
                    : 'bg-slate-700/40 border-slate-600 text-slate-400'
                }`}
              >
                {a.is_active ? 'Activa' : 'Pausada'}
              </button>
              <button
                onClick={() => remove(a.id)}
                className="text-[11px] px-2 py-0.5 rounded-full text-red-300 hover:bg-red-500/10 transition-colors"
              >
                Borrar
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Disparos recientes */}
      {firings.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-slate-300">Disparos recientes</h3>
          {firings.map((f) => (
            <div key={f.id} className="text-sm bg-slate-800/30 border border-slate-700/60 rounded-lg px-3 py-1.5">
              <span className="font-mono text-slate-400 text-[11px]">{f.asset_symbol ?? 'CARTERA'}</span>
              {' '}<span className="text-slate-200">{f.message}</span>
              <span className="text-[11px] text-slate-500 ml-1">· {new Date(f.fired_at).toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
