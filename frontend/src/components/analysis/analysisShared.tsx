/**
 * components/analysis/analysisShared.tsx — Utilidades y piezas compartidas por
 * las pestañas del panel de análisis (señales, indicadores, predicción, patrones,
 * backtest). Extraído de AnalysisPanel para que cada pestaña viva en su archivo.
 */

import { type ReactNode } from 'react'

// ── Helpers de señal ─────────────────────────────────────────────

export function signalColor(signal: string): string {
  switch (signal) {
    case 'COMPRA':
    case 'COMPRA_FUERTE':
      return 'text-green-400'
    case 'VENTA':
    case 'VENTA_FUERTE':
      return 'text-red-400'
    default:
      return 'text-yellow-400'
  }
}

export function signalBg(signal: string): string {
  switch (signal) {
    case 'COMPRA':
    case 'COMPRA_FUERTE':
      return 'bg-green-500/20 border-green-500/30'
    case 'VENTA':
    case 'VENTA_FUERTE':
      return 'bg-red-500/20 border-red-500/30'
    default:
      return 'bg-yellow-500/20 border-yellow-500/30'
  }
}

export function signalLabel(signal: string): string {
  const map: Record<string, string> = {
    'COMPRA': 'Compra',
    'COMPRA_FUERTE': 'Compra Fuerte',
    'VENTA': 'Venta',
    'VENTA_FUERTE': 'Venta Fuerte',
    'NEUTRAL': 'Neutral',
  }
  return map[signal] ?? signal
}

export function signalDot(signal: string): string {
  switch (signal) {
    case 'COMPRA':
    case 'COMPRA_FUERTE':
      return 'bg-green-400'
    case 'VENTA':
    case 'VENTA_FUERTE':
      return 'bg-red-400'
    default:
      return 'bg-yellow-400'
  }
}

export function reliabilityBadge(r: string) {
  const colors: Record<string, string> = {
    'ALTA':  'bg-green-600/30 text-green-300',
    'MEDIA': 'bg-yellow-600/30 text-yellow-300',
    'BAJA':  'bg-slate-600/30 text-slate-300',
  }
  return colors[r] ?? 'bg-slate-600/30 text-slate-300'
}

export function reliabilityStars(r: string): string {
  const map: Record<string, string> = { 'ALTA': '★★★', 'MEDIA': '★★☆', 'BAJA': '★☆☆' }
  return map[r] ?? '—'
}

// Descripción educativa de 1 frase por indicador. El orden importa:
// los más específicos (Stochastic) se comprueban antes que los genéricos.
export function indicatorDescription(name: string): string | null {
  const n = name.toLowerCase()
  if (n.includes('stoch')) return 'Stochastic RSI: aplica el oscilador estocástico sobre el RSI para anticipar giros de precio antes que el RSI clásico.'
  if (n.includes('rsi')) return 'RSI (Índice de Fuerza Relativa): escala de 0 a 100; por encima de 70 indica sobrecompra y por debajo de 30, sobreventa.'
  if (n.includes('macd')) return 'MACD: compara dos medias móviles exponenciales para detectar cambios de momentum y de tendencia.'
  if (n.includes('boll')) return 'Bandas de Bollinger: miden la volatilidad; tocar la banda superior sugiere sobrecompra y la inferior, sobreventa.'
  if (n.includes('sma')) return 'SMA (Media Móvil Simple): precio medio de las últimas N velas; si el precio la supera, la tendencia es alcista.'
  if (n.includes('ema')) return 'EMA (Media Móvil Exponencial): como la SMA pero da más peso a las velas recientes, por lo que reacciona antes.'
  if (n.includes('adx')) return 'ADX: mide la fuerza de la tendencia (no su dirección); por encima de 25 indica una tendencia fuerte.'
  if (n.includes('atr')) return 'ATR (Average True Range): mide la volatilidad media del mercado; valores altos indican movimientos bruscos.'
  if (n.includes('cci')) return 'CCI (Commodity Channel Index): detecta condiciones de sobrecompra/sobreventa y posibles giros de precio.'
  if (n.includes('obv')) return 'OBV (On-Balance Volume): acumula el volumen según la dirección del precio para confirmar tendencias.'
  if (n.includes('vwap')) return 'VWAP: precio medio ponderado por volumen del día; actúa como soporte/resistencia intradiario.'
  if (n.includes('williams')) return 'Williams %R: oscilador de momentum; cerca de 0 indica sobrecompra y cerca de -100, sobreventa.'
  return null
}

// ── Piezas de UI compartidas ─────────────────────────────────────

export function MetricCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-slate-900/50 rounded-lg p-3">
      <p className="text-[10px] text-slate-500 uppercase">{label}</p>
      <p className={`text-sm font-bold font-mono ${color}`}>{value}</p>
    </div>
  )
}

export function NumField({ label, value, onChange, title }: { label: string; value: number; onChange: (n: number) => void; title?: string }) {
  return (
    <label className="text-[10px] text-slate-400" title={title}>
      <span className="block mb-1 uppercase">{label}</span>
      <input
        type="number" min={0} value={value}
        onChange={(e) => onChange(Math.max(0, Number.parseFloat(e.target.value) || 0))}
        className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 w-24 focus:ring-1 focus:ring-blue-500 outline-none"
      />
    </label>
  )
}

export function TextField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (s: string) => void; placeholder?: string }) {
  return (
    <label className="text-[10px] text-slate-400">
      <span className="block mb-1 uppercase">{label}</span>
      <input
        type="number" min={0} step="0.5" value={value} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 w-24 focus:ring-1 focus:ring-blue-500 outline-none"
      />
    </label>
  )
}

export function EmptyState({ icon, title, description }: { icon: ReactNode; title: string; description: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center gap-3">
      <div className="text-slate-600">{icon}</div>
      <div>
        <p className="text-slate-300 text-sm font-medium">{title}</p>
        <p className="text-slate-500 text-xs max-w-md mt-1 leading-relaxed">{description}</p>
      </div>
      <p className="text-[10px] text-slate-600 mt-1">Pulsa "Ejecutar análisis" para comenzar</p>
    </div>
  )
}
