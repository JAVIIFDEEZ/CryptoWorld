/**
 * components/PortfolioInsights.tsx — Visualizaciones del portfolio.
 *
 * Dos gráficos construidos con datos reales (sin estimaciones sintéticas):
 *   1. Donut de distribución de exposición sobre las posiciones ABIERTAS
 *      (valor de mercado = cantidad abierta × precio actual).
 *   2. Curva de PnL realizado acumulado a partir de las posiciones CERRADAS,
 *      ordenadas por fecha de cierre.
 *
 * Si no hay datos suficientes para un gráfico, su tarjeta muestra un
 * estado vacío explicativo en lugar de ocultarse, para mantener el layout.
 */

import { useMemo } from 'react'
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
} from 'recharts'
import type { Position } from '../services/portfolioService'
import AnimatedNumber from './ui/AnimatedNumber'

// Paleta cualitativa para segmentos del donut (consistente con el tema oscuro).
const PALETTE = [
  '#3b82f6', '#22c55e', '#eab308', '#a855f7', '#ec4899',
  '#14b8a6', '#f97316', '#0ea5e9', '#84cc16', '#f43f5e',
]

const fmtUSD = (n: number) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: n >= 1000 ? 0 : 2,
  }).format(n)

const num = (s: string | number) => (typeof s === 'string' ? Number.parseFloat(s) : s)

interface AllocSlice {
  name: string
  value: number
  color: string
}

function buildAllocation(open: Position[]): AllocSlice[] {
  const bySymbol = new Map<string, number>()
  for (const p of open) {
    const exposure = Math.abs(num(p.open_quantity) * num(p.current_price))
    if (!Number.isFinite(exposure) || exposure <= 0) continue
    bySymbol.set(p.asset_symbol, (bySymbol.get(p.asset_symbol) ?? 0) + exposure)
  }
  return [...bySymbol.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([name, value], i) => ({ name, value, color: PALETTE[i % PALETTE.length] }))
}

interface CurvePoint {
  date: string
  cumulative: number
}

function buildPnlCurve(closed: Position[]): CurvePoint[] {
  const withDate = closed
    .filter(p => p.closed_at)
    .sort((a, b) => new Date(a.closed_at!).getTime() - new Date(b.closed_at!).getTime())
  let running = 0
  return withDate.map(p => {
    running += num(p.realized_pnl_usd)
    return {
      date: new Date(p.closed_at!).toLocaleDateString('es-ES', { day: '2-digit', month: 'short' }),
      cumulative: Math.round(running * 100) / 100,
    }
  })
}

function ChartCard({ title, subtitle, children }: {
  title: string
  subtitle: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-slate-800 rounded-xl border border-slate-700 p-5">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-white">{title}</h3>
        <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>
      </div>
      {children}
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="h-56 flex items-center justify-center text-center text-sm text-slate-500 px-4">
      {message}
    </div>
  )
}

function AllocationTooltip({ active, payload, total }: {
  active?: boolean
  payload?: Array<{ payload: AllocSlice }>
  total: number
}) {
  if (!active || !payload?.length) return null
  const slice = payload[0].payload
  const pct = total > 0 ? (slice.value / total) * 100 : 0
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="font-semibold text-white">{slice.name}</p>
      <p className="text-slate-300 font-mono">{fmtUSD(slice.value)}</p>
      <p className="text-slate-500">{pct.toFixed(1)}% de la cartera</p>
    </div>
  )
}

function PnlTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ value: number }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  const v = payload[0].value
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs shadow-xl">
      <p className="text-slate-400">{label}</p>
      <p className={`font-mono font-semibold ${v >= 0 ? 'text-positive' : 'text-negative'}`}>
        {v >= 0 ? '+' : ''}{fmtUSD(v)}
      </p>
    </div>
  )
}

export default function PortfolioInsights({
  openPositions,
  closedPositions,
}: {
  openPositions: Position[]
  closedPositions: Position[]
}) {
  const allocation = useMemo(() => buildAllocation(openPositions), [openPositions])
  const totalExposure = useMemo(() => allocation.reduce((s, a) => s + a.value, 0), [allocation])
  const curve = useMemo(() => buildPnlCurve(closedPositions), [closedPositions])

  const lastCurve = curve.length ? curve[curve.length - 1].cumulative : 0
  const curvePositive = lastCurve >= 0

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6 cw-fade-in-up">
      {/* ── Donut de distribución ── */}
      <ChartCard
        title="Distribución de la cartera"
        subtitle="Exposición actual por activo (valor de mercado)"
      >
        {allocation.length === 0 ? (
          <EmptyState message="Abre una posición para ver el reparto de tu cartera por activo." />
        ) : (
          <div className="flex flex-col sm:flex-row items-center gap-4">
            <div className="relative w-44 h-44 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={allocation}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={52}
                    outerRadius={78}
                    paddingAngle={allocation.length > 1 ? 2 : 0}
                    stroke="none"
                  >
                    {allocation.map(s => <Cell key={s.name} fill={s.color} />)}
                  </Pie>
                  <Tooltip content={<AllocationTooltip total={totalExposure} />} />
                </PieChart>
              </ResponsiveContainer>
              {/* Total en el centro */}
              <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                <span className="text-[10px] text-slate-500 uppercase tracking-wide">Total</span>
                <AnimatedNumber value={totalExposure} format={fmtUSD} className="text-base font-bold font-mono text-white" />
              </div>
            </div>
            {/* Leyenda */}
            <ul className="flex-1 w-full space-y-1.5 max-h-44 overflow-y-auto">
              {allocation.map(s => {
                const pct = totalExposure > 0 ? (s.value / totalExposure) * 100 : 0
                return (
                  <li key={s.name} className="flex items-center gap-2 text-sm">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ backgroundColor: s.color }} />
                    <span className="font-medium text-slate-200">{s.name}</span>
                    <span className="ml-auto font-mono text-slate-400 text-xs">{pct.toFixed(1)}%</span>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
      </ChartCard>

      {/* ── Curva de PnL realizado acumulado ── */}
      <ChartCard
        title="PnL realizado acumulado"
        subtitle="Resultado consolidado por fecha de cierre"
      >
        {curve.length < 2 ? (
          <EmptyState message="Cierra al menos dos posiciones para trazar la evolución de tu PnL realizado." />
        ) : (
          <div className="h-56">
            <div className="flex items-baseline gap-2 mb-2">
              <span className={`text-xl font-bold font-mono ${curvePositive ? 'text-positive' : 'text-negative'}`}>
                {curvePositive ? '+' : ''}{fmtUSD(lastCurve)}
              </span>
              <span className="text-xs text-slate-500">{curve.length} cierres</span>
            </div>
            <ResponsiveContainer width="100%" height="85%">
              <AreaChart data={curve} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={curvePositive ? '#22c55e' : '#ef4444'} stopOpacity={0.35} />
                    <stop offset="100%" stopColor={curvePositive ? '#22c55e' : '#ef4444'} stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={{ stroke: '#334155' }} minTickGap={24} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} axisLine={false} width={48}
                  tickFormatter={(v: number) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v))} />
                <Tooltip content={<PnlTooltip />} cursor={{ stroke: '#475569', strokeWidth: 1 }} />
                <Area
                  type="monotone"
                  dataKey="cumulative"
                  stroke={curvePositive ? '#22c55e' : '#ef4444'}
                  strokeWidth={2}
                  fill="url(#pnlFill)"
                  dot={false}
                  activeDot={{ r: 4 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </ChartCard>
    </div>
  )
}
