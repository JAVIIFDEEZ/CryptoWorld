/**
 * pages/admin/AdminAssetsPage.tsx — Gestión de criptoactivos (admin).
 *
 * Tabla con todos los activos, formulario para añadir/editar,
 * y botón para eliminar.
 */

import { useEffect, useState, useCallback } from 'react'
import { adminService, type AdminAsset, type CreateAssetPayload } from '@/services/adminService'

const emptyForm: CreateAssetPayload = {
  symbol: '',
  name: '',
  current_price: '',
  market_cap: '',
  volume_24h: '',
  price_change_24h: '',
  coingecko_id: '',
  logo_url: '',
}

function AdminAssetsPage() {
  const [assets, setAssets] = useState<AdminAsset[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<CreateAssetPayload>(emptyForm)
  const [formError, setFormError] = useState('')
  const [formLoading, setFormLoading] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [actionLoading, setActionLoading] = useState<number | null>(null)

  const fetchAssets = useCallback(() => {
    setLoading(true)
    adminService
      .listAssets()
      .then(setAssets)
      .catch(() => setError('Error al cargar activos.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchAssets()
  }, [fetchAssets])

  function handleFormChange(field: keyof CreateAssetPayload, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }))
  }

  function startEdit(asset: AdminAsset) {
    setEditingId(asset.id)
    setForm({
      symbol: asset.symbol,
      name: asset.name,
      current_price: asset.current_price,
      market_cap: asset.market_cap ?? '',
      volume_24h: asset.volume_24h ?? '',
      price_change_24h: asset.price_change_24h ?? '',
      coingecko_id: asset.coingecko_id ?? '',
      logo_url: asset.logo_url ?? '',
    })
    setShowForm(true)
    setFormError('')
  }

  function cancelForm() {
    setShowForm(false)
    setEditingId(null)
    setForm(emptyForm)
    setFormError('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormLoading(true)
    setFormError('')

    try {
      if (editingId) {
        const updated = await adminService.updateAsset(editingId, {
          name: form.name,
          current_price: form.current_price,
          market_cap: form.market_cap || undefined,
          volume_24h: form.volume_24h || undefined,
          price_change_24h: form.price_change_24h || undefined,
          coingecko_id: form.coingecko_id || undefined,
          logo_url: form.logo_url || undefined,
        })
        setAssets((prev) => prev.map((a) => (a.id === editingId ? updated : a)))
      } else {
        const created = await adminService.createAsset(form)
        setAssets((prev) => [...prev, created])
      }
      cancelForm()
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { error?: string } } }
      setFormError(errorObj?.response?.data?.error ?? 'Error al guardar activo.')
    } finally {
      setFormLoading(false)
    }
  }

  async function handleDelete(assetId: number, symbol: string) {
    if (!window.confirm(`¿Eliminar el activo "${symbol}"?`)) return
    setActionLoading(assetId)
    try {
      await adminService.deleteAsset(assetId)
      setAssets((prev) => prev.filter((a) => a.id !== assetId))
    } catch {
      setError('Error al eliminar activo.')
    } finally {
      setActionLoading(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-slate-400 animate-pulse">Cargando activos...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Gestión de Criptoactivos</h1>
        <button
          onClick={() => {
            cancelForm()
            setShowForm(true)
          }}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg transition-colors"
        >
          + Añadir Activo
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
          {error}
          <button onClick={() => setError('')} className="ml-2 underline">Cerrar</button>
        </div>
      )}

      {/* Formulario de creación/edición */}
      {showForm && (
        <form
          onSubmit={handleSubmit}
          className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-4"
        >
          <h2 className="text-lg font-semibold text-white">
            {editingId ? 'Editar Activo' : 'Nuevo Activo'}
          </h2>

          {formError && (
            <div className="bg-red-500/10 border border-red-500/30 rounded p-2 text-red-400 text-sm">
              {formError}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Símbolo *</label>
              <input
                type="text"
                value={form.symbol}
                onChange={(e) => handleFormChange('symbol', e.target.value)}
                disabled={!!editingId}
                required
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white disabled:opacity-50"
                placeholder="BTC"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Nombre *</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => handleFormChange('name', e.target.value)}
                required
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white"
                placeholder="Bitcoin"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Precio Actual *</label>
              <input
                type="text"
                value={form.current_price}
                onChange={(e) => handleFormChange('current_price', e.target.value)}
                required
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white"
                placeholder="65000.00"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Market Cap</label>
              <input
                type="text"
                value={form.market_cap}
                onChange={(e) => handleFormChange('market_cap', e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white"
                placeholder="1280000000000"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Volumen 24h</label>
              <input
                type="text"
                value={form.volume_24h}
                onChange={(e) => handleFormChange('volume_24h', e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white"
                placeholder="35000000000"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">CoinGecko ID</label>
              <input
                type="text"
                value={form.coingecko_id}
                onChange={(e) => handleFormChange('coingecko_id', e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white"
                placeholder="bitcoin"
              />
            </div>
          </div>

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={formLoading}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-lg disabled:opacity-50 transition-colors"
            >
              {formLoading ? 'Guardando...' : editingId ? 'Actualizar' : 'Crear'}
            </button>
            <button
              type="button"
              onClick={cancelForm}
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 text-sm rounded-lg transition-colors"
            >
              Cancelar
            </button>
          </div>
        </form>
      )}

      {/* Tabla de activos */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-slate-400 uppercase bg-slate-800/50 border-b border-slate-700">
            <tr>
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Símbolo</th>
              <th className="px-4 py-3">Nombre</th>
              <th className="px-4 py-3">Precio</th>
              <th className="px-4 py-3">Market Cap</th>
              <th className="px-4 py-3">Vol. 24h</th>
              <th className="px-4 py-3">CoinGecko ID</th>
              <th className="px-4 py-3">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {assets.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-slate-400">
                  No hay activos registrados.
                </td>
              </tr>
            ) : (
              assets.map((a) => (
                <tr
                  key={a.id}
                  className="border-b border-slate-700/50 hover:bg-slate-800/30 transition-colors"
                >
                  <td className="px-4 py-3 text-slate-300">{a.id}</td>
                  <td className="px-4 py-3 text-white font-medium">{a.symbol}</td>
                  <td className="px-4 py-3 text-slate-300">{a.name}</td>
                  <td className="px-4 py-3 text-slate-300">${Number(a.current_price).toLocaleString()}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {a.market_cap ? `$${Number(a.market_cap).toLocaleString()}` : '—'}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {a.volume_24h ? `$${Number(a.volume_24h).toLocaleString()}` : '—'}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">{a.coingecko_id ?? '—'}</td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => startEdit(a)}
                        className="px-2 py-1 text-xs rounded bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 transition-colors"
                      >
                        Editar
                      </button>
                      <button
                        onClick={() => handleDelete(a.id, a.symbol)}
                        disabled={actionLoading === a.id}
                        className="px-2 py-1 text-xs rounded bg-red-600/30 hover:bg-red-600/50 text-red-300 disabled:opacity-40 transition-colors"
                      >
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default AdminAssetsPage
