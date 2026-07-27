/**
 * DataHealthPanel.tsx — Salud del almacén histórico OHLCV (calidad de datos).
 *
 * Observabilidad de la fiabilidad de los datos que alimentan riesgo, backtests
 * y la terminal: completitud, frescura y huecos por serie + nota global.
 */

import { useEffect, useState } from 'react'
import { dataHealthService, type DataHealth, type SeriesStatus } from '@/services/dataHealthService'

const STATUS_STYLE: Record<SeriesStatus, string> = {
  SANO: 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300',
  CON_HUECOS: 'bg-amber-500/15 border-amber-500/40 text-amber-300',
  DESACTUALIZADO: 'bg-red-500/15 border-red-500/40 text-red-300',
  VACIO: 'bg-slate-600/20 border-slate-500/40 text-slate-400',
}

const STATUS_LABEL: Record<SeriesStatus, string> = {
  SANO: 'Sano', CON_HUECOS: 'Con huecos', DESACTUALIZADO: 'Desactualizado', VACIO: 'Vacío',
}

const GRADE_STYLE: Record<string, string> = {
  EXCELENTE: 'text-emerald-300', ACEPTABLE: 'text-amber-300',
  DEFICIENTE: 'text-red-300', SIN_DATOS: 'text-slate-400',
}

export default function DataHealthPanel() {
  const [data, setData] = useState<DataHealth | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    dataHealthService.get()
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { /* best-effort */ })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return (
    <section className="bg-slate-800 rounded-xl p-6 border border-slate-700">
      <h2 className="text-lg font-semibold text-white mb-1">Salud del almacén de datos</h2>
      <p className="text-xs text-slate-500 mb-4">
        Fiabilidad del histórico OHLCV propio — completitud, frescura y huecos
        por serie. Es la base de lo que se deriva del histórico (riesgo,
        backtests, terminal cuantitativa).
      </p>

      {loading && <p className="text-sm text-slate-500">Cargando…</p>}

      {!loading && data?.status === 'EMPTY' && (
        <p className="text-sm text-slate-500">El almacén aún no tiene datos.</p>
      )}

      {!loading && data?.status === 'OK' && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center mb-4">
            <div>
              <p className="text-[10px] text-slate-500 uppercase">Grado</p>
              <p className={`text-lg font-bold ${GRADE_STYLE[data.summary.grade]}`}>{data.summary.grade}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase">Series sanas</p>
              <p className="text-lg font-bold font-mono text-white">{data.summary.healthy_pct}%</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase">Con huecos</p>
              <p className="text-lg font-bold font-mono text-white">{data.summary.with_gaps}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase">Velas</p>
              <p className="text-lg font-bold font-mono text-white">{data.summary.total_candles.toLocaleString()}</p>
            </div>
          </div>

          <div className="space-y-1 max-h-64 overflow-y-auto">
            {data.series.map((s) => (
              <div key={`${s.symbol}-${s.interval}`} className="flex items-center justify-between text-xs gap-2">
                <span className="font-mono text-slate-300 w-24 shrink-0">{s.symbol} · {s.interval}</span>
                <span className="text-slate-500 flex-1">
                  {s.candles.toLocaleString()} velas · {s.completeness_pct}%
                  {s.missing_candles > 0 ? ` · faltan ${s.missing_candles}` : ''}
                  {s.freshness_hours != null ? ` · hace ${s.freshness_hours}h` : ''}
                </span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border shrink-0 ${STATUS_STYLE[s.status]}`}>
                  {STATUS_LABEL[s.status]}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
