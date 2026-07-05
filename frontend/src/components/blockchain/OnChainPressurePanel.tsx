/**
 * components/blockchain/OnChainPressurePanel.tsx — Presión on-chain (edge).
 *
 * Indicador de flujo hacia/desde exchanges construido sobre el histórico propio
 * de grandes movimientos: depósitos en exchanges = presión vendedora potencial;
 * retiradas = acumulación. Muestra el veredicto, la puntuación en [-1, +1], los
 * flujos y la serie temporal por tramos (barras entrada vs salida).
 */

import { useEffect, useState } from 'react'
import {
  Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import {
  blockchainService,
  type OnChainPressure,
} from '@/services/blockchainService'

const WINDOWS = [
  { hours: 24, label: '24h' },
  { hours: 72, label: '3d' },
  { hours: 168, label: '7d' },
]

const VERDICT_STYLE: Record<OnChainPressure['verdict'], { chip: string; label: string }> = {
  ACUMULACION: { chip: 'bg-green-500/15 text-green-300 border-green-500/30', label: '▲ Acumulación' },
  PRESION_VENDEDORA: { chip: 'bg-red-500/15 text-red-300 border-red-500/30', label: '▼ Presión vendedora' },
  EQUILIBRIO: { chip: 'bg-slate-700/40 text-slate-300 border-slate-600/40', label: '— Equilibrio' },
  INSUFICIENTE: { chip: 'bg-amber-500/15 text-amber-300 border-amber-500/40', label: '○ Muestra insuficiente' },
}

function fmtUsd(n: number): string {
  const a = Math.abs(n)
  if (a >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (a >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  if (a >= 1e3) return `$${(n / 1e3).toFixed(1)}K`
  return `$${n.toFixed(0)}`
}

function PressureBar({ value }: { value: number }) {
  const pct = ((value + 1) / 2) * 100
  return (
    <div className="space-y-1">
      <div className="relative h-3 rounded-full overflow-hidden flex">
        <div className="w-1/2 bg-gradient-to-r from-red-500/60 to-slate-600/40" />
        <div className="w-1/2 bg-gradient-to-r from-slate-600/40 to-green-500/60" />
        <div
          className="absolute top-0 bottom-0 w-1.5 bg-white rounded-full shadow transition-all"
          style={{ left: `calc(${Math.min(Math.max(pct, 1), 99)}% - 3px)` }}
        />
      </div>
      <div className="flex justify-between text-[9px] text-slate-500">
        <span className="text-red-400">−1 depósitos (venta)</span>
        <span>0</span>
        <span className="text-green-400">retiradas (acumulación) +1</span>
      </div>
    </div>
  )
}

export default function OnChainPressurePanel({ chain = 'ethereum' }: Readonly<{ chain?: string }>) {
  const [hours, setHours] = useState(24)
  const [data, setData] = useState<OnChainPressure | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    blockchainService.getOnChainPressure(chain, hours)
      .then((d) => setData(d.error ? null : d))
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [chain, hours])

  const v = data ? VERDICT_STYLE[data.verdict] : VERDICT_STYLE.INSUFICIENTE
  const chart = (data?.series ?? []).map((b) => ({
    t: new Date(b.start_ms).toLocaleString(undefined, { day: '2-digit', hour: '2-digit' }),
    entrada: Math.round(b.inflow_usd),
    salida: Math.round(b.outflow_usd),
  }))

  return (
    <div className="bg-slate-800 rounded-xl p-6 border border-slate-700 mb-6">
      <div className="flex items-center flex-wrap gap-2 mb-1">
        <span className="text-emerald-400">⚖</span>
        <h2 className="text-lg font-bold text-white">Presión on-chain (flujo de exchanges)</h2>
        <div className="ml-auto flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w.hours}
              onClick={() => setHours(w.hours)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                hours === w.hours ? 'bg-emerald-600 text-white' : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-700'
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </div>
      <p className="text-slate-400 text-xs mb-4">
        Depósito en exchange = venta potencial · retirada = acumulación · histórico propio del escáner (cada 15 min)
      </p>

      {loading && <p className="text-slate-500 text-sm">Cargando…</p>}

      {!loading && data && (
        <div className="space-y-4">
          {/* Veredicto + puntuación */}
          <div className={`rounded-xl border p-4 ${v.chip}`}>
            <div className="flex items-center justify-between flex-wrap gap-2">
              <p className="text-sm font-bold uppercase tracking-wide">{v.label}</p>
              <span className="text-xl font-bold font-mono">
                {data.pressure > 0 ? '+' : ''}{data.pressure.toFixed(2)}
              </span>
            </div>
            <p className="text-[11px] mt-1.5 text-slate-300">{data.verdict_text}</p>
          </div>

          <PressureBar value={data.pressure} />

          {/* Flujos */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-slate-900/40 rounded-lg border border-slate-700/50 p-3">
              <p className="text-[10px] text-slate-500 uppercase">→ A exchanges</p>
              <p className="text-sm font-bold font-mono text-red-300">{fmtUsd(data.inflow_usd)}</p>
            </div>
            <div className="bg-slate-900/40 rounded-lg border border-slate-700/50 p-3">
              <p className="text-[10px] text-slate-500 uppercase">← De exchanges</p>
              <p className="text-sm font-bold font-mono text-green-300">{fmtUsd(data.outflow_usd)}</p>
            </div>
            <div className="bg-slate-900/40 rounded-lg border border-slate-700/50 p-3">
              <p className="text-[10px] text-slate-500 uppercase">Neto</p>
              <p className={`text-sm font-bold font-mono ${data.net_flow_usd > 0 ? 'text-red-300' : 'text-green-300'}`}>
                {fmtUsd(data.net_flow_usd)}
              </p>
            </div>
          </div>

          {/* Serie temporal entrada vs salida */}
          {chart.length >= 2 && (
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={chart} margin={{ top: 4, right: 6, left: -8, bottom: 0 }}>
                <XAxis dataKey="t" tick={{ fill: '#64748b', fontSize: 9 }} axisLine={{ stroke: '#334155' }} tickLine={false} minTickGap={20} />
                <YAxis tick={{ fill: '#64748b', fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => fmtUsd(Number(v))} width={58} />
                <ReferenceLine y={0} stroke="#475569" />
                <Tooltip
                  contentStyle={{ background: 'rgb(var(--c-slate-900))', border: '1px solid rgb(var(--c-slate-700))', borderRadius: 8, fontSize: 11 }}
                  formatter={(val, name) => [fmtUsd(Number(val)), name === 'entrada' ? 'a exchanges' : 'de exchanges']}
                />
                <Bar dataKey="entrada" fill="#ef4444" fillOpacity={0.75} radius={[2, 2, 0, 0]} />
                <Bar dataKey="salida" fill="#22c55e" fillOpacity={0.75} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}

          <p className="text-[10px] text-slate-600">
            {data.total_movements} movimientos en la ventana ({data.classified_count} con dirección conocida
            {data.unknown_count > 0 ? `, ${data.unknown_count} sin etiqueta` : ''}). {data.note}
          </p>
        </div>
      )}

      {!loading && !data && (
        <p className="text-slate-500 text-sm">No se pudo cargar el indicador de presión.</p>
      )}
    </div>
  )
}
