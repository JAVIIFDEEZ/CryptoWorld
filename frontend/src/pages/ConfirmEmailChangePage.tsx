/**
 * pages/ConfirmEmailChangePage.tsx — Confirmación del cambio de email.
 *
 * El usuario llega aquí desde el enlace enviado a su NUEVA dirección
 * (/auth/confirm-email-change?token=...). Al confirmar, el backend
 * sustituye el email de login y lo marca como verificado.
 *
 * Mismo patrón visual que VerifyEmailPage (página pública, sin sesión).
 */

import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { authService } from '@/services/authService'
import { apiErrorMessage } from '@/utils/apiError'

function ConfirmEmailChangePage() {
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('Confirmando el cambio de email...')

  useEffect(() => {
    async function confirm() {
      const token = searchParams.get('token')
      if (!token) {
        setStatus('error')
        setMessage('El enlace no contiene un token de confirmación válido.')
        return
      }

      try {
        const response = await authService.confirmEmailChange(token)
        setStatus('success')
        setMessage(response.message)
      } catch (err: unknown) {
        setStatus('error')
        setMessage(apiErrorMessage(err, 'No se pudo confirmar el cambio de email.'))
      }
    }

    confirm()
  }, [searchParams])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-[#0b1120] to-[#0f1f3d] px-4 py-12">
      <div className="w-full max-w-md bg-slate-800/80 border border-slate-700 rounded-2xl p-8 text-center">
        <h1 className="text-xl font-semibold text-white mb-3">Cambio de email</h1>
        <p className={status === 'success' ? 'text-emerald-400' : status === 'error' ? 'text-red-400' : 'text-slate-300'}>
          {message}
        </p>

        {status === 'success' && (
          <p className="text-slate-400 text-sm mt-3">
            A partir de ahora inicia sesión con tu nueva dirección.
          </p>
        )}

        <div className="mt-6">
          <Link
            to="/login"
            className="inline-block bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
          >
            Ir a login
          </Link>
        </div>
      </div>
    </div>
  )
}

export default ConfirmEmailChangePage
