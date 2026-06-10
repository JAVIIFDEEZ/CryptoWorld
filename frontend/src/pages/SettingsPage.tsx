/**
 * pages/SettingsPage.tsx — Ajustes de cuenta.
 *
 * Secciones:
 *   - Perfil: datos de la cuenta con estado de verificación y antigüedad.
 *   - Preferencias: moneda fiat persistida en el backend (PATCH /auth/me/).
 *   - Notificaciones: toggles persistidos (alertas de precio, resúmenes).
 *   - Seguridad: cambio de contraseña y acceso a la gestión de 2FA.
 *   - Zona de peligro: eliminación de cuenta con confirmación por contraseña.
 *
 * Las preferencias se guardan automáticamente al cambiarlas (con feedback
 * por toast); el resto de acciones usa formularios explícitos.
 */

import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import {
  authService,
  type PreferredCurrency,
  type UserMeResponse,
} from '@/services/authService'
import { useToast } from '@/components/ui/Toast'
import PasswordInput from '@/components/ui/PasswordInput'

const CURRENCY_OPTIONS: { value: PreferredCurrency; label: string }[] = [
  { value: 'usd', label: 'Dólar Estadounidense (USD - $)' },
  { value: 'eur', label: 'Euro (EUR - €)' },
  { value: 'gbp', label: 'Libra Esterlina (GBP - £)' },
]

/** Toggle accesible reutilizado por las dos preferencias de notificación. */
function ToggleSwitch({
  checked,
  disabled,
  onChange,
  label,
  description,
}: {
  checked: boolean
  disabled?: boolean
  onChange: (value: boolean) => void
  label: string
  description: string
}) {
  return (
    <label className={`flex items-center justify-between gap-4 ${disabled ? 'opacity-60' : 'cursor-pointer'}`}>
      <div>
        <span className="block text-sm font-medium text-slate-300">{label}</span>
        <span className="block text-xs text-slate-500">{description}</span>
      </div>
      <div className="relative shrink-0">
        <input
          type="checkbox"
          className="sr-only peer"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-blue-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
      </div>
    </label>
  )
}

function VerifiedBadge({ verified }: { verified: boolean }) {
  return verified ? (
    <span className="inline-flex items-center gap-1 text-xs font-medium bg-emerald-500/15 text-emerald-400 px-2 py-0.5 rounded-full">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-3.5 h-3.5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      Verificado
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs font-medium bg-amber-500/15 text-amber-400 px-2 py-0.5 rounded-full">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-3.5 h-3.5">
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
      </svg>
      Sin verificar
    </span>
  )
}

