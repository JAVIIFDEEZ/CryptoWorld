/**
 * ExecutionAuditPanel.tsx — Rastro de auditoría de la ejecución real.
 *
 * Registro de cumplimiento de cada intento de orden real (enviada / fallida /
 * bloqueada) con su motivo, más un resumen. No pinta nada si aún no hay
 * intentos registrados.
 */

import { useCallback, useEffect, useState } from 'react'
import { tradingService, type ExecutionAudit } from '@/services/tradingService'

const STATUS_STYLE: Record<string, string> = {
  sent: 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300',
  failed: 'bg-red-500/15 border-red-500/40 text-red-300',
  blocked: 'bg-amber-500/15 border-amber-500/40 text-amber-300',
}
const STATUS_LABEL: Record<string, string> = { sent: 'Enviada', failed: 'Fallida', blocked: 'Bloqueada' }
const FILTERS = ['', 'sent', 'failed', 'blocked'] as const

export default function ExecutionAuditPanel() {
  const [data, setData] = useState<ExecutionAudit | null>(null)
  const [filter, setFilter] = useState<string>('')
  const [loading, setLoading] = useState(true)

  const load = useCallback((status: string) => {
    setLoading(true)
    tradingService.getAudit({ status: status || undefined, limit: 50 })
      .then(setData)
      .catch(() => { /* best-effort */ })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load(filter) }, [filter, load])

  if (!loading && data?.status === 'EMPTY') return null

  const s = data?.summary

  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-white mb-1">Auditoría de ejecución real</h3>
      <p className="text-[11px] text-slate-500 mb-3">
        Registro de cumplimiento de cada intento de orden real y su motivo.
      </p>

      {s && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center mb-4">
          <div>
            <p className="text-[10px] text-slate-500 uppercase">Intentos</p>
            <p className="text-lg font-bold font-mono text-white">{s.total_attempts}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase">Enviadas</p>
            <p className="text-lg font-bold font-mono text-emerald-300">{s.sent}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase">Bloqueadas</p>
            <p className="text-lg font-bold font-mono text-amber-300">{s.blocked}</p>
          </div>
          <div>
            <p className="text-[10px] text-slate-500 uppercase">Fallidas</p>
            <p className="text-lg font-bold font-mono text-red-300">{s.failed}</p>
          </div>
        </div>
      )}

      {/* Filtro por estado */}
      <div className="flex gap-1.5 mb-3">
        {FILTERS.map((f) => (
          <button
            key={f || 'all'}
            onClick={() => setFilter(f)}
            className={`text-[11px] px-2.5 py-0.5 rounded-full border transition-colors ${
              filter === f ? 'bg-blue-600/20 border-blue-500/40 text-blue-300'
                           : 'border-slate-700 text-slate-400 hover:bg-slate-700/40'
            }`}
          >
            {f ? STATUS_LABEL[f] : 'Todas'}
          </button>
        ))}
      </div>

      {/* Registro cronológico */}
      <div className="space-y-1 max-h-72 overflow-y-auto">
        {(data?.entries ?? []).map((e) => (
          <div key={e.id} className="flex items-center gap-2 text-xs bg-slate-800/40 rounded px-2 py-1">
            <span className={`text-[10px] px-1.5 py-0.5 rounded border shrink-0 ${STATUS_STYLE[e.status]}`}>
              {STATUS_LABEL[e.status]}
            </span>
            <span className="font-mono text-slate-300 shrink-0">{e.side === 'buy' ? '▲' : '▼'} {e.symbol}</span>
            <span className="text-slate-500 flex-1 truncate">
              {e.fill_price != null ? `fill ${e.fill_price}` : ''}{e.error ? ` · ${e.error}` : ''}
              {e.is_testnet ? ' · testnet' : ''}
            </span>
            <span className="text-[10px] text-slate-600 shrink-0">{new Date(e.created_at).toLocaleString()}</span>
          </div>
        ))}
        {!loading && (data?.entries?.length ?? 0) === 0 && (
          <p className="text-xs text-slate-500 py-2">Sin órdenes con ese estado.</p>
        )}
      </div>
    </div>
  )
}
