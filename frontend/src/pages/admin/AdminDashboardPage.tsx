/**
 * pages/admin/AdminDashboardPage.tsx — Dashboard de administración.
 *
 * Muestra KPIs globales del sistema: total usuarios, activos,
 * análisis ejecutados, etc.
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { adminService, type AdminStats } from '@/services/adminService'

function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    adminService
      .getStats()
      .then(setStats)
      .catch(() => setError('Error al cargar estadísticas.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-slate-400 animate-pulse">Cargando estadísticas...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
        {error}
      </div>
    )
  }

  const cards = [
    { label: 'Total Usuarios', value: stats?.total_users ?? 0, color: 'text-blue-400' },
    { label: 'Usuarios Activos', value: stats?.active_users ?? 0, color: 'text-green-400' },
    { label: 'Email Verificado', value: stats?.verified_users ?? 0, color: 'text-cyan-400' },
    { label: 'Con 2FA', value: stats?.users_with_2fa ?? 0, color: 'text-purple-400' },
    { label: 'Administradores', value: stats?.admin_users ?? 0, color: 'text-yellow-400' },
    { label: 'Total Criptoactivos', value: stats?.total_assets ?? 0, color: 'text-orange-400' },
    { label: 'Análisis Ejecutados', value: stats?.total_analyses ?? 0, color: 'text-pink-400' },
  ]

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Panel de Administración</h1>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="bg-slate-800 border border-slate-700 rounded-xl p-5"
          >
            <p className="text-xs text-slate-400 uppercase tracking-wider mb-1">
              {card.label}
            </p>
            <p className={`text-3xl font-bold ${card.color}`}>{card.value}</p>
          </div>
        ))}
      </div>

      {/* Quick Links */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Link
          to="/admin/users"
          className="bg-slate-800 border border-slate-700 rounded-xl p-5 hover:bg-slate-700 transition-colors group"
        >
          <h3 className="text-lg font-semibold text-white group-hover:text-blue-400 transition-colors">
            Gestión de Usuarios
          </h3>
          <p className="text-sm text-slate-400 mt-1">
            Ver, editar, activar/desactivar y eliminar usuarios del sistema.
          </p>
        </Link>

        <Link
          to="/admin/assets"
          className="bg-slate-800 border border-slate-700 rounded-xl p-5 hover:bg-slate-700 transition-colors group"
        >
          <h3 className="text-lg font-semibold text-white group-hover:text-blue-400 transition-colors">
            Gestión de Criptoactivos
          </h3>
          <p className="text-sm text-slate-400 mt-1">
            Añadir, editar y eliminar activos criptográficos del catálogo.
          </p>
        </Link>
      </div>
    </div>
  )
}

export default AdminDashboardPage
