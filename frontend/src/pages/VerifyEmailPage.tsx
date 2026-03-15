import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { authService } from '@/services/authService'

function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('Verificando enlace...')

  useEffect(() => {
    async function verify() {
      const token = searchParams.get('token')
      if (!token) {
        setStatus('error')
        setMessage('El enlace no contiene un token de verificacion valido.')
        return
      }

      try {
        const response = await authService.verifyEmail(token)
        setStatus('success')
        setMessage(response.message)
      } catch (err: unknown) {
        const axiosError = err as { response?: { data?: { error?: string } } }
        setStatus('error')
        setMessage(axiosError?.response?.data?.error ?? 'No se pudo verificar el email.')
      }
    }

    verify()
  }, [searchParams])

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-[#0b1120] to-[#0f1f3d] px-4 py-12">
      <div className="w-full max-w-md bg-slate-800/80 border border-slate-700 rounded-2xl p-8 text-center">
        <h1 className="text-xl font-semibold text-white mb-3">Verificacion de email</h1>
        <p className={status === 'success' ? 'text-emerald-400' : status === 'error' ? 'text-red-400' : 'text-slate-300'}>
          {message}
        </p>

        <div className="mt-6">
          {status === 'success' ? (
            <div className="flex flex-col gap-3">
              <Link
                to="/login?next=/security/2fa"
                className="inline-block bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
              >
                Configurar 2FA ahora
              </Link>
              <Link
                to="/login"
                className="inline-block bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
              >
                Continuar sin 2FA (ir a login)
              </Link>
            </div>
          ) : (
            <Link
              to="/login"
              className="inline-block bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
            >
              Ir a login
            </Link>
          )}
        </div>
      </div>
    </div>
  )
}

export default VerifyEmailPage
