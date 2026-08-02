/**
 * pages/ResetPasswordPage.tsx — Establecer nueva contraseña.
 *
 * Página destino del enlace enviado por email al solicitar
 * recuperación de contraseña.
 *
 * Lee uid y token de los query params de la URL:
 *   /auth/password-reset/confirm/?uid=xxx&token=yyy
 *
 * Llama a POST /api/auth/password-reset/confirm/ y redirige
 * al login con un mensaje de éxito.
 */

import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { authService } from '@/services/authService'
import PasswordInput from '@/components/ui/PasswordInput'
import { apiErrorFor } from '@/utils/apiError'
import { PASSWORD_HINT, PASSWORD_MIN_LENGTH, checkPasswordLength } from '@/utils/authPolicy'

const AUTH_INPUT_CLASSES =
  'w-full bg-slate-700/70 border border-slate-600 rounded-xl px-3.5 py-2.5 pr-10 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition'

function ResetPasswordPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const uid = searchParams.get('uid') ?? ''
  const token = searchParams.get('token') ?? ''

  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Token inválido o enlace mal formado
  const isInvalidLink = !uid || !token

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (newPassword !== confirmPassword) {
      setError('Las contraseñas no coinciden.')
      return
    }

    const lengthError = checkPasswordLength(newPassword)
    if (lengthError) {
      setError(lengthError)
      return
    }

    setIsLoading(true)
    try {
      await authService.confirmPasswordReset(uid, token, newPassword, confirmPassword)
      navigate('/login', {
        replace: true,
        state: { message: 'Contraseña restablecida correctamente. Ya puedes iniciar sesión.' },
      })
    } catch (err: unknown) {
      // Si la política de contraseña rechaza la nueva, el motivo llega en
      // `details.new_password`; si no, el mensaje general (enlace caducado).
      setError(
        apiErrorFor(
          err,
          'new_password',
          'No se pudo restablecer la contraseña. El enlace puede haber expirado.',
        ),
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-[#0b1120] to-[#0f1f3d] px-4 py-12">
      <div className="w-full max-w-md">

        {/* Header / branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 shadow-lg shadow-blue-500/30 mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
            </svg>
          </div>
          <h1 className="text-3xl font-bold text-white tracking-tight">
            <span className="text-blue-400">Crypto</span>World
          </h1>
          <p className="text-slate-400 mt-2 text-sm">
            Sistema de análisis de criptomonedas
          </p>
        </div>

        {/* Card */}
        <div className="bg-slate-800/80 backdrop-blur rounded-2xl border border-slate-700/60 p-8 shadow-2xl">

          {isInvalidLink ? (
            /* ── Enlace inválido ── */
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-red-900/40 border border-red-700/50 mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-7 h-7 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-white mb-2">Enlace inválido</h2>
              <p className="text-slate-400 text-sm leading-relaxed mb-6">
                Este enlace de recuperación es inválido o ha expirado.
                Solicita uno nuevo desde la página de recuperación.
              </p>
              <Link
                to="/forgot-password"
                className="inline-block w-full text-center bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 text-white font-semibold py-2.5 rounded-xl transition-all text-sm shadow-lg shadow-blue-500/20"
              >
                Solicitar nuevo enlace
              </Link>
              <p className="text-center text-slate-500 text-sm mt-4">
                <Link to="/login" className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
                  ← Volver al inicio de sesión
                </Link>
              </p>
            </div>
          ) : (
            /* ── Formulario de nueva contraseña ── */
            <>
              <h2 className="text-xl font-semibold text-white mb-1">Nueva contraseña</h2>
              <p className="text-slate-400 text-sm mb-6">
                {PASSWORD_HINT}
              </p>

              {error && (
                <div className="bg-red-900/30 border border-red-700/60 rounded-lg px-4 py-3 mb-5">
                  <p className="text-red-400 text-sm">{error}</p>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label htmlFor="new-password" className="block text-sm font-medium text-slate-300 mb-1.5">
                    Nueva contraseña
                  </label>
                  <PasswordInput
                    id="new-password"
                    value={newPassword}
                    onChange={setNewPassword}
                    required
                    minLength={PASSWORD_MIN_LENGTH}
                    autoComplete="new-password"
                    placeholder="••••••••"
                    inputClassName={AUTH_INPUT_CLASSES}
                  />
                </div>

                <div>
                  <label htmlFor="confirm-password" className="block text-sm font-medium text-slate-300 mb-1.5">
                    Confirmar contraseña
                  </label>
                  <PasswordInput
                    id="confirm-password"
                    value={confirmPassword}
                    onChange={setConfirmPassword}
                    required
                    minLength={PASSWORD_MIN_LENGTH}
                    autoComplete="new-password"
                    placeholder="••••••••"
                    inputClassName={AUTH_INPUT_CLASSES}
                  />
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 disabled:from-blue-800 disabled:to-blue-800 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl transition-all text-sm mt-2 shadow-lg shadow-blue-500/20"
                >
                  {isLoading ? 'Guardando...' : 'Restablecer contraseña'}
                </button>
              </form>

              <p className="text-center text-slate-500 text-sm mt-6">
                <Link to="/login" className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
                  ← Volver al inicio de sesión
                </Link>
              </p>
            </>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-slate-600 text-xs mt-6">
          © 2026 CryptoWorld · Análisis cuantitativo de criptomonedas
        </p>
      </div>
    </div>
  )
}

export default ResetPasswordPage
