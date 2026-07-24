/**
 * pages/PortfolioPage.tsx - Gestión de portfolio con posiciones explícitas.
 *
 * Modelo Hedge: cada posición es independiente (LONG o SHORT).
 * Es posible tener múltiples posiciones simultáneas en la misma dirección
 * o en dirección opuesta sobre el mismo activo.
 *
 * Tabs:
 *   1. Posiciones Abiertas   - PnL no realizado en tiempo real
 *   2. Posiciones Cerradas   - PnL realizado histórico
 *   3. Historial de Trades   - registro raw de todas las operaciones
 */

import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import {
  portfolioService,
  type Position,
  type PositionSummary,
  type Trade,
  type OpenPositionPayload,
  type ClosePositionPayload,
  type AddToPositionPayload,
} from '../services/portfolioService'
import PortfolioInsights from '@/components/portfolio/PortfolioInsights'
import RiskPanel from '@/components/portfolio/RiskPanel'
import TcaPanel from '@/components/portfolio/TcaPanel'
import EmptyState from '../components/ui/EmptyState'
import AnimatedNumber from '../components/ui/AnimatedNumber'
import Skeleton from '../components/ui/Skeleton'

// -- Iconos para estados vacíos --

const IconPositions = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.5 9 7.5l4 4 7-7M21 8.5v5h-5" />
  </svg>
)

const IconHistory = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
  </svg>
)

// -- Helpers --

