import React, { useState, useEffect } from 'react'
import apiClient from '@/services/api'
import { useAuth } from '@/hooks/useAuth'

export default function AdminDashboardPage() {
  const { user } = useAuth()
  const [users, setUsers] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const [showCreateModal, setShowCreateModal] = useState(false)
  const [formData, setFormData] = useState({ email: '', username: '', password: '' })
  const [createError, setCreateError] = useState('')

  useEffect(() => {
    async function fetchUsers() {
      try {
        const response = await apiClient.get('/admin/users/')
        setUsers(response.data)
      } catch (err) {
        console.error('Error fetching users', err)
      } finally {
        setLoading(false)
      }
    }
    fetchUsers()
  }, [])

  const toggleUserStatus = async (userId: number, currentStatus: boolean) => {
    try {
      await apiClient.patch(`/admin/users/${userId}/`, {
        is_active: !currentStatus
      })
      setUsers(users.map(u => 
        u.id === userId ? { ...u, is_active: !currentStatus } : u
      ))
    } catch (err) {
      console.error('Error toggling status', err)
    }
  }

  const toggleAdminStatus = async (userId: number, currentStatus: boolean) => {
    try {
      await apiClient.patch(`/admin/users/${userId}/`, {
        is_admin: !currentStatus
      })
      setUsers(users.map(u => 
        u.id === userId ? { ...u, is_admin: !currentStatus } : u
      ))
    } catch (err) {
      console.error('Error toggling admin status', err)
    }
  }

  const syncMarketData = async () => {
    try {
      if(confirm('¿Forzar sincronización de datos de mercado? Esto puede tardar.')) {
        await apiClient.post('/admin/market/sync/')
        alert('Sincronización completada.')
      }
    } catch (err) {
      console.error('Error', err)
      alert('Error sincronizando mercado.')
    }
  }

  const handleCreateAdmin = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError('')
    try {
      const resp = await apiClient.post('/admin/users/', formData)
      setUsers([resp.data.user, ...users])
      setShowCreateModal(false)
      setFormData({ email: '', username: '', password: '' })
      alert('Administrador creado existosamente.')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: string } } }
      setCreateError(axiosErr.response?.data?.error || 'Error al crear el administrador.')
    }
  }

  return (
    <div className="container mx-auto p-4 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Panel de Administración</h1>
          <p className="text-slate-400 mt-1">
            Gestión centralizada de usuarios y catálogo cripto. Hola, {user?.username}.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition text-sm flex items-center gap-2"
          >
            Nuevo Admin
          </button>
          <button
            onClick={syncMarketData}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition text-sm flex items-center gap-2"
          >
            Forzar Sinc. Mercado
          </button>
        </div>
      </div>

      <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-700">
          <h2 className="text-xl font-semibold text-white">Usuarios del Sistema</h2>
        </div>
        <div className="p-6">
          {loading ? (
            <div className="text-slate-400">Cargando usuarios...</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-slate-300">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-400">
                    <th className="py-3 px-4 font-medium">ID</th>
                    <th className="py-3 px-4 font-medium">Email</th>
                    <th className="py-3 px-4 font-medium">Username</th>
                    <th className="py-3 px-4 font-medium">Verificado</th>
                    <th className="py-3 px-4 font-medium">2FA</th>
                    <th className="py-3 px-4 font-medium">Estado</th>
                    <th className="py-3 px-4 font-medium text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map(u => (
                    <tr key={u.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                      <td className="py-3 px-4">{u.id}</td>
                      <td className="py-3 px-4">{u.email}</td>
                      <td className="py-3 px-4">{u.username} {u.is_admin && <span className="text-xs bg-fuchsia-900/50 text-fuchsia-300 px-2 py-0.5 rounded-full ml-2">Admin</span>}</td>
                      <td className="py-3 px-4">
                        {u.is_email_verified ? 'Sí' : 'No'}
                      </td>
                      <td className="py-3 px-4">
                        {u.is_2fa_enabled ? 'Sí' : 'No'}
                      </td>
                      <td className="py-3 px-4">
                        <span className={`px-2 py-1 rounded-full text-xs font-semibold ${u.is_active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                          {u.is_active ? 'Activo' : 'Bloqueado'}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right space-x-2">
                        <button 
                          onClick={() => toggleAdminStatus(u.id, u.is_admin)}
                          className={`text-sm px-3 py-1 rounded transition-colors ${
                            u.is_admin ? 'bg-fuchsia-500/10 text-fuchsia-400 hover:bg-fuchsia-500/20' : 'bg-slate-500/10 text-slate-400 hover:bg-slate-500/20'
                          }`}
                        >
                          {u.is_admin ? 'Quitar Admin' : 'Hacer Admin'}
                        </button>
                        <button 
                          onClick={() => toggleUserStatus(u.id, u.is_active)}
                          disabled={u.is_admin}
                          className={`text-sm px-3 py-1 rounded transition-colors ${
                            u.is_admin ? 'opacity-50 cursor-not-allowed bg-slate-700 text-slate-400' : 
                            u.is_active ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20' : 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20'
                          }`}
                        >
                          {u.is_active ? 'Bloquear' : 'Desbloquear'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Modal Nuevo Admin */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 w-full max-w-md shadow-2xl">
            <h2 className="text-xl font-bold text-white mb-4">Crear Nuevo Administrador</h2>
            {createError && (
              <div className="bg-red-500/20 text-red-300 px-4 py-3 rounded-lg mb-4 text-sm border border-red-500/30">
                {createError}
              </div>
            )}
            <form onSubmit={handleCreateAdmin} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Email</label>
                <input
                  type="email"
                  required
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 text-white focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500"
                  placeholder="admin@cryptoworld.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Username</label>
                <input
                  type="text"
                  required
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 text-white focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500"
                  placeholder="admin"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1">Contraseña</label>
                <input
                  type="password"
                  required
                  autoComplete="new-password"
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 text-white focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500"
                  placeholder="********"
                />
              </div>
              
              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 text-slate-400 hover:text-white transition"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition font-medium"
                >
                  Crear y Conceder Permisos
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
