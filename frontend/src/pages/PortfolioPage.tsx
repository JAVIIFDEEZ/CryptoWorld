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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
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

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-2xl p-6 w-full max-w-md border border-gray-700">
        <div className="flex justify-between items-center mb-5">
          <h2 className="text-lg font-bold text-white">Registrar operación</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl">✕</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Símbolo</label>
            <input
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm uppercase"
              placeholder="BTC, ETH, SOL…"
              value={form.asset_symbol}
              onChange={e => setForm(f => ({ ...f, asset_symbol: e.target.value.toUpperCase() }))}
              required
            />
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">Tipo</label>
            <select
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm"
              value={form.trade_type}
              onChange={e => setForm(f => ({ ...f, trade_type: e.target.value as 'BUY' | 'SELL' }))}
            >
              <option value="BUY">Compra</option>
              <option value="SELL">Venta</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Cantidad</label>
              <input
                type="number"
                step="any"
                min="0"
                className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm"
                value={form.quantity || ''}
                onChange={e => setForm(f => ({ ...f, quantity: parseFloat(e.target.value) || 0 }))}
                required
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Precio (USD)</label>
              <input
                type="number"
                step="any"
                min="0"
                className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm"
                value={form.price_usd || ''}
                onChange={e => setForm(f => ({ ...f, price_usd: parseFloat(e.target.value) || 0 }))}
                required
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">Fecha y hora</label>
            <input
              type="datetime-local"
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm"
              value={form.executed_at}
              onChange={e => setForm(f => ({ ...f, executed_at: e.target.value }))}
              required
            />
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">Notas (opcional)</label>
            <input
              className="w-full bg-gray-700 text-white rounded-lg px-3 py-2 text-sm"
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