const fmt = (n: string | number, decimals = 2) =>
  new Intl.NumberFormat('es-ES', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(typeof n === 'string' ? Number.parseFloat(n) : n)

const fmtUSD = (n: string | number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(
    typeof n === 'string' ? Number.parseFloat(n) : n,
  )

const pnlColor = (is_profit: boolean) => (is_profit ? 'text-positive' : 'text-negative')
const pnlBg = (is_profit: boolean) => (is_profit ? 'bg-positive-soft' : 'bg-negative-soft')
const sign = (isProfit: boolean) => (isProfit ? '+' : '')
const NOW_ISO = () => new Date().toISOString().slice(0, 16)

// -- Badges --

function DirectionBadge({ direction }: { direction: 'LONG' | 'SHORT' }) {
  return direction === 'LONG' ? (
    <span className="px-1.5 py-0.5 rounded text-xs font-bold bg-positive-soft text-positive border border-positive-ring">
      LONG
    </span>
  ) : (
    <span className="px-1.5 py-0.5 rounded text-xs font-bold bg-caution-soft text-caution border border-caution-ring">
      SHORT
    </span>
  )
}

// -- Modal: Abrir posición --

function OpenPositionModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const [form, setForm] = useState<OpenPositionPayload>({
    asset_symbol: '',
    direction: 'LONG',
    quantity: 0,
    entry_price: 0,
    opened_at: NOW_ISO(),
    label: '',
    notes: '',
  })
  const [totalUsd, setTotalUsd] = useState('')
  const [loading, setLoading] = useState(false)
  const [fetchingPrice, setFetchingPrice] = useState(false)
  const [priceNote, setPriceNote] = useState('')
  const [error, setError] = useState('')

  const handleQtyChange = (val: string) => {
    const qty = Number.parseFloat(val) || 0
    if (qty > 0 && form.entry_price > 0) setTotalUsd((qty * form.entry_price).toFixed(2))
    setForm(f => ({ ...f, quantity: qty }))
  }
  const handlePriceChange = (val: string) => {
    const price = Number.parseFloat(val) || 0
    if (price > 0 && form.quantity > 0) setTotalUsd((form.quantity * price).toFixed(2))
    setForm(f => ({ ...f, entry_price: price }))
    if (val) setPriceNote('')
  }
  const handleTotalChange = (val: string) => {
    setTotalUsd(val)
    const total = Number.parseFloat(val) || 0
    if (total > 0 && form.entry_price > 0)
      setForm(f => ({ ...f, quantity: Number.parseFloat((total / f.entry_price).toFixed(10)) }))
  }
  const fetchPrice = async () => {
    if (!form.asset_symbol) return
    setFetchingPrice(true)
    setPriceNote('')
    const price = await portfolioService.getAssetPrice(form.asset_symbol)
    if (price !== null && price > 0) {
      const qty = form.quantity
      const tot = Number.parseFloat(totalUsd) || 0
      setForm(f => ({ ...f, entry_price: price }))
      if (qty > 0) setTotalUsd((qty * price).toFixed(2))
      else if (tot > 0)
        setForm(f => ({ ...f, entry_price: price, quantity: Number.parseFloat((tot / price).toFixed(10)) }))
      setPriceNote(
        `Precio actual: $${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 })}`,
      )
    } else {
      setPriceNote(`"${form.asset_symbol}" no está en el catálogo.`)
    }
    setFetchingPrice(false)
  }
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (form.quantity <= 0) { setError('La cantidad debe ser mayor que cero.'); return }
    if (form.entry_price <= 0) { setError('El precio debe ser mayor que cero.'); return }
    setLoading(true)
    try {
      await portfolioService.openPosition({ ...form, opened_at: new Date(form.opened_at).toISOString() })
      onCreated()
      onClose()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg ?? 'Error al abrir la posición')
    } finally {
      setLoading(false)
    }
  }
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-2xl p-6 w-full max-w-md border border-slate-700 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center mb-5">
          <h2 className="text-lg font-bold text-white">Abrir posición</h2>
          <button onClick={onClose} aria-label="Cerrar" className="text-slate-400 hover:text-white text-xl leading-none">&times;</button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Símbolo</label>
            <div className="flex gap-2">
              <input
                className="flex-1 bg-slate-700 text-white rounded-lg px-3 py-2 text-sm uppercase placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="BTC, ETH, SOL..."
                value={form.asset_symbol}
                onChange={e => { setForm(f => ({ ...f, asset_symbol: e.target.value.toUpperCase() })); setPriceNote('') }}
                required
              />
              <button
                type="button"
                onClick={fetchPrice}
                disabled={fetchingPrice || !form.asset_symbol}
                className="shrink-0 px-3 py-2 rounded-lg bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white text-xs font-medium whitespace-nowrap"
              >
                {fetchingPrice ? '...' : 'Precio actual'}
              </button>
            </div>
            {priceNote && (
              <p className={`text-xs mt-1 ${priceNote.includes('no está') ? 'text-negative' : 'text-positive'}`}>
                {priceNote}
              </p>
            )}
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Dirección</label>
            <div className="flex gap-2">
              {(['LONG', 'SHORT'] as const).map(d => (
                <button key={d} type="button"
                  onClick={() => setForm(f => ({ ...f, direction: d }))}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    form.direction === d
                      ? d === 'LONG'
                        ? 'bg-positive text-white'
                        : 'bg-caution text-white'
                      : 'bg-slate-700 text-slate-400 hover:text-white'
                  }`}
                >
                  {d === 'LONG' ? '↑ LONG' : '↓ SHORT'}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Total (USD)</label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm">$</span>
              <input type="number" step="any" min="0" placeholder="500"
                className="w-full bg-slate-700 text-white rounded-lg pl-7 pr-3 py-2 text-sm placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={totalUsd} onChange={e => handleTotalChange(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Cantidad (tokens)</label>
              <input type="number" step="any" min="0" placeholder="0.005"
                className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={form.quantity || ''} onChange={e => handleQtyChange(e.target.value)} required />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Precio entrada (USD)</label>
              <input type="number" step="any" min="0" placeholder="94000"
                className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={form.entry_price || ''} onChange={e => handlePriceChange(e.target.value)} required />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Fecha y hora de entrada</label>
            <input type="datetime-local"
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              value={form.opened_at} onChange={e => setForm(f => ({ ...f, opened_at: e.target.value }))} required />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Etiqueta (opcional)</label>
            <input
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Estrategia largo plazo, DCA..."
              value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Notas (opcional)</label>
            <input
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Exchange, contexto..."
              value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          </div>
          {error && <p className="text-negative text-sm">{error}</p>}
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg text-sm">
              Cancelar
            </button>
            <button type="submit" disabled={loading}
              className={`flex-1 py-2 rounded-lg text-sm font-medium disabled:opacity-50 text-white ${
                form.direction === 'LONG' ? 'bg-positive hover:bg-green-500' : 'bg-caution hover:bg-yellow-500'
              }`}>
              {loading ? 'Abriendo...' : `Abrir ${form.direction}`}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// -- Modal: Ampliar posición --

function AddToPositionModal({
  position,
  onClose,
  onDone,
}: {
  position: Position
  onClose: () => void
  onDone: () => void
}) {
  const currentPrice = Number.parseFloat(position.current_price)
  const [form, setForm] = useState<AddToPositionPayload>({
    quantity: 0,
    entry_price: Math.max(currentPrice, 0),
    executed_at: NOW_ISO(),
    notes: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (form.quantity <= 0) { setError('La cantidad debe ser mayor que cero.'); return }
    if (form.entry_price <= 0) { setError('El precio debe ser mayor que cero.'); return }
    setLoading(true)
    try {
      await portfolioService.addToPosition(position.id, {
        ...form,
        executed_at: new Date(form.executed_at).toISOString(),
      })
      onDone()
      onClose()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg ?? 'Error al ampliar la posición')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-2xl p-6 w-full max-w-md border border-slate-700">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h2 className="text-lg font-bold text-white">Ampliar posición</h2>
            <div className="flex items-center gap-2 mt-1">
              <DirectionBadge direction={position.direction} />
              <span className="text-sm text-slate-300">
                {position.asset_symbol} · entrada media: {fmtUSD(position.avg_entry_price)}
              </span>
            </div>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="text-slate-400 hover:text-white text-xl leading-none">&times;</button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Cantidad a añadir</label>
              <input type="number" step="any" min="0" placeholder="0.01"
                className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={form.quantity || ''}
                onChange={e => setForm(f => ({ ...f, quantity: Number.parseFloat(e.target.value) || 0 }))}
                required />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Precio entrada (USD)</label>
              <input type="number" step="any" min="0"
                className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={form.entry_price || ''}
                onChange={e => setForm(f => ({ ...f, entry_price: Number.parseFloat(e.target.value) || 0 }))}
                required />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Fecha y hora</label>
            <input type="datetime-local"
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              value={form.executed_at}
              onChange={e => setForm(f => ({ ...f, executed_at: e.target.value }))}
              required />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Notas (opcional)</label>
            <input
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Exchange, contexto..."
              value={form.notes}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          </div>
          {error && <p className="text-negative text-sm">{error}</p>}
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg text-sm">
              Cancelar
            </button>
            <button type="submit" disabled={loading}
              className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white py-2 rounded-lg text-sm font-medium">
              {loading ? 'Guardando...' : 'Ampliar posición'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// -- Modal: Cerrar posición --

function ClosePositionModal({
  position,
  onClose,
  onDone,
}: {
  position: Position
  onClose: () => void
  onDone: () => void
}) {
  const currentPrice = Number.parseFloat(position.current_price)
  const openQty = Number.parseFloat(position.open_quantity)
  const [form, setForm] = useState<ClosePositionPayload>({
    close_quantity: openQty,
    close_price: Math.max(currentPrice, 0),
    executed_at: NOW_ISO(),
    notes: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const isFullClose = form.close_quantity >= openQty
  const avgEntry = Number.parseFloat(position.avg_entry_price)
  const estimatedPnl =
    form.close_price > 0 && form.close_quantity > 0
      ? position.direction === 'LONG'
        ? (form.close_price - avgEntry) * form.close_quantity
        : (avgEntry - form.close_price) * form.close_quantity
      : null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (form.close_quantity <= 0) { setError('La cantidad debe ser mayor que cero.'); return }
    if (form.close_quantity > openQty) { setError(`No puedes cerrar más de ${openQty} tokens.`); return }
    if (form.close_price <= 0) { setError('El precio de cierre debe ser mayor que cero.'); return }
    setLoading(true)
    try {
      await portfolioService.closePosition(position.id, {
        ...form,
        executed_at: new Date(form.executed_at).toISOString(),
      })
      onDone()
      onClose()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg ?? 'Error al cerrar la posición')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-2xl p-6 w-full max-w-md border border-slate-700">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h2 className="text-lg font-bold text-white">Cerrar posición</h2>
            <div className="flex items-center gap-2 mt-1">
              <DirectionBadge direction={position.direction} />
              <span className="text-sm text-slate-300">
                {position.asset_symbol} · {fmt(position.open_quantity, 6)} tokens disponibles
              </span>
            </div>
          </div>
          <button onClick={onClose} aria-label="Cerrar" className="text-slate-400 hover:text-white text-xl leading-none">&times;</button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="flex gap-2">
            {[25, 50, 75, 100].map(pct => (
              <button key={pct} type="button"
                onClick={() => setForm(f => ({
                  ...f,
                  close_quantity: Number.parseFloat((openQty * pct / 100).toFixed(10)),
                }))}
                className="flex-1 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs text-slate-300">
                {pct}%
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Cantidad{' '}
                {isFullClose && <span className="text-caution">(cierre total)</span>}
              </label>
              <input type="number" step="any" min="0" max={openQty}
                className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={form.close_quantity || ''}
                onChange={e => setForm(f => ({ ...f, close_quantity: Number.parseFloat(e.target.value) || 0 }))}
                required />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Precio de cierre (USD)</label>
              <input type="number" step="any" min="0"
                className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={form.close_price || ''}
                onChange={e => setForm(f => ({ ...f, close_price: Number.parseFloat(e.target.value) || 0 }))}
                required />
            </div>
          </div>
          {estimatedPnl !== null && (
            <div className={`rounded-lg p-3 text-sm ${estimatedPnl >= 0 ? 'bg-positive-soft text-positive' : 'bg-negative-soft text-negative'}`}>
              PnL estimado: <strong>{estimatedPnl >= 0 ? '+' : ''}{fmtUSD(estimatedPnl)}</strong>
            </div>
          )}
          <div>
            <label className="block text-xs text-slate-400 mb-1">Fecha y hora</label>
            <input type="datetime-local"
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              value={form.executed_at}
              onChange={e => setForm(f => ({ ...f, executed_at: e.target.value }))}
              required />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Notas (opcional)</label>
            <input
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Motivo del cierre..."
              value={form.notes}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} />
          </div>
          {error && <p className="text-negative text-sm">{error}</p>}
          <div className="flex gap-3 pt-1">
            <button type="button" onClick={onClose}
              className="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg text-sm">
              Cancelar
            </button>
            <button type="submit" disabled={loading}
              className="flex-1 bg-negative hover:bg-red-600 disabled:opacity-50 text-white py-2 rounded-lg text-sm font-medium">
              {loading ? 'Cerrando...' : isFullClose ? 'Cerrar posición' : 'Cierre parcial'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// -- Tabla posiciones abiertas --

function OpenPositionsTable({
  positions,
  onAdd,
  onClose,
  onDelete,
}: {
  positions: Position[]
  onAdd: (p: Position) => void
  onClose: (p: Position) => void
  onDelete: (p: Position) => void
}) {
  if (positions.length === 0) {
    return (
      <EmptyState
        icon={<IconPositions />}
        title="Sin posiciones abiertas"
        description='Pulsa "Nueva posición" para abrir tu primera posición LONG o SHORT.'
      />
    )
  }
  return (
    <div className="bg-slate-800 rounded-xl overflow-x-auto">
      <table className="w-full text-sm min-w-[760px]">
        <thead>
          <tr className="text-slate-400 text-xs border-b border-slate-700">
            <th className="text-left px-4 py-3">Activo</th>
            <th className="text-right px-4 py-3">Cantidad abierta</th>
            <th className="text-right px-4 py-3">Precio medio</th>
            <th className="text-right px-4 py-3">Precio actual</th>
            <th className="text-right px-4 py-3">PnL no realizado</th>
            <th className="text-right px-4 py-3">PnL realizado</th>
            <th className="text-right px-4 py-3">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(pos => {
            const realizedNum = Number.parseFloat(pos.realized_pnl_usd)
            return (
              <tr key={pos.id} className="border-b border-slate-700/50 hover:bg-slate-700/20">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {pos.logo_url && (
                      <img src={pos.logo_url} alt={pos.asset_symbol} className="w-6 h-6 rounded-full" />
                    )}
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium">{pos.asset_symbol}</span>
                        <DirectionBadge direction={pos.direction} />
                      </div>
                      <p className="text-xs text-slate-400">{pos.asset_name}</p>
                      {pos.label && <p className="text-xs text-blue-400/70 mt-0.5">{pos.label}</p>}
                    </div>
                  </div>
                </td>
                <td className="text-right px-4 py-3 font-mono">{fmt(pos.open_quantity, 6)}</td>
                <td className="text-right px-4 py-3 font-mono">{fmtUSD(pos.avg_entry_price)}</td>
                <td className="text-right px-4 py-3 font-mono">{fmtUSD(pos.current_price)}</td>
                <td className={`text-right px-4 py-3 font-mono ${pnlColor(pos.is_profit)}`}>
                  {sign(pos.is_profit)}{fmtUSD(pos.unrealized_pnl_usd)}<br />
                  <span className="text-xs">{sign(pos.is_profit)}{fmt(pos.unrealized_pnl_pct)}%</span>
                </td>
                <td className={`text-right px-4 py-3 font-mono ${realizedNum >= 0 ? 'text-positive' : 'text-negative'}`}>
                  {realizedNum >= 0 ? '+' : ''}{fmtUSD(pos.realized_pnl_usd)}
                </td>
                <td className="text-right px-4 py-3">
                  <div className="flex justify-end gap-1.5">
                    <button onClick={() => onAdd(pos)}
                      className="px-2 py-1 rounded bg-blue-900/50 hover:bg-blue-700/60 text-blue-300 text-xs">
                      + Ampliar
                    </button>
                    <button onClick={() => onClose(pos)}
                      className="px-2 py-1 rounded bg-negative-soft hover:bg-red-700/50 text-negative text-xs">
                      Cerrar
                    </button>
                    {pos.trades_count === 0 && (
                      <button onClick={() => onDelete(pos)}
                        className="px-2 py-1 rounded bg-slate-700/50 hover:bg-slate-600/60 text-slate-400 text-xs"
                        title="Eliminar (sin trades)">
                        Borrar
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// -- Tabla posiciones cerradas --

function ClosedPositionsTable({ positions }: { positions: Position[] }) {
  if (positions.length === 0) {
    return (
      <EmptyState
        icon={<IconPositions />}
        title="No hay posiciones cerradas"
        description="Cuando cierres una posición aparecerá aquí con su PnL realizado."
      />
    )
  }
  return (
    <div className="bg-slate-800 rounded-xl overflow-x-auto">
      <table className="w-full text-sm min-w-[640px]">
        <thead>
          <tr className="text-slate-400 text-xs border-b border-slate-700">
            <th className="text-left px-4 py-3">Activo</th>
            <th className="text-right px-4 py-3">Cantidad inicial</th>
            <th className="text-right px-4 py-3">Precio entrada</th>
            <th className="text-right px-4 py-3">PnL realizado</th>
            <th className="text-right px-4 py-3">Apertura</th>
            <th className="text-right px-4 py-3">Cierre</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(pos => {
            const realized = Number.parseFloat(pos.realized_pnl_usd)
            const isProfit = realized >= 0
            return (
              <tr key={pos.id} className="border-b border-slate-700/50 hover:bg-slate-700/20">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {pos.logo_url && (
                      <img src={pos.logo_url} alt={pos.asset_symbol} className="w-6 h-6 rounded-full" />
                    )}
                    <div>
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium">{pos.asset_symbol}</span>
                        <DirectionBadge direction={pos.direction} />
                      </div>
                      {pos.label && <p className="text-xs text-blue-400/70">{pos.label}</p>}
                    </div>
                  </div>
                </td>
                <td className="text-right px-4 py-3 font-mono">{fmt(pos.initial_quantity, 6)}</td>
                <td className="text-right px-4 py-3 font-mono">{fmtUSD(pos.avg_entry_price)}</td>
                <td className={`text-right px-4 py-3 font-mono font-semibold ${isProfit ? 'text-green-400' : 'text-red-400'}`}>
                  {isProfit ? '+' : ''}{fmtUSD(realized)}
                </td>
                <td className="text-right px-4 py-3 text-slate-400 text-xs">
                  {new Date(pos.opened_at).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })}
                </td>
                <td className="text-right px-4 py-3 text-slate-400 text-xs">
                  {pos.closed_at
                    ? new Date(pos.closed_at).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })
                    : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// -- Tabla historial de trades --

function TradeHistoryTable({
  trades,
  onDelete,
}: {
  trades: Trade[]
  onDelete: (id: number) => void
}) {
  if (trades.length === 0) {
    return (
      <EmptyState
        icon={<IconHistory />}
        title="No hay operaciones registradas"
        description="Tus compras y ventas aparecerán en este historial."
      />
    )
  }
  return (
    <div className="bg-slate-800 rounded-xl overflow-x-auto">
      <table className="w-full text-sm min-w-[620px]">
        <thead>
          <tr className="text-slate-400 text-xs border-b border-slate-700">
            <th className="text-left px-4 py-3">Fecha</th>
            <th className="text-left px-4 py-3">Activo</th>
            <th className="text-left px-4 py-3">Tipo</th>
            <th className="text-right px-4 py-3">Cantidad</th>
            <th className="text-right px-4 py-3">Precio</th>
            <th className="text-right px-4 py-3">Total</th>
            <th className="text-right px-4 py-3"></th>
          </tr>
        </thead>
        <tbody>
          {trades.map(t => (
            <tr key={t.id} className="border-b border-slate-700/50 hover:bg-slate-700/20">
              <td className="px-4 py-3 text-slate-400 text-xs">
                {new Date(t.executed_at).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })}
              </td>
              <td className="px-4 py-3 font-medium">{t.asset_symbol}</td>
              <td className="px-4 py-3">
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  t.trade_type === 'BUY'
                    ? 'bg-green-900/40 text-green-400'
                    : 'bg-red-900/40 text-red-400'
                }`}>
                  {t.trade_type === 'BUY' ? '↑ Compra' : '↓ Venta'}
                </span>
              </td>
              <td className="text-right px-4 py-3 font-mono">{fmt(t.quantity, 6)}</td>
              <td className="text-right px-4 py-3 font-mono">{fmtUSD(t.price_usd)}</td>
              <td className="text-right px-4 py-3 font-mono">{fmtUSD(t.total_usd)}</td>
              <td className="text-right px-4 py-3">
                <button onClick={() => onDelete(t.id)}
                  className="text-slate-500 hover:text-red-400 text-xs transition-colors">
                  Eliminar
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// -- Página principal --

type Tab = 'open' | 'closed' | 'history'

export default function PortfolioPage() {
  const { t } = useTranslation()
  const [positionSummary, setPositionSummary] = useState<PositionSummary | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [tab, setTab] = useState<Tab>('open')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [showOpenModal, setShowOpenModal] = useState(false)
  const [addTarget, setAddTarget] = useState<Position | null>(null)
  const [closeTarget, setCloseTarget] = useState<Position | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [summary, tradeList] = await Promise.all([
        portfolioService.getPositions(),
        portfolioService.getTrades({ limit: 200 }),
      ])
      setPositionSummary(summary)
      setTrades(tradeList)
    } catch {
      setError('Error al cargar el portfolio')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  const handleDeleteTrade = async (id: number) => {
    if (!confirm('¿Eliminar esta operación?')) return
    try { await portfolioService.deleteTrade(id); await fetchData() }
    catch { alert('No se pudo eliminar la operación') }
  }

  const handleDeletePosition = async (pos: Position) => {
    if (!confirm(`¿Eliminar la posición ${pos.direction} ${pos.asset_symbol}?`)) return
    try { await portfolioService.deletePosition(pos.id); await fetchData() }
    catch { alert('No se pudo eliminar la posición') }
  }

  const openPositions = positionSummary?.open_positions ?? []
  const closedPositions = positionSummary?.closed_positions ?? []
  const totalUnrealized = Number.parseFloat(positionSummary?.total_unrealized_pnl_usd ?? '0')
  const totalRealized = Number.parseFloat(positionSummary?.total_realized_pnl_usd ?? '0')

  return (
    <div>
        {/* Cabecera */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">{t('portfolio.title')}</h1>
            <p className="text-slate-400 text-sm mt-1">
              {t('portfolio.subtitle')}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative group">
              <button
                className="bg-slate-700 hover:bg-slate-600 text-slate-200 px-3 py-2 rounded-xl text-sm font-medium transition-colors flex items-center gap-1.5"
                title="Exportar informe CSV"
              >
                ⭳ Exportar
              </button>
              <div className="absolute right-0 mt-1 w-44 bg-slate-800 border border-slate-700 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-20">
                <button
                  onClick={() => portfolioService.downloadReport('positions').catch(() => { /* ignore */ })}
                  className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700/60 rounded-t-lg"
                >
                  📄 Posiciones (CSV)
                </button>
                <button
                  onClick={() => portfolioService.downloadReport('risk').catch(() => { /* ignore */ })}
                  className="w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700/60 rounded-b-lg"
                >
                  🛡 Riesgo (CSV)
                </button>
              </div>
            </div>
            <button
              onClick={() => setShowOpenModal(true)}
              className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-xl text-sm font-medium transition-colors"
            >
              {t('portfolio.newPosition')}
            </button>
          </div>
        </div>

        {loading && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-20 rounded-xl" />
              ))}
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <Skeleton className="h-64 rounded-xl" />
              <Skeleton className="h-64 rounded-xl" />
            </div>
            <Skeleton className="h-48 rounded-xl" />
          </div>
        )}
        {error && !loading && (
          <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm mb-6">
            {error}
          </div>
        )}

        {!loading && !error && positionSummary && (
          <>
            {/* Riesgo agregado del libro completo (manual + paper + real) */}
            <RiskPanel />
            {/* Coste de ejecución real (TCA) */}
            <div className="mb-6"><TcaPanel /></div>
            {/* KPIs */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-slate-800 rounded-xl p-4">
                <p className="text-xs text-slate-400 mb-1">{t('portfolio.openPositions')}</p>
                <AnimatedNumber value={openPositions.length} className="text-xl font-bold block" />
                <p className="text-xs text-slate-500 mt-0.5">
                  {positionSummary.open_long_count} LONG · {positionSummary.open_short_count} SHORT
                </p>
              </div>
              <div className="bg-slate-800 rounded-xl p-4">
                <p className="text-xs text-slate-400 mb-1">{t('portfolio.closedPositions')}</p>
                <AnimatedNumber value={closedPositions.length} className="text-xl font-bold block" />
              </div>
              <div className={`rounded-xl p-4 ${pnlBg(totalUnrealized >= 0)}`}>
                <p className="text-xs text-slate-400 mb-1">{t('portfolio.unrealizedPnl')}</p>
                <AnimatedNumber
                  value={totalUnrealized}
                  format={(n) => `${n >= 0 ? '+' : ''}${fmtUSD(n)}`}
                  className={`text-xl font-bold block ${pnlColor(totalUnrealized >= 0)}`}
                />
              </div>
              <div className={`rounded-xl p-4 ${pnlBg(totalRealized >= 0)}`}>
                <p className="text-xs text-slate-400 mb-1">{t('portfolio.realizedPnl')}</p>
                <AnimatedNumber
                  value={totalRealized}
                  format={(n) => `${n >= 0 ? '+' : ''}${fmtUSD(n)}`}
                  className={`text-xl font-bold block ${pnlColor(totalRealized >= 0)}`}
                />
              </div>
            </div>

            {/* Visualizaciones: distribución de cartera + curva de PnL realizado */}
            {(openPositions.length > 0 || closedPositions.length > 0) && (
              <PortfolioInsights openPositions={openPositions} closedPositions={closedPositions} />
            )}

            {/* Tabs */}
            <div className="flex gap-2 mb-4">
              {(
                [
                  ['open', t('portfolio.tabOpen', { count: openPositions.length })],
                  ['closed', t('portfolio.tabClosed', { count: closedPositions.length })],
                  ['history', t('portfolio.tabHistory', { count: trades.length })],
                ] as [Tab, string][]
              ).map(([t, label]) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    tab === t
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-800 text-slate-400 hover:text-white'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            {tab === 'open' && (
              <OpenPositionsTable
                positions={openPositions}
                onAdd={p => setAddTarget(p)}
                onClose={p => setCloseTarget(p)}
                onDelete={handleDeletePosition}
              />
            )}
            {tab === 'closed' && <ClosedPositionsTable positions={closedPositions} />}
            {tab === 'history' && <TradeHistoryTable trades={trades} onDelete={handleDeleteTrade} />}
          </>
        )}

      {showOpenModal && (
        <OpenPositionModal onClose={() => setShowOpenModal(false)} onCreated={fetchData} />
      )}
      {addTarget && (
        <AddToPositionModal position={addTarget} onClose={() => setAddTarget(null)} onDone={fetchData} />
      )}
      {closeTarget && (
        <ClosePositionModal position={closeTarget} onClose={() => setCloseTarget(null)} onDone={fetchData} />
      )}
    </div>
  )
}
