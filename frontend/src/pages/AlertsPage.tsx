/**
 * pages/AlertsPage.tsx — Gestión de alertas de precio.
 *
 * El usuario puede crear alertas ABOVE/BELOW para cualquier activo.
 * Las alertas son evaluadas por el worker Celery cada 2 minutos.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  alertsService,
  type PriceAlert,
  type CreateAlertPayload,
} from '../services/alertsService'
import EmptyState from '../components/ui/EmptyState'
import { apiErrorMessage } from '@/utils/apiError'

const IconBell = () => (
  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.85 23.85 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m6.714 0a3 3 0 1 1-6.714 0m6.714 0a24.2 24.2 0 0 1-6.714 0" />
  </svg>
)

// ────────────────────────── Modal crear alerta ────────────────────

const EMPTY_FORM: CreateAlertPayload = {
  asset_symbol: '',
  condition: 'ABOVE',
  threshold_price: 0,
  notes: '',
}

function CreateAlertModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const [form, setForm] = useState<CreateAlertPayload>(EMPTY_FORM)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await alertsService.createAlert(form)
      onCreated()
      onClose()
    } catch (err: unknown) {
      const msg = apiErrorMessage(err)
      setError(msg ?? 'Error al crear la alerta')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 rounded-2xl p-6 w-full max-w-md border border-slate-700">
        <div className="flex justify-between items-center mb-5">
          <h2 className="text-lg font-bold text-white">Nueva alerta de precio</h2>
          <button onClick={onClose} aria-label="Cerrar" className="text-slate-400 hover:text-white text-xl">×</button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Símbolo del activo</label>
            <input
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm uppercase"
              placeholder="BTC, ETH, SOL…"
              value={form.asset_symbol}
              onChange={e => setForm(f => ({ ...f, asset_symbol: e.target.value.toUpperCase() }))}
              required
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Condición</label>
            <select
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm"
              value={form.condition}
              onChange={e => setForm(f => ({ ...f, condition: e.target.value as 'ABOVE' | 'BELOW' }))}
            >
              <option value="ABOVE">Precio sube por encima de…</option>
              <option value="BELOW">Precio cae por debajo de…</option>
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Precio objetivo (USD)</label>
            <input
              type="number"
              step="any"
              min="0"
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm"
              placeholder="ej: 100000"
              value={form.threshold_price || ''}
              onChange={e => setForm(f => ({ ...f, threshold_price: parseFloat(e.target.value) || 0 }))}
              required
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Nota (opcional)</label>
            <input
              className="w-full bg-slate-700 text-white rounded-lg px-3 py-2 text-sm"
              placeholder="Motivo de la alerta…"
              value={form.notes}
              onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
            />
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          <div className="flex gap-3 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 bg-slate-700 hover:bg-slate-600 text-white py-2 rounded-lg text-sm"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 text-white py-2 rounded-lg text-sm font-medium"
            >
              {loading ? 'Creando…' : 'Crear alerta'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ────────────────────────── Tarjeta de alerta ─────────────────────

function AlertCard({
  alert,
  onToggle,
  onDelete,
}: {
  alert: PriceAlert
  onToggle: (id: number) => void
  onDelete: (id: number) => void
}) {
  const fmtUSD = (n: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)

  return (
    <div className={`bg-slate-800 rounded-xl p-4 border ${alert.is_triggered ? 'border-yellow-500/50' : alert.is_active ? 'border-slate-700' : 'border-slate-700/30 opacity-60'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-bold text-white">{alert.asset_symbol}</span>
            <span className={`px-2 py-0.5 rounded text-xs font-medium ${alert.condition === 'ABOVE' ? 'bg-green-900/40 text-green-400' : 'bg-red-900/40 text-red-400'}`}>
              {alert.condition === 'ABOVE' ? '↑ Por encima' : '↓ Por debajo'}
            </span>
            {alert.is_triggered && (
              <span className="px-2 py-0.5 rounded text-xs font-medium bg-yellow-900/40 text-yellow-400">
                Disparada
              </span>
            )}
          </div>
          <p className="text-sm text-slate-300">
            {alert.condition === 'ABOVE' ? 'Alerta cuando supere' : 'Alerta cuando caiga a'}{' '}
            <span className="font-mono font-bold text-white">{fmtUSD(alert.threshold_price)}</span>
          </p>
          {alert.current_price != null && (
            <p className="text-xs text-slate-400 mt-0.5">
              Precio actual: <span className="font-mono">{fmtUSD(alert.current_price)}</span>
            </p>
          )}
          {alert.notes && <p className="text-xs text-slate-500 mt-1">{alert.notes}</p>}
          {alert.triggered_at && (
            <p className="text-xs text-yellow-400 mt-1">
              Disparada: {new Date(alert.triggered_at).toLocaleString('es-ES')}
            </p>
          )}
        </div>

        <div className="flex gap-2 shrink-0 items-center">
          <button
            onClick={() => onToggle(alert.id)}
            title={alert.is_active ? 'Desactivar' : 'Activar'}
            className={`h-8 px-3 rounded-lg flex items-center justify-center text-xs font-medium whitespace-nowrap ${alert.is_active ? 'bg-blue-900/40 text-blue-400 hover:bg-blue-900/70' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'}`}
          >
            {alert.is_active ? 'Activada' : 'Desactivar'}
          </button>
          <button
            onClick={() => onDelete(alert.id)}
            title="Eliminar alerta"
            aria-label="Eliminar alerta"
            className="w-8 h-8 rounded-lg flex items-center justify-center text-sm bg-slate-700 text-slate-400 hover:bg-red-900/40 hover:text-red-400"
          >
            ×
          </button>
        </div>
      </div>
    </div>
  )
}

// ────────────────────────── Página principal ─────────────────────

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<PriceAlert[]>([])
  const [showModal, setShowModal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<'all' | 'active' | 'triggered'>('all')

  const fetchAlerts = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await alertsService.getAlerts()
      setAlerts(data)
    } catch {
      setError('Error al cargar las alertas')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAlerts()
  }, [fetchAlerts])

  const handleToggle = async (id: number) => {
    try {
      const updated = await alertsService.toggleAlert(id)
      setAlerts(prev => prev.map(a => (a.id === id ? updated : a)))
    } catch {
      alert('Error al cambiar estado de la alerta')
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('¿Eliminar esta alerta?')) return
    try {
      await alertsService.deleteAlert(id)
      setAlerts(prev => prev.filter(a => a.id !== id))
    } catch {
      alert('Error al eliminar la alerta')
    }
  }

  const filtered = alerts.filter(a => {
    if (filter === 'active') return a.is_active && !a.is_triggered
    if (filter === 'triggered') return a.is_triggered
    return true
  })

  const triggeredCount = alerts.filter(a => a.is_triggered).length
  const activeCount = alerts.filter(a => a.is_active && !a.is_triggered).length

  return (
    <div className="max-w-4xl mx-auto">
        {/* Cabecera */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold">Alertas de precio</h1>
            <p className="text-slate-400 text-sm mt-1">
              Evaluadas automáticamente cada 2 minutos
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="bg-yellow-600 hover:bg-yellow-500 text-white px-4 py-2 rounded-xl text-sm font-medium"
          >
            + Nueva alerta
          </button>
        </div>

        {/* Estadísticas rápidas */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-slate-800 rounded-xl p-4 text-center">
            <p className="text-2xl font-bold">{alerts.length}</p>
            <p className="text-xs text-slate-400 mt-1">Total</p>
          </div>
          <div className="bg-slate-800 rounded-xl p-4 text-center">
            <p className="text-2xl font-bold text-blue-400">{activeCount}</p>
            <p className="text-xs text-slate-400 mt-1">Activas</p>
          </div>
          <div className="bg-slate-800 rounded-xl p-4 text-center">
            <p className="text-2xl font-bold text-yellow-400">{triggeredCount}</p>
            <p className="text-xs text-slate-400 mt-1">Disparadas</p>
          </div>
        </div>

        {/* Filtros */}
        <div className="flex gap-2 mb-4">
          {(['all', 'active', 'triggered'] as const).map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium ${filter === f ? 'bg-yellow-600 text-white' : 'bg-slate-800 text-slate-400 hover:text-white'}`}
            >
              {f === 'all' ? 'Todas' : f === 'active' ? 'Activas' : 'Disparadas'}
            </button>
          ))}
        </div>

        {loading && (
          <div className="flex justify-center py-20">
            <div className="w-8 h-8 border-2 border-yellow-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {error && !loading && (
          <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
            {error}
          </div>
        )}

        {!loading && !error && filtered.length === 0 && (
          <EmptyState
            icon={<IconBell />}
            title={filter === 'all' ? 'No hay alertas configuradas' : 'No hay alertas en esta categoría'}
            description={filter === 'all' ? 'Crea tu primera alerta para recibir notificaciones automáticas.' : undefined}
          />
        )}

        {!loading && !error && (
          <div className="space-y-3">
            {filtered.map(alert => (
              <AlertCard
                key={alert.id}
                alert={alert}
                onToggle={handleToggle}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}

      {showModal && (
        <CreateAlertModal
          onClose={() => setShowModal(false)}
          onCreated={fetchAlerts}
        />
      )}
    </div>
  )
}
