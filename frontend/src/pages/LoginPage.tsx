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
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'

function LoginPage() {
  const { login, isAuthenticated, isLoading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  // Mensaje de éxito proveniente del registro
  const successMessage = (location.state as { message?: string } | null)?.message ?? null

  // Si ya está autenticado, redirigir directamente
  if (isAuthenticated) {
    const from = (location.state as { from?: Location })?.from?.pathname ?? '/dashboard'
    navigate(from, { replace: true })
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    try {
      await login(email, password)
      // Redirigir a la ruta que intentaba acceder antes del login
      const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/dashboard'
      navigate(from, { replace: true })
    } catch {
      setError('Credenciales incorrectas. Verifica tu email y contraseña.')
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
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full bg-slate-700/70 border border-slate-600 rounded-xl px-3.5 py-2.5 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 disabled:from-blue-800 disabled:to-blue-800 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl transition-all text-sm mt-2 shadow-lg shadow-blue-500/20"
            >
              {isLoading ? 'Entrando...' : 'Entrar'}
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
