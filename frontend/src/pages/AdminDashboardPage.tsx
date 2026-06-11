/**
 * pages/AdminDashboardPage.tsx — Panel de administración.
 *
 * Funcionalidad:
 *   - KPIs: usuarios totales, verificados, admins y bloqueados.
 *   - Sincronización manual del catálogo de mercado (CoinGecko).
 *   - Tabla de usuarios con búsqueda, paginación y acciones por fila:
 *     conceder/revocar admin, bloquear/desbloquear y reenviar verificación.
 *
 * Todas las acciones destructivas pasan por ConfirmDialog (nunca
 * window.confirm) y el feedback se da con toasts. El propio admin no
 * puede bloquearse ni degradarse (el backend también lo impide).
 */

import { useEffect, useMemo, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import {
  adminService,
  type AdminUser,
  type MarketSyncResult,
  type SystemHealth,
} from '@/services/adminService'
import { useToast } from '@/components/ui/Toast'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import PasswordInput from '@/components/ui/PasswordInput'

const PAGE_SIZE = 10

type PendingAction =
  | { kind: 'toggle-admin'; user: AdminUser }
  | { kind: 'toggle-active'; user: AdminUser }
  | { kind: 'sync-market' }

function formatDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('es-ES', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function StatCard({ label, value, accent }: { label: string; value: number; accent?: string }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
      <p className="text-xs text-slate-500 uppercase">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${accent ?? 'text-white'}`}>{value}</p>
    </div>
  )
}

function HealthChip({ label, ok, detail }: { label: string; ok: boolean; detail?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${
        ok ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'
      }`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-emerald-400' : 'bg-red-400'}`} />
      {label}
      {detail && <span className="text-slate-400 font-normal">· {detail}</span>}
    </span>
  )
}

/**
 * Estado del sistema: chips de BD/cache/broker y modo del email.
 * Si el email está en modo consola, banner explicando que los emails
 * NO se entregan y qué variable falta — el fallo más silencioso del deploy.
 */
function SystemHealthPanel({ health }: { health: SystemHealth | null }) {
  if (!health) return null

  const { components } = health
  const emailReal = components.email_backend !== 'console'

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-white">Estado del sistema</h3>
        <div className="flex flex-wrap gap-2">
          <HealthChip label="Base de datos" ok={components.database === 'ok'} />
          <HealthChip label="Cache Redis" ok={components.cache === 'ok'} />
          <HealthChip label="Broker Celery" ok={components.celery_broker === 'ok'} />
          <HealthChip label="Email" ok={emailReal} detail={components.email_backend} />
        </div>
      </div>

      {!emailReal && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-3">
          <p className="text-sm text-amber-300 font-medium">
            Los emails NO se están entregando: el servidor está en modo consola.
          </p>
          <p className="text-xs text-amber-200/70 mt-1">
            Los envíos (verificación, reset, alertas) solo se imprimen en los logs del backend.
            Define <code className="text-amber-200">SENDGRID_API_KEY</code> (o las variables{' '}
            <code className="text-amber-200">EMAIL_*</code> de SMTP) junto a{' '}
            <code className="text-amber-200">DEFAULT_FROM_EMAIL</code> y{' '}
            <code className="text-amber-200">FRONTEND_URL</code> en los servicios web y worker,
            y redespliega. Guía completa en DEPLOY.md.
          </p>
        </div>
      )}

      {components.celery_broker === 'error' && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-3">
          <p className="text-sm text-amber-300 font-medium">
            Broker Celery inaccesible: alertas y sincronización periódica detenidas.
          </p>
          <p className="text-xs text-amber-200/70 mt-1">
            Los emails salen igualmente por el fallback síncrono, pero revisa que{' '}
            <code className="text-amber-200">REDIS_URL</code> esté vinculada y el servicio worker en marcha.
          </p>
        </div>
      )}
    </div>
  )
}