export default function SettingsPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { showToast } = useToast()

  // Perfil y preferencias cargadas del backend (fuente de verdad)
  const [me, setMe] = useState<UserMeResponse | null>(null)
  const [isLoadingMe, setIsLoadingMe] = useState(true)
  const [isSavingPrefs, setIsSavingPrefs] = useState(false)
  const [isResendingVerification, setIsResendingVerification] = useState(false)

  // Modal para borrar cuenta
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteError, setDeleteError] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)

  // Cambio de contraseña
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordError, setPasswordError] = useState('')
  const [isChangingPassword, setIsChangingPassword] = useState(false)

  useEffect(() => {
    let cancelled = false
    authService
      .me()
      .then((data) => {
        if (!cancelled) setMe(data)
      })
      .catch(() => {
        if (!cancelled) showToast('No se pudo cargar la información de la cuenta.', 'error')
      })
      .finally(() => {
        if (!cancelled) setIsLoadingMe(false)
      })
    return () => {
      cancelled = true
    }
  }, [showToast])

  /** Guardar una preferencia y sincronizar el estado con la respuesta. */
  const savePreference = async (payload: Parameters<typeof authService.updatePreferences>[0]) => {
    if (!me) return
    const previous = me
    // Optimista: aplicar en UI, revertir si el backend falla
    setMe({ ...me, ...payload })
    setIsSavingPrefs(true)
    try {
      const updated = await authService.updatePreferences(payload)
      setMe(updated)
      showToast('Preferencias guardadas.', 'success')
    } catch {
      setMe(previous)
      showToast('No se pudieron guardar las preferencias.', 'error')
    } finally {
      setIsSavingPrefs(false)
    }
  }

  const handleResendVerification = async () => {
    if (!me) return
    setIsResendingVerification(true)
    try {
      await authService.resendVerificationEmail(me.email)
      showToast('Email de verificación reenviado. Revisa tu bandeja de entrada.', 'success')
    } catch {
      showToast('No se pudo reenviar el email de verificación.', 'error')
    } finally {
      setIsResendingVerification(false)
    }
  }

  const handleDeleteAccount = async (e: React.FormEvent) => {
    e.preventDefault()
    setDeleteError('')
    setIsDeleting(true)

    try {
      await authService.deleteAccount(deletePassword)
      logout()
      navigate('/login', { replace: true })
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: string } } }
      setDeleteError(axiosErr.response?.data?.error || 'Error al eliminar la cuenta. Verifica tu contraseña.')
    } finally {
      setIsDeleting(false)
    }
  }

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setPasswordError('')

    if (newPassword !== confirmPassword) {
      setPasswordError('Las nuevas contraseñas no coinciden.')
      return
    }
    if (newPassword.length < 8) {
      setPasswordError('La nueva contraseña debe tener al menos 8 caracteres.')
      return
    }

    setIsChangingPassword(true)
    try {
      await authService.changePassword(oldPassword, newPassword)
      showToast('Contraseña actualizada correctamente.', 'success')
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { error?: string } } }
      setPasswordError(axiosErr.response?.data?.error || 'Error al cambiar la contraseña. Revisa tus datos.')
    } finally {
      setIsChangingPassword(false)
    }
  }

  const memberSince = me
    ? new Date(me.date_joined).toLocaleDateString('es-ES', { day: 'numeric', month: 'long', year: 'numeric' })
    : null

  return (
    <div className="max-w-4xl mx-auto py-8 px-4 h-full overflow-y-auto">
      <h1 className="text-3xl font-bold text-white mb-2">Ajustes</h1>
      <p className="text-slate-400 mb-8">Administra la información de tu perfil y las opciones de seguridad.</p>

      <div className="space-y-8">

        {/* SECCIÓN PERFIL */}
        <section className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <h2 className="text-xl font-semibold text-white mb-6">Información del Perfil</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1">Nombre de usuario</label>
              <div className="bg-slate-900/50 px-4 py-3 rounded-lg border border-slate-700 text-slate-300">
                {me?.username ?? user?.username}
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-400 mb-1">Correo electrónico</label>
              <div className="bg-slate-900/50 px-4 py-3 rounded-lg border border-slate-700 text-slate-300 flex items-center justify-between gap-2">
                <span className="truncate">{me?.email ?? user?.email}</span>
                {me && <VerifiedBadge verified={me.is_email_verified} />}
              </div>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-500">
            {memberSince && <span>Miembro desde el {memberSince}</span>}
            {me && (
              <span className="inline-flex items-center gap-1.5">
                2FA:
                {me.is_2fa_enabled ? (
                  <span className="text-emerald-400 font-medium">activado</span>
                ) : (
                  <span className="text-slate-400 font-medium">desactivado</span>
                )}
              </span>
            )}
          </div>

          {me && !me.is_email_verified && (
            <div className="mt-4 bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <p className="text-sm text-amber-300">
                Tu email aún no está verificado. Algunas funciones, como las notificaciones, requieren verificación.
              </p>
              <button
                onClick={handleResendVerification}
                disabled={isResendingVerification}
                className="shrink-0 text-sm bg-amber-600 hover:bg-amber-700 disabled:bg-amber-800 text-white px-4 py-2 rounded-lg transition-colors"
              >
                {isResendingVerification ? 'Enviando...' : 'Reenviar email'}
              </button>
            </div>
          )}
        </section>

        {/* SECCIÓN PREFERENCIAS */}
        <section className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-xl font-semibold text-white">Preferencias Generales</h2>
            {isSavingPrefs && <span className="text-xs text-slate-500">Guardando...</span>}
          </div>
          <p className="text-slate-400 text-sm mb-6">Personaliza tu experiencia en la plataforma. Los cambios se guardan automáticamente.</p>

          <div className="max-w-md space-y-6">
            <div>
              <label htmlFor="preferred-currency" className="block text-sm font-medium text-slate-300 mb-2">
                Moneda principal (Fiat)
              </label>
              <select
                id="preferred-currency"
                value={me?.preferred_currency ?? 'usd'}
                disabled={isLoadingMe || isSavingPrefs}
                onChange={(e) => savePreference({ preferred_currency: e.target.value as PreferredCurrency })}
                className="bg-slate-900 border border-slate-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 w-full outline-none disabled:opacity-60"
              >
                {CURRENCY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
              <p className="text-xs text-slate-500 mt-2">La moneda base para mostrar precios y tu portafolio.</p>
            </div>
          </div>
        </section>

        {/* SECCIÓN NOTIFICACIONES */}
        <section className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <h2 className="text-xl font-semibold text-white mb-2">Notificaciones</h2>
          <p className="text-slate-400 text-sm mb-6">Administra qué avisos deseas recibir por correo electrónico.</p>

          <div className="space-y-4 max-w-md">
            <ToggleSwitch
              checked={me?.notify_price_alerts ?? true}
              disabled={isLoadingMe || isSavingPrefs}
              onChange={(value) => savePreference({ notify_price_alerts: value })}
              label="Alertas de precio"
              description="Recibe un correo cuando se dispare una de tus alertas de precio configuradas."
            />

            <hr className="border-slate-700 my-4" />

            <ToggleSwitch
              checked={me?.notify_market_digest ?? false}
              disabled={isLoadingMe || isSavingPrefs}
              onChange={(value) => savePreference({ notify_market_digest: value })}
              label="Novedades y Noticias"
              description="Recibe resúmenes periódicos sobre el estado del mercado."
            />
          </div>
        </section>

        {/* SECCIÓN CONTRASEÑA */}
        <section className="bg-slate-800 rounded-xl p-6 border border-slate-700">
          <h2 className="text-xl font-semibold text-white mb-2">Cambiar Contraseña</h2>
          <p className="text-slate-400 text-sm mb-6">Actualiza la contraseña utilizada para acceder a tu cuenta.</p>

          <form onSubmit={handleChangePassword} className="max-w-md space-y-4">
            <div>
              <label htmlFor="current-password" className="block text-sm font-medium text-slate-300 mb-1">Contraseña actual</label>
              <PasswordInput
                id="current-password"
                value={oldPassword}
                onChange={setOldPassword}
                required
                autoComplete="current-password"
                placeholder="Introducir contraseña actual"
              />
            </div>
            <div>
              <label htmlFor="new-password" className="block text-sm font-medium text-slate-300 mb-1">Nueva contraseña</label>
              <PasswordInput
                id="new-password"
                value={newPassword}
                onChange={setNewPassword}
                required
                autoComplete="new-password"
                placeholder="Mínimo 8 caracteres"
              />
            </div>
            <div>
              <label htmlFor="confirm-password" className="block text-sm font-medium text-slate-300 mb-1">Confirmar nueva contraseña</label>
              <PasswordInput
                id="confirm-password"
                value={confirmPassword}
                onChange={setConfirmPassword}
                required
                autoComplete="new-password"
                placeholder="Repetir nueva contraseña"
              />
            </div>

            {passwordError && <p className="text-sm text-red-400 mt-2">{passwordError}</p>}

            <div className="pt-2">
              <button
                type="submit"
                disabled={isChangingPassword}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-800 text-white font-medium px-5 py-2.5 rounded-lg transition-colors"
              >
                {isChangingPassword ? 'Cambiando...' : 'Actualizar contraseña'}
              </button>
            </div>
          </form>
        </section>

        {/* SECCIÓN 2FA */}
        <section className="bg-slate-800 rounded-xl p-6 border border-slate-700 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-white mb-1">Autenticación de dos factores (2FA)</h2>
            <p className="text-slate-400 text-sm">
              Protege tu cuenta con un código temporal adicional desde tu dispositivo móvil.
            </p>
          </div>
          <div>
            <Link
              to="/security/2fa"
              className="inline-block bg-slate-700 hover:bg-slate-600 text-white px-5 py-2.5 rounded-lg transition-colors border border-slate-600 whitespace-nowrap"
            >
              Gestión de 2FA
            </Link>
          </div>
        </section>

        {/* ZONA DE PELIGRO */}
        <section className="bg-red-950/20 border border-red-900/50 rounded-xl p-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h2 className="text-xl font-semibold text-red-500 mb-1">Eliminar Cuenta</h2>
              <p className="text-red-400/80 text-sm">
                Permite eliminar tu cuenta permanentemente. Esta acción no se puede deshacer.
              </p>
            </div>
            <div>
              <button
                onClick={() => setShowDeleteModal(true)}
                className="bg-red-600 hover:bg-red-700 text-white px-5 py-2.5 rounded-lg transition-colors whitespace-nowrap"
              >
                Borrar cuenta
              </button>
            </div>
          </div>
        </section>

      </div>

      {/* MODAL DE CONFIRMACIÓN DE BORRADO */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true">
          <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="text-xl font-bold text-white mb-4">¿Estás absolutamente seguro?</h3>
            <p className="text-slate-300 text-sm mb-6">
              Esta acción <strong>no se puede deshacer</strong>. Se eliminará permanentemente tu cuenta y se borrarán todos tus datos de nuestros servidores.
            </p>

            <form onSubmit={handleDeleteAccount}>
              <div className="mb-6">
                <label htmlFor="delete-password" className="block text-sm font-medium text-slate-400 mb-2">
                  Escribe tu contraseña para confirmar
                </label>
                <PasswordInput
                  id="delete-password"
                  value={deletePassword}
                  onChange={setDeletePassword}
                  required
                  tone="danger"
                  placeholder="Tu contraseña actual"
                />
                {deleteError && (
                  <p className="mt-2 text-sm text-red-400">{deleteError}</p>
                )}
              </div>
              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setShowDeleteModal(false)
                    setDeletePassword('')
                    setDeleteError('')
                  }}
                  className="px-4 py-2 rounded-lg text-slate-300 hover:bg-slate-700 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={isDeleting}
                  className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-700 disabled:bg-red-800 text-white transition-colors"
                >
                  {isDeleting ? 'Eliminando...' : 'Sí, eliminar mi cuenta'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
