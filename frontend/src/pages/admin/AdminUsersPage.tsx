/**
 * pages/admin/AdminUsersPage.tsx — Gestión de usuarios (admin).
 *
 * Tabla con todos los usuarios, acciones de activar/desactivar,
 * cambiar rol y eliminar.
 */

import { useEffect, useState, useCallback } from 'react'
import { adminService, type AdminUser } from '@/services/adminService'
import { useAuth } from '@/hooks/useAuth'

function AdminUsersPage() {
  const { user: currentUser } = useAuth()
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionLoading, setActionLoading] = useState<number | null>(null)

  const fetchUsers = useCallback(() => {
    setLoading(true)
    adminService
      .listUsers()
      .then(setUsers)
      .catch(() => setError('Error al cargar usuarios.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    fetchUsers()
  }, [fetchUsers])

  async function handleToggleActive(userId: number, currentlyActive: boolean) {
    setActionLoading(userId)
    try {
      const updated = await adminService.updateUser(userId, { is_active: !currentlyActive })
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)))
    } catch {
      setError('Error al actualizar usuario.')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleToggleRole(userId: number, currentRole: string) {
    setActionLoading(userId)
    try {
      const newRole = currentRole === 'admin' ? 'user' : 'admin'
      const updated = await adminService.updateUser(userId, { role: newRole as 'user' | 'admin' })
      setUsers((prev) => prev.map((u) => (u.id === userId ? updated : u)))
    } catch {
      setError('Error al cambiar rol.')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleDelete(userId: number, username: string) {
    if (!window.confirm(`¿Estás seguro de eliminar al usuario "${username}"? Esta acción no se puede deshacer.`)) {
      return
    }
    setActionLoading(userId)
    try {
      await adminService.deleteUser(userId)
      setUsers((prev) => prev.filter((u) => u.id !== userId))
    } catch {
      setError('Error al eliminar usuario.')
    } finally {
      setActionLoading(null)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-slate-400 animate-pulse">Cargando usuarios...</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Gestión de Usuarios</h1>
        <span className="text-sm text-slate-400">{users.length} usuarios</span>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
          {error}
          <button onClick={() => setError('')} className="ml-2 underline">Cerrar</button>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-slate-400 uppercase bg-slate-800/50 border-b border-slate-700">
            <tr>
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Usuario</th>
              <th className="px-4 py-3">Email</th>
              <th className="px-4 py-3">Rol</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Email Verificado</th>
              <th className="px-4 py-3">2FA</th>
              <th className="px-4 py-3">Fecha Registro</th>
              <th className="px-4 py-3">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => {
              const isSelf = u.id === currentUser?.id
              const isDisabled = actionLoading === u.id

              return (
                <tr
                  key={u.id}
                  className="border-b border-slate-700/50 hover:bg-slate-800/30 transition-colors"
                >
                  <td className="px-4 py-3 text-slate-300">{u.id}</td>
                  <td className="px-4 py-3 text-white font-medium">{u.username}</td>
                  <td className="px-4 py-3 text-slate-300">{u.email}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        u.role === 'admin'
                          ? 'bg-yellow-500/20 text-yellow-400'
                          : 'bg-slate-600/30 text-slate-300'
                      }`}
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-block w-2 h-2 rounded-full mr-2 ${
                        u.is_active ? 'bg-green-400' : 'bg-red-400'
                      }`}
                    />
                    <span className="text-slate-300">{u.is_active ? 'Activo' : 'Inactivo'}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {u.is_email_verified ? '✓' : '✗'}
                  </td>
                  <td className="px-4 py-3 text-slate-300">
                    {u.is_2fa_enabled ? '✓' : '✗'}
                  </td>
                  <td className="px-4 py-3 text-slate-400 text-xs">
                    {new Date(u.date_joined).toLocaleDateString('es-ES')}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleToggleActive(u.id, u.is_active)}
                        disabled={isDisabled || isSelf}
                        title={isSelf ? 'No puedes desactivarte a ti mismo' : u.is_active ? 'Desactivar' : 'Activar'}
                        className="px-2 py-1 text-xs rounded bg-slate-700 hover:bg-slate-600 text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        {u.is_active ? 'Desactivar' : 'Activar'}
                      </button>
                      <button
                        onClick={() => handleToggleRole(u.id, u.role)}
                        disabled={isDisabled || isSelf}
                        title={isSelf ? 'No puedes cambiar tu propio rol' : 'Cambiar rol'}
                        className="px-2 py-1 text-xs rounded bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        {u.role === 'admin' ? '→ User' : '→ Admin'}
                      </button>
                      <button
                        onClick={() => handleDelete(u.id, u.username)}
                        disabled={isDisabled || isSelf}
                        title={isSelf ? 'No puedes eliminarte a ti mismo' : 'Eliminar'}
                        className="px-2 py-1 text-xs rounded bg-red-600/30 hover:bg-red-600/50 text-red-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                      >
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default AdminUsersPage
