/**
 * pages/LoginPage.tsx — Página de inicio de sesión.
 *
 * Responsabilidad: formulario de autenticación.
 * Delega la lógica de login en el hook useAuth,
 * que a su vez usa authService para llamar a la API.
 *
 * Al autenticarse correctamente, redirige al dashboard
 * (o a la ruta que el usuario intentaba acceder antes del 401).
 */

import { useState, type FormEvent } from 'react'
import { useNavigate, useLocation, Link, useSearchParams } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { authService } from '@/services/authService'

function LoginPage() {
  const { login, verify2FALogin, isAuthenticated, isLoading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [totpCode, setTotpCode] = useState('')
  const [preAuthToken, setPreAuthToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [errorCode, setErrorCode] = useState<string | null>(null)
  const [resendInfo, setResendInfo] = useState<string | null>(null)

  // Mensaje de éxito proveniente del registro
  const successMessage = (location.state as { message?: string } | null)?.message ?? null
  const nextPath = searchParams.get('next') ?? undefined

  // Si ya está autenticado, redirigir directamente
  if (isAuthenticated) {
    const from = (location.state as { from?: Location })?.from?.pathname ?? '/dashboard'
    navigate(from, { replace: true })
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setErrorCode(null)
    setResendInfo(null)

    try {
      if (preAuthToken) {
        await verify2FALogin(preAuthToken, totpCode)
        const from = nextPath ?? (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/dashboard'
        navigate(from, { replace: true })
        return
      }

      const result = await login(email, password)

      if (result.requires2FA) {
        setPreAuthToken(result.preAuthToken ?? null)
        return
      }

      // Redirigir a la ruta que intentaba acceder antes del login
      const from = nextPath ?? (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/dashboard'
      navigate(from, { replace: true })
    } catch (err: unknown) {
      const axiosError = err as { response?: { status?: number; data?: { error?: string; error_code?: string } } }
      const backendError = axiosError?.response?.data?.error
      const backendCode = axiosError?.response?.data?.error_code

      if (backendCode) {
        setErrorCode(backendCode)
      }

      setError(backendError ?? 'Credenciales incorrectas. Verifica tu email y contraseña.')
    }
  }

  async function handleResendVerification() {
    setError(null)
    setErrorCode(null)
    setResendInfo(null)

    if (!email) {
      setError('Introduce tu email y pulsa de nuevo para reenviar la verificación.')
      return
    }

    try {
      const response = await authService.resendVerificationEmail(email)
      setResendInfo(response.message)
    } catch {
      setError('No se pudo reenviar el email de verificación. Inténtalo más tarde.')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-[#0b1120] to-[#0f1f3d] px-4 py-12">
      <div className="w-full max-w-md">
        {/* Header / branding */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 shadow-lg shadow-blue-500/30 mb-4">
            {/* Ícono de actividad (inline SVG para evitar dependencia extra) */}
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

        {/* Card del formulario */}
        <div className="bg-slate-800/80 backdrop-blur rounded-2xl border border-slate-700/60 p-8 shadow-2xl">
          <h2 className="text-xl font-semibold text-white mb-1">Iniciar sesión</h2>
          <p className="text-slate-400 text-sm mb-6">Accede a tu panel de análisis.</p>

          {successMessage && (
            <div className="bg-emerald-900/30 border border-emerald-700/60 rounded-lg px-4 py-3 mb-5">
              <p className="text-emerald-400 text-sm">{successMessage}</p>
            </div>
          )}

          {error && (
            <div className="bg-red-900/30 border border-red-700/60 rounded-lg px-4 py-3 mb-5">
              <p className="text-red-400 text-sm">{error}</p>
              {errorCode === 'email_not_verified' && (
                <button
                  type="button"
                  onClick={handleResendVerification}
                  className="mt-2 text-xs text-blue-300 hover:text-blue-200 underline"
                >
                  Reenviar email de verificación
                </button>
              )}
            </div>
          )}

          {resendInfo && (
            <div className="bg-emerald-900/30 border border-emerald-700/60 rounded-lg px-4 py-3 mb-5">
              <p className="text-emerald-400 text-sm">{resendInfo}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-300 mb-1.5">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="tu@email.com"
                className="w-full bg-slate-700/70 border border-slate-600 rounded-xl px-3.5 py-2.5 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-300 mb-1.5">
                Contraseña
              </label>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  placeholder="••••••••"
                  className="w-full bg-slate-700/70 border border-slate-600 rounded-xl px-3.5 py-2.5 pr-10 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-white"
                >
                  {showPassword ? (
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.242m4.242 4.242L9.88 9.88" />
                    </svg>
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            {preAuthToken && (
              <div>
                <label htmlFor="totp" className="block text-sm font-medium text-slate-300 mb-1.5">
                  Codigo de autenticacion (2FA)
                </label>
                <input
                  id="totp"
                  type="text"
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value)}
                  required
                  minLength={6}
                  maxLength={6}
                  placeholder="123456"
                  className="w-full bg-slate-700/70 border border-slate-600 rounded-xl px-3.5 py-2.5 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
                />
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 disabled:from-blue-800 disabled:to-blue-800 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl transition-all text-sm mt-2 shadow-lg shadow-blue-500/20"
            >
              {isLoading ? 'Entrando...' : preAuthToken ? 'Validar 2FA' : 'Entrar'}
            </button>
          </form>

          <p className="text-center text-slate-500 text-sm mt-6">
            ¿No tienes cuenta?{' '}
            <Link to="/register" className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
              Regístrate
            </Link>
          </p>
        </div>

        {/* Footer */}
        <p className="text-center text-slate-600 text-xs mt-6">
          TFG · Análisis de Criptomonedas · UCLM
        </p>
      </div>
    </div>
  )
}

export default LoginPage
