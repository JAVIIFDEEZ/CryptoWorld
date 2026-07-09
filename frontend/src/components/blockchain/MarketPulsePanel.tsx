/**
 * components/blockchain/MarketPulsePanel.tsx — Pulso on-chain de mercado.
 *
 * Vista institucional (estilo terminal): flujo neto a/desde exchanges agregado
 * de TODAS las redes escaneadas, con veredicto de presión, desglose por cadena,
 * exchange y activo, y una barra de flujo neto por tramo. Responde la pregunta
 * institucional: ¿dónde está entrando y saliendo el dinero grande AHORA?
 */

import { useEffect, useState } from 'react'
import { blockchainService, type OnChainPulse } from '@/services/blockchainService'

function usdCompact(n: number | undefined): string {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const sign = n < 0 ? '-' : ''
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`
  return `${sign}$${abs.toFixed(0)}`
}

const VERDICT: Record<string, { label: string; color: string }> = {
  ACUMULACION: { label: 'ACUMULACIÓN', color: 'text-emerald-400' },
  PRESION_VENDEDORA: { label: 'PRESIÓN VENDEDORA', color: 'text-red-400' },
  EQUILIBRIO: { label: 'EQUILIBRIO', color: 'text-slate-300' },
  INSUFICIENTE: { label: 'MUESTRA INSUFICIENTE', color: 'text-amber-300' },
}

const HOURS = [24, 72, 168]

export default function MarketPulsePanel() {
  const [pulse, setPulse] = useState<OnChainPulse | null>(null)
  const [hours, setHours] = useState(24)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    blockchainService.getMarketPulse(hours)
      .then((p) => { if (!cancelled) setPulse(p) })
      .catch(() => { /* sin pulso */ })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [hours])

  const v = VERDICT[pulse?.verdict ?? 'INSUFICIENTE'] ?? VERDICT.INSUFICIENTE
  const acc = (pulse?.net_flow_usd ?? 0) >= 0

  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden mb-6">
      <div className="px-5 pt-4 pb-1 flex items-center gap-2 flex-wrap">
        <span>📡</span>
        <h2 className="text-lg font-semibold text-white">Pulso on-chain de mercado</h2>
        <span className="text-[10px] text-slate-500">flujo neto a/desde exchanges · todas las redes</span>
        <div className="ml-auto flex gap-1">
          {HOURS.map((h) => (
            <button
              key={h}
              onClick={() => setHours(h)}
              className={`text-[10px] px-2 py-1 rounded-lg border transition-colors ${
                hours === h ? 'bg-blue-600/20 text-blue-300 border-blue-500/30' : 'bg-slate-800 text-slate-500 border-slate-700'
              }`}
            >
              {h === 24 ? '24h' : h === 72 ? '3d' : '7d'}
            </button>
          ))}
        </div>
      </div>

      <div className="p-5 pt-3">
        {loading && <p className="text-sm text-slate-500 py-6 text-center">Agregando el flujo on-chain…</p>}

        {!loading && pulse?.status !== 'OK' && (
          <p className="text-sm text-amber-300/80 py-4">
            {pulse?.note ?? 'El escáner aún no ha acumulado movimientos suficientes en esta ventana.'}
          </p>
        )}

        {!loading && pulse?.status === 'OK' && (
          <div className="space-y-4">
            {/* Veredicto + KPIs */}
            <div className={`rounded-xl border p-4 ${acc ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-red-500/5 border-red-500/20'}`}>
              <div className="flex items-center gap-4 flex-wrap">
                <p className={`text-2xl font-bold ${v.color}`}>{v.label}</p>
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Flujo neto</p>
                  <p className={`text-lg font-bold font-mono ${acc ? 'text-emerald-400' : 'text-red-400'}`}>
                    {acc ? '+' : ''}{usdCompact(pulse.net_flow_usd)}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Retiradas / Depósitos</p>
                  <p className="text-sm font-bold font-mono">
                    <span className="text-emerald-400">{usdCompact(pulse.outflow_usd)}</span>
                    <span className="text-slate-600"> / </span>
                    <span className="text-red-400">{usdCompact(pulse.inflow_usd)}</span>
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 uppercase">Movimientos</p>
                  <p className="text-sm font-bold font-mono text-white">{pulse.movements} · {pulse.classified} clasif.</p>
                </div>
              </div>
              {pulse.verdict_text && <p className="text-[11px] text-slate-400 mt-2">{pulse.verdict_text}</p>}
            </div>

            {/* Serie temporal de flujo neto (barras +/-) */}
            {(pulse.series?.length ?? 0) > 1 && <NetFlowBars series={pulse.series!} />}

            {/* Desgloses en tres columnas estilo terminal */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <FlowTable title="Por cadena" rows={pulse.chains ?? []} keyName="chain" />
              <FlowTable title="Por exchange" rows={pulse.exchanges ?? []} keyName="exchange" />
              <FlowTable title="Por activo" rows={pulse.symbols ?? []} keyName="symbol" />
            </div>

            {pulse.note && <p className="text-[10px] text-slate-600">{pulse.note}</p>}
          </div>
        )}
      </div>
    </div>
  )
}

function NetFlowBars({ series }: Readonly<{ series: NonNullable<OnChainPulse['series']> }>) {
  const max = Math.max(...series.map((b) => Math.abs(b.net_flow_usd)), 1)
  return (
    <div>
      <p className="text-[10px] uppercase text-slate-500 mb-2">Flujo neto por tramo (verde = acumulación)</p>
      <div className="flex items-end gap-0.5 h-16">
        {series.map((b) => {
          const h = (Math.abs(b.net_flow_usd) / max) * 100
          const pos = b.net_flow_usd >= 0
          return (
            <div key={b.t} className="flex-1 flex flex-col justify-end h-full" title={usdCompact(b.net_flow_usd)}>
              <div
                className={pos ? 'bg-emerald-500/70' : 'bg-red-500/70'}
                style={{ height: `${h}%`, minHeight: h > 0 ? '2px' : '0' }}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}

function FlowTable({ title, rows, keyName }: Readonly<{
  title: string
  rows: { net_flow_usd: number; movements: number; [k: string]: string | number }[]
  keyName: string
}>) {
  return (
    <div className="bg-slate-900/40 rounded-lg border border-slate-700/60 p-3">
      <p className="text-[10px] uppercase text-slate-500 mb-2">{title}</p>
      {rows.length === 0 ? (
        <p className="text-[10px] text-slate-600">Sin datos.</p>
      ) : (
        <div className="space-y-1">
          {rows.map((r) => {
            const acc = r.net_flow_usd >= 0
            return (
              <div key={String(r[keyName])} className="flex items-center gap-2 text-[11px]">
                <span className="flex-1 truncate text-slate-300 font-mono">{String(r[keyName])}</span>
                <span className="text-[9px] text-slate-600">{r.movements}</span>
                <span className={`w-16 text-right font-mono ${acc ? 'text-emerald-400' : 'text-red-400'}`}>
                  {acc ? '+' : ''}{usdCompact(r.net_flow_usd)}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
