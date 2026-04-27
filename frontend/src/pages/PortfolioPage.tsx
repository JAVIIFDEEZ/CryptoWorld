/**
 * pages/PortfolioPage.tsx — Gestión de portfolio de criptomonedas.
 *
 * Permite al usuario ver su portfolio (posiciones abiertas + PnL),
 * registrar operaciones de compra/venta y ver el historial de trades.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  portfolioService,
  type PortfolioSummary,
  type Trade,
  type AddTradePayload,
} from '../services/portfolioService'

// ────────────────────────── Helpers ──────────────────────────────

const fmt = (n: number, decimals = 2) =>
  new Intl.NumberFormat('es-ES', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(n)

const fmtUSD = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)

// ────────────────────────── Formulario AddTrade ───────────────────

const EMPTY_FORM: AddTradePayload = {
  asset_symbol: '',
  trade_type: 'BUY',
  quantity: 0,
  price_usd: 0,
  executed_at: new Date().toISOString().slice(0, 16),
  notes: '',
}

function AddTradeModal({
  onClose,
  onAdded,
}: {
  onClose: () => void
  onAdded: () => void
}) {
  const [form, setForm] = useState<AddTradePayload>(EMPTY_FORM)
  const [totalUsd, setTotalUsd] = useState('')
  const [loading, setLoading] = useState(false)
  const [fetchingPrice, setFetchingPrice] = useState(false)
  const [priceNote, setPriceNote] = useState('')
  const [error, setError] = useState('')

  // Cantidad cambia → actualiza Total
  const handleQtyChange = (val: string) => {
    const qty = parseFloat(val) || 0
    if (qty > 0 && form.price_usd > 0) {
      setTotalUsd((qty * form.price_usd).toFixed(2))
    }
    setForm(f => ({ ...f, quantity: qty }))
  }

  // Precio cambia → actualiza Total
  const handlePriceChange = (val: string) => {
    const price = parseFloat(val) || 0
    if (price > 0 && form.quantity > 0) {
      setTotalUsd((form.quantity * price).toFixed(2))
    }
    setForm(f => ({ ...f, price_usd: price }))
    if (val) setPriceNote('')
  }

  // Total cambia → calcula Cantidad = Total / Precio
  const handleTotalChange = (val: string) => {
    setTotalUsd(val)
    const total = parseFloat(val) || 0
    if (total > 0 && form.price_usd > 0) {
      setForm(f => ({ ...f, quantity: parseFloat((total / f.price_usd).toFixed(10)) }))
    }
  }

  // Obtener precio actual del catálogo
  const fetchPrice = async () => {
    if (!form.asset_symbol) return
    setFetchingPrice(true)
    setPriceNote('')
    const price = await portfolioService.getAssetPrice(form.asset_symbol)
    if (price !== null && price > 0) {
      const qty = form.quantity
      const tot = parseFloat(totalUsd) || 0
      setForm(f => ({ ...f, price_usd: price }))
      if (qty > 0) {
        setTotalUsd((qty * price).toFixed(2))
      } else if (tot > 0) {
        setForm(f => ({ ...f, price_usd: price, quantity: parseFloat((tot / price).toFixed(10)) }))
      }
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
    if (form.price_usd <= 0) { setError('El precio debe ser mayor que cero.'); return }
    setLoading(true)
    try {
      await portfolioService.addTrade({
        ...form,
        executed_at: new Date(form.executed_at).toISOString(),
      })
      onAdded()
      onClose()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
      setError(msg ?? 'Error al registrar la operación')
    } finally {
      setLoading(false)
    }
  }

  const displayTotal = totalUsd || (form.quantity > 0 && form.price_usd > 0
    ? (form.quantity * form.price_usd).toFixed(2)
    : '')

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-2xl p-6 w-full max-w-md border border-gray-700">
        <div className="flex justify-between items-center mb-5">
          <h2 className="text-lg font-bold text-white">Registrar operación</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl">✕</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Símbolo + botón precio */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Símbolo</label>
            <div className="flex gap-2">
              <input
                className="flex-1 bg-gray-700 text-white rounded-lg px-3 py-2 text-sm uppercase placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                placeholder="BTC, ETH, SOL…"
                value={form.asset_symbol}
                onChange={e => {
                  setForm(f => ({ ...f, asset_symbol: e.target.value.toUpperCase() }))
                  setPriceNote('')
                }}
                required
              />
              <button
                type="button"
                onClick={fetchPrice}
                disabled={fetchingPrice || !form.asset_symbol}
                className="shrink-0 px-3 py-2 rounded-lg bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white text-xs font-medium transition-colors whitespace-nowrap"
              >
                {fetchingPrice ? '…' : '📈 Precio actual'}
              </button>
            </div>
            {priceNote && (
              <p className={`text-xs mt-1 ${priceNote.includes('no está') || priceNote.includes('Error') ? 'text-red-400' : 'text-emerald-400'}`}>
                {priceNote}
              </p>
            )}
          </div>

          {/* Tipo */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Tipo</label>
            <div className="flex gap-2">
              {(['BUY', 'SELL'] as const).map(t => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setForm(f => ({ ...f, trade_type: t }))}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${
                    form.trade_type === t
                      ? t === 'BUY'
                        ? 'bg-emerald-600 text-white'
                        : 'bg-red-600 text-white'
                      : 'bg-gray-700 text-gray-400 hover:text-white'
                  }`}
                >
                  {t === 'BUY' ? '↑ Compra' : '↓ Venta'}
                </button>
              ))}
            </div>
          </div>

          {/* Total USD — campo principal */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Total a invertir (USD)
              <span className="ml-1 text-gray-600">— o introduce cantidad y precio manualmente</span>
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
              <input
                type="number"
                step="any"
                min="0"
                placeholder="500"
                className="w-full bg-gray-700 text-white rounded-lg pl-7 pr-3 py-2 text-sm placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={displayTotal}
                onChange={e => handleTotalChange(e.target.value)}
              />
            </div>
          </div>

          {/* Cantidad + Precio */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Cantidad (tokens)</label>
              <input
                type="number"
                step="any"
                min="0"
                placeholder="0.005"
                className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={form.quantity || ''}
                onChange={e => handleQtyChange(e.target.value)}
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Precio por token (USD)</label>
              <input
                type="number"
                step="any"
                min="0"
                placeholder="94000"
                className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                value={form.price_usd || ''}
                onChange={e => handlePriceChange(e.target.value)}
                required
              />
            </div>
          </div>

          {/* Fecha */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Fecha y hora</label>
            <input
              type="datetime-local"
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
              value={form.executed_at}
              onChange={e => setForm(f => ({ ...f, executed_at: e.target.value }))}
              required
            />
          </div>

          {/* Notas */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Notas (opcional)</label>
            <input
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm placeholder-gray-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Exchange, estrategia…"
              value={form.notes}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
            />
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 bg-gray-700 hover:bg-gray-600 text-white py-2 rounded-lg text-sm"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white py-2 rounded-lg text-sm font-medium"
            >
              {loading ? 'Guardando…' : 'Registrar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ────────────────────────── Página principal ─────────────────────

export default function PortfolioPage() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [tab, setTab] = useState<'portfolio' | 'history'>('portfolio')
  const [showModal, setShowModal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [sum, tradeList] = await Promise.all([
        portfolioService.getSummary(),
        portfolioService.getTrades({ limit: 100 }),
      ])
      setSummary(sum)
      setTrades(tradeList)
    } catch {
      setError('Error al cargar el portfolio')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleDeleteTrade = async (id: number) => {
    if (!confirm('¿Eliminar esta operación?')) return
    try {
      await portfolioService.deleteTrade(id)
      await fetchData()
    } catch {
      alert('No se pudo eliminar la operación')
    }
  }

  return (
    <div className="min-h-screen bg-gray-900 text-white p-6">
      <div className="max-w-6xl mx-auto">
        {/* Cabecera */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Portfolio</h1>
            <p className="text-gray-400 text-sm mt-1">Seguimiento de tus posiciones y operaciones</p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-xl text-sm font-medium"
          >
            + Registrar operación
          </button>
        </div>

        {loading && (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {error && !loading && (
          <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
            {error}
          </div>
        )}

        {!loading && !error && summary && (
          <>
            {/* Resumen PnL */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-gray-800 rounded-xl p-4">
                <p className="text-xs text-gray-400 mb-1">Invertido</p>
                <p className="text-lg font-bold">{fmtUSD(summary.total_invested_usd)}</p>
              </div>
              <div className="bg-gray-800 rounded-xl p-4">
                <p className="text-xs text-gray-400 mb-1">Valor actual</p>
                <p className="text-lg font-bold">{fmtUSD(summary.total_current_value_usd)}</p>
              </div>
              <div className={`rounded-xl p-4 ${summary.is_profit ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                <p className="text-xs text-gray-400 mb-1">PnL (USD)</p>
                <p className={`text-lg font-bold ${summary.is_profit ? 'text-green-400' : 'text-red-400'}`}>
                  {summary.is_profit ? '+' : ''}{fmtUSD(summary.total_pnl_usd)}
                </p>
              </div>
              <div className={`rounded-xl p-4 ${summary.is_profit ? 'bg-green-900/30' : 'bg-red-900/30'}`}>
                <p className="text-xs text-gray-400 mb-1">PnL (%)</p>
                <p className={`text-lg font-bold ${summary.is_profit ? 'text-green-400' : 'text-red-400'}`}>
                  {summary.is_profit ? '+' : ''}{fmt(summary.total_pnl_pct)}%
                </p>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex gap-2 mb-4">
              <button
                onClick={() => setTab('portfolio')}
                className={`px-4 py-2 rounded-lg text-sm font-medium ${tab === 'portfolio' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
              >
                Posiciones abiertas
              </button>
              <button
                onClick={() => setTab('history')}
                className={`px-4 py-2 rounded-lg text-sm font-medium ${tab === 'history' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'}`}
              >
                Historial ({trades.length})
              </button>
            </div>

            {/* Posiciones */}
            {tab === 'portfolio' && (
              summary.positions.length === 0 ? (
                <div className="bg-gray-800 rounded-xl p-8 text-center text-gray-400">
                  <p className="text-lg mb-2">Sin posiciones abiertas</p>
                  <p className="text-sm">Registra tu primera operación para ver tu portfolio aquí.</p>
                </div>
              ) : (
                <div className="bg-gray-800 rounded-xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-gray-400 text-xs border-b border-gray-700">
                        <th className="text-left px-4 py-3">Activo</th>
                        <th className="text-right px-4 py-3">Cantidad</th>
                        <th className="text-right px-4 py-3">Precio medio</th>
                        <th className="text-right px-4 py-3">Precio actual</th>
                        <th className="text-right px-4 py-3">Valor</th>
                        <th className="text-right px-4 py-3">PnL</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.positions.map(pos => (
                        <tr key={pos.asset_symbol} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              {pos.logo_url && (
                                <img src={pos.logo_url} alt={pos.asset_symbol} className="w-6 h-6 rounded-full" />
                              )}
                              <div>
                                <p className="font-medium">{pos.asset_symbol}</p>
                                <p className="text-xs text-gray-400">{pos.asset_name}</p>
                              </div>
                            </div>
                          </td>
                          <td className="text-right px-4 py-3 font-mono">{fmt(pos.quantity, 6)}</td>
                          <td className="text-right px-4 py-3 font-mono">{fmtUSD(pos.avg_buy_price)}</td>
                          <td className="text-right px-4 py-3 font-mono">{fmtUSD(pos.current_price)}</td>
                          <td className="text-right px-4 py-3 font-mono">{fmtUSD(pos.current_value)}</td>
                          <td className={`text-right px-4 py-3 font-mono ${pos.is_profit ? 'text-green-400' : 'text-red-400'}`}>
                            {pos.is_profit ? '+' : ''}{fmtUSD(pos.pnl_usd)}<br />
                            <span className="text-xs">{pos.is_profit ? '+' : ''}{fmt(pos.pnl_pct)}%</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            )}

            {/* Historial */}
            {tab === 'history' && (
              trades.length === 0 ? (
                <div className="bg-gray-800 rounded-xl p-8 text-center text-gray-400">
                  <p>No hay operaciones registradas.</p>
                </div>
              ) : (
                <div className="bg-gray-800 rounded-xl overflow-hidden">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-gray-400 text-xs border-b border-gray-700">
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
                        <tr key={t.id} className="border-b border-gray-700/50 hover:bg-gray-700/30">
                          <td className="px-4 py-3 text-gray-400">
                            {new Date(t.executed_at).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })}
                          </td>
                          <td className="px-4 py-3 font-medium">{t.asset_symbol}</td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-0.5 rounded text-xs font-medium ${t.trade_type === 'BUY' ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
                              {t.trade_type === 'BUY' ? 'Compra' : 'Venta'}
                            </span>
                          </td>
                          <td className="text-right px-4 py-3 font-mono">{fmt(t.quantity, 6)}</td>
                          <td className="text-right px-4 py-3 font-mono">{fmtUSD(t.price_usd)}</td>
                          <td className="text-right px-4 py-3 font-mono">{fmtUSD(t.total_usd)}</td>
                          <td className="text-right px-4 py-3">
                            <button
                              onClick={() => handleDeleteTrade(t.id)}
                              className="text-gray-500 hover:text-red-400 text-xs"
                            >
                              Eliminar
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            )}
          </>
        )}
      </div>

      {showModal && (
        <AddTradeModal
          onClose={() => setShowModal(false)}
          onAdded={fetchData}
        />
      )}
    </div>
  )
}