export default function AdminDashboardPage() {
  const { user: currentUser } = useAuth()
  const { showToast } = useToast()

  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState(false)
  const [health, setHealth] = useState<SystemHealth | null>(null)

  // Búsqueda y paginación (client-side)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)

  // Confirmaciones y acciones en curso
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null)
  const [isExecutingAction, setIsExecutingAction] = useState(false)
  const [resendingUserId, setResendingUserId] = useState<number | null>(null)

  // Sincronización de mercado
  const [syncResult, setSyncResult] = useState<MarketSyncResult | null>(null)
  const [isSyncing, setIsSyncing] = useState(false)
  const [perPage, setPerPage] = useState(100)

  // Modal de creación de admin
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [formData, setFormData] = useState({ email: '', username: '', password: '' })
  const [createError, setCreateError] = useState('')
  const [isCreating, setIsCreating] = useState(false)

  useEffect(() => {
    let cancelled = false
    adminService
      .listUsers()
      .then((data) => {
        if (!cancelled) setUsers(data)
      })
      .catch(() => {
        if (!cancelled) setLoadError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    // Estado de infraestructura: informativo, no bloquea el panel si falla
    adminService
      .getSystemHealth()
      .then((data) => {
        if (!cancelled) setHealth(data)
      })
      .catch(() => {
        // El panel funciona igual sin el health check
      })
    return () => {
      cancelled = true
    }
  }, [])

  // ── Derivados: filtro + paginación ─────────────────────────────────

  const filteredUsers = useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return users
    return users.filter(
      (u) => u.email.toLowerCase().includes(term) || u.username.toLowerCase().includes(term),
    )
  }, [users, search])

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const pageUsers = filteredUsers.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)

  const stats = useMemo(
    () => ({
      total: users.length,
      verified: users.filter((u) => u.is_email_verified).length,
      admins: users.filter((u) => u.is_admin).length,
      blocked: users.filter((u) => !u.is_active).length,
    }),
    [users],
  )

  // ── Acciones ───────────────────────────────────────────────────────

  const replaceUser = (updated: AdminUser) => {
    setUsers((prev) => prev.map((u) => (u.id === updated.id ? updated : u)))
  }

  const executePendingAction = async () => {
    if (!pendingAction) return
    setIsExecutingAction(true)
    try {
      if (pendingAction.kind === 'toggle-admin') {
        const u = pendingAction.user
        const updated = await adminService.updateUser(u.id, { is_admin: !u.is_admin })
        replaceUser(updated)
        showToast(
          updated.is_admin
            ? `${updated.username} ahora es administrador.`
            : `Permisos de administrador revocados a ${updated.username}.`,
          'success',
        )
      } else if (pendingAction.kind === 'toggle-active') {
        const u = pendingAction.user
        const updated = await adminService.updateUser(u.id, { is_active: !u.is_active })
        replaceUser(updated)
        showToast(
          updated.is_active
            ? `Cuenta de ${updated.username} desbloqueada.`
            : `Cuenta de ${updated.username} bloqueada.`,
          'success',
        )
      } else {
        setIsSyncing(true)
        setSyncResult(null)
        const result = await adminService.syncMarket(perPage)
        setSyncResult(result)
        showToast('Sincronización de mercado completada.', 'success')
      }
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: string } } }
      showToast(axiosErr.response?.data?.error || 'La operación ha fallado.', 'error')
    } finally {
      setIsExecutingAction(false)
      setIsSyncing(false)
      setPendingAction(null)
    }
  }

  const handleResendVerification = async (u: AdminUser) => {
    setResendingUserId(u.id)
    try {
      const { message } = await adminService.resendVerification(u.id)
      showToast(message, 'success')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: string } } }
      showToast(axiosErr.response?.data?.error || 'No se pudo reenviar la verificación.', 'error')
    } finally {
      setResendingUserId(null)
    }
  }

  const handleCreateAdmin = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreateError('')
    setIsCreating(true)
    try {
      const newUser = await adminService.createAdmin(formData)
      setUsers((prev) => [newUser, ...prev])
      setShowCreateModal(false)
      setFormData({ email: '', username: '', password: '' })
      showToast(`Administrador ${newUser.username} creado correctamente.`, 'success')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: string } } }
      setCreateError(axiosErr.response?.data?.error || 'Error al crear el administrador.')
    } finally {
      setIsCreating(false)
    }
  }

  // ── Texto del diálogo de confirmación según la acción pendiente ────

  const confirmProps = useMemo(() => {
    if (!pendingAction) return null
    if (pendingAction.kind === 'toggle-admin') {
      const u = pendingAction.user
      return u.is_admin
        ? {
            title: 'Revocar permisos de administrador',
            description: (
              <>
                <strong className="text-white">{u.username}</strong> ({u.email}) perderá el acceso al
                panel de administración. ¿Continuar?
              </>
            ),
            confirmLabel: 'Revocar permisos',
            tone: 'danger' as const,
          }
        : {
            title: 'Conceder permisos de administrador',
            description: (
              <>
                <strong className="text-white">{u.username}</strong> ({u.email}) tendrá acceso completo
                al panel de administración, incluida la gestión de usuarios. ¿Continuar?
              </>
            ),
            confirmLabel: 'Hacer administrador',
            tone: 'primary' as const,
          }
    }
    if (pendingAction.kind === 'toggle-active') {
      const u = pendingAction.user
      return u.is_active
        ? {
            title: 'Bloquear cuenta',
            description: (
              <>
                <strong className="text-white">{u.username}</strong> ({u.email}) no podrá iniciar sesión
                hasta que se desbloquee la cuenta. ¿Continuar?
              </>
            ),
            confirmLabel: 'Bloquear',
            tone: 'danger' as const,
          }
        : {
            title: 'Desbloquear cuenta',
            description: (
              <>
                <strong className="text-white">{u.username}</strong> ({u.email}) podrá volver a iniciar
                sesión. ¿Continuar?
              </>
            ),
            confirmLabel: 'Desbloquear',
            tone: 'primary' as const,
          }
    }
    return {
      title: 'Sincronizar catálogo de mercado',
      description: (
        <>
          Se descargarán los <strong className="text-white">{perPage}</strong> activos con mayor
          capitalización desde CoinGecko. La operación puede tardar ~10 segundos.
        </>
      ),
      confirmLabel: 'Sincronizar',
      tone: 'primary' as const,
    }
  }, [pendingAction, perPage])

  return (
    <div className="container mx-auto p-4 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Panel de Administración</h1>
          <p className="text-slate-400 mt-1">
            Gestión centralizada de usuarios y catálogo cripto.
          </p>
        </div>
        <div>
          <button
            onClick={() => setShowCreateModal(true)}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition text-sm font-medium"
          >
            + Nuevo administrador
          </button>
        </div>
      </div>

      {/* Tarjetas de resumen */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard label="Usuarios registrados" value={stats.total} />
        <StatCard label="Emails verificados" value={stats.verified} accent="text-emerald-400" />
        <StatCard label="Administradores" value={stats.admins} accent="text-fuchsia-400" />
        <StatCard label="Bloqueados" value={stats.blocked} accent="text-red-400" />
      </div>

      {/* Estado de la infraestructura (BD, Redis, Celery, email) */}
      <SystemHealthPanel health={health} />

      {/* Panel de sincronización */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-1">Sincronización de mercado</h3>
        <p className="text-xs text-slate-400 mb-4">
          Descarga el catálogo de criptomonedas desde CoinGecko y actualiza precios, logos y market caps en la base de datos.
          Genera además un snapshot de serie temporal inmutable por cada activo.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs text-slate-400 flex items-center gap-2">
            Top
            <input
              type="number"
              min={10}
              max={250}
              step={10}
              value={perPage}
              onChange={(e) => setPerPage(Math.min(250, Math.max(10, Number(e.target.value))))}
              className="w-20 bg-slate-700 border border-slate-600 rounded px-2 py-1 text-white text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
            activos por market cap
          </label>
          <button
            onClick={() => setPendingAction({ kind: 'sync-market' })}
            disabled={isSyncing}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-900 disabled:cursor-not-allowed text-white rounded-lg transition text-sm"
          >
            {isSyncing ? 'Sincronizando...' : 'Sincronizar ahora'}
          </button>
        </div>

        {/* Resultado del último sync */}
        {syncResult && (
          <div className="mt-4 pt-4 border-t border-slate-700">
            <p className="text-xs font-semibold text-slate-400 mb-3">Resultado de la última sincronización</p>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-2xl font-bold text-green-400">{syncResult.assets_created}</p>
                <p className="text-xs text-slate-400 mt-1">Creados</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-blue-400">{syncResult.assets_updated}</p>
                <p className="text-xs text-slate-400 mt-1">Actualizados</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-purple-400">{syncResult.snapshots_created}</p>
                <p className="text-xs text-slate-400 mt-1">Snapshots</p>
              </div>
            </div>
            {syncResult.errors.length > 0 && (
              <div className="mt-3 bg-red-900/30 border border-red-700 rounded-lg px-3 py-2">
                <p className="text-xs text-red-400">
                  {syncResult.errors.length} error(es): {syncResult.errors.slice(0, 3).join(', ')}
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Tabla de usuarios */}
      <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-700 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h2 className="text-xl font-semibold text-white">Usuarios del Sistema</h2>
          <div className="relative">
            <svg
              xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"
              className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
            <input
              type="search"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              placeholder="Buscar por email o usuario..."
              aria-label="Buscar usuarios"
              className="bg-slate-900 border border-slate-700 rounded-lg pl-9 pr-4 py-2 text-sm text-white w-full sm:w-72 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
            />
          </div>
        </div>

        <div className="p-6">
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-12 bg-slate-700/40 rounded-lg animate-pulse" />
              ))}
            </div>
          ) : loadError ? (
            <p className="text-red-400 text-sm">
              No se pudo cargar la lista de usuarios. Recarga la página o inténtalo más tarde.
            </p>
          ) : filteredUsers.length === 0 ? (
            <p className="text-slate-400 text-sm text-center py-8">
              {search ? `Sin resultados para "${search}".` : 'No hay usuarios registrados.'}
            </p>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-slate-300">
                  <thead>
                    <tr className="border-b border-slate-700 text-slate-400 text-sm">
                      <th className="py-3 px-4 font-medium">Usuario</th>
                      <th className="py-3 px-4 font-medium">Email</th>
                      <th className="py-3 px-4 font-medium">Registro</th>
                      <th className="py-3 px-4 font-medium">Verificado</th>
                      <th className="py-3 px-4 font-medium">2FA</th>
                      <th className="py-3 px-4 font-medium">Estado</th>
                      <th className="py-3 px-4 font-medium text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {pageUsers.map((u) => {
                      const isSelf = u.id === currentUser?.id
                      return (
                        <tr key={u.id} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                          <td className="py-3 px-4 whitespace-nowrap">
                            {u.username}
                            {u.is_admin && (
                              <span className="text-xs bg-fuchsia-900/50 text-fuchsia-300 px-2 py-0.5 rounded-full ml-2">Admin</span>
                            )}
                            {isSelf && (
                              <span className="text-xs bg-blue-900/50 text-blue-300 px-2 py-0.5 rounded-full ml-2">Tú</span>
                            )}
                          </td>
                          <td className="py-3 px-4">{u.email}</td>
                          <td className="py-3 px-4 whitespace-nowrap text-sm text-slate-400">{formatDate(u.date_joined)}</td>
                          <td className="py-3 px-4">
                            {u.is_email_verified ? (
                              <span className="text-emerald-400 text-sm">Sí</span>
                            ) : (
                              <button
                                onClick={() => handleResendVerification(u)}
                                disabled={resendingUserId === u.id}
                                title="Reenviar email de verificación"
                                className="text-xs bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 disabled:opacity-50 px-2.5 py-1 rounded transition-colors"
                              >
                                {resendingUserId === u.id ? 'Enviando...' : 'No · Reenviar'}
                              </button>
                            )}
                          </td>
                          <td className="py-3 px-4 text-sm">{u.is_2fa_enabled ? 'Sí' : 'No'}</td>
                          <td className="py-3 px-4">
                            <span className={`px-2 py-1 rounded-full text-xs font-semibold ${u.is_active ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
                              {u.is_active ? 'Activo' : 'Bloqueado'}
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right whitespace-nowrap space-x-2">
                            <button
                              onClick={() => setPendingAction({ kind: 'toggle-admin', user: u })}
                              disabled={isSelf}
                              title={isSelf ? 'No puedes modificar tus propios permisos' : undefined}
                              className={`text-sm px-3 py-1 rounded transition-colors ${
                                isSelf
                                  ? 'opacity-40 cursor-not-allowed bg-slate-700 text-slate-400'
                                  : u.is_admin
                                    ? 'bg-fuchsia-500/10 text-fuchsia-400 hover:bg-fuchsia-500/20'
                                    : 'bg-slate-500/10 text-slate-400 hover:bg-slate-500/20'
                              }`}
                            >
                              {u.is_admin ? 'Quitar Admin' : 'Hacer Admin'}
                            </button>
                            <button
                              onClick={() => setPendingAction({ kind: 'toggle-active', user: u })}
                              disabled={isSelf}
                              title={isSelf ? 'No puedes bloquear tu propia cuenta' : undefined}
                              className={`text-sm px-3 py-1 rounded transition-colors ${
                                isSelf
                                  ? 'opacity-40 cursor-not-allowed bg-slate-700 text-slate-400'
                                  : u.is_active
                                    ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                                    : 'bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20'
                              }`}
                            >
                              {u.is_active ? 'Bloquear' : 'Desbloquear'}
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {/* Paginación */}
              {totalPages > 1 && (
                <div className="flex items-center justify-between mt-4 pt-4 border-t border-slate-700">
                  <p className="text-xs text-slate-500">
                    {filteredUsers.length} usuario(s) · página {currentPage} de {totalPages}
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPage(currentPage - 1)}
                      disabled={currentPage <= 1}
                      className="text-sm px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-slate-200 transition-colors"
                    >
                      Anterior
                    </button>
                    <button
                      onClick={() => setPage(currentPage + 1)}
                      disabled={currentPage >= totalPages}
                      className="text-sm px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-slate-200 transition-colors"
                    >
                      Siguiente
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Diálogo de confirmación de acciones */}
      {confirmProps && (
        <ConfirmDialog
          open={!!pendingAction}
          title={confirmProps.title}
          description={confirmProps.description}
          confirmLabel={confirmProps.confirmLabel}
          tone={confirmProps.tone}
          isLoading={isExecutingAction}
          onConfirm={executePendingAction}
          onCancel={() => setPendingAction(null)}
        />
      )}

      {/* Modal Nuevo Admin */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true">
          <div className="bg-slate-800 p-6 rounded-xl border border-slate-700 w-full max-w-md shadow-2xl">
            <h2 className="text-xl font-bold text-white mb-1">Crear nuevo administrador</h2>
            <p className="text-sm text-slate-400 mb-4">
              La cuenta se crea con el email verificado y acceso completo al panel.
            </p>
            {createError && (
              <div className="bg-red-500/20 text-red-300 px-4 py-3 rounded-lg mb-4 text-sm border border-red-500/30">
                {createError}
              </div>
            )}
            <form onSubmit={handleCreateAdmin} className="space-y-4">
              <div>
                <label htmlFor="admin-email" className="block text-sm font-medium text-slate-300 mb-1">Email</label>
                <input
                  id="admin-email"
                  type="email"
                  required
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 text-white focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500 outline-none"
                  placeholder="admin@cryptoworld.com"
                />
              </div>
              <div>
                <label htmlFor="admin-username" className="block text-sm font-medium text-slate-300 mb-1">Nombre de usuario</label>
                <input
                  id="admin-username"
                  type="text"
                  required
                  minLength={3}
                  value={formData.username}
                  onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2 text-white focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500 outline-none"
                  placeholder="admin"
                />
              </div>
              <div>
                <label htmlFor="admin-password" className="block text-sm font-medium text-slate-300 mb-1">Contraseña</label>
                <PasswordInput
                  id="admin-password"
                  value={formData.password}
                  onChange={(password) => setFormData({ ...formData, password })}
                  required
                  autoComplete="new-password"
                  placeholder="Mínimo 8 caracteres"
                />
                <p className="text-xs text-slate-500 mt-1">
                  Debe cumplir la política de contraseñas (longitud mínima, no común, no solo números).
                </p>
              </div>

              <div className="flex justify-end gap-3 pt-4">
                <button
                  type="button"
                  onClick={() => {
                    setShowCreateModal(false)
                    setCreateError('')
                  }}
                  className="px-4 py-2 text-slate-400 hover:text-white transition"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={isCreating}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-800 text-white rounded-lg transition font-medium"
                >
                  {isCreating ? 'Creando...' : 'Crear administrador'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
