/**
 * pages/ForgotPasswordPage.tsx — Solicitar recuperación de contraseña.
 *
 * El usuario introduce su email. Si existe en el sistema, recibirá
 * un enlace para restablecer la contraseña.
 *
 * Por seguridad el backend siempre responde HTTP 200 aunque el email
 * no exista, evitando la enumeración de usuarios (OWASP Top 10).
 */

import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { authService } from '@/services/authService'

function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsLoading(true)

    try {
      await authService.requestPasswordReset(email)
      setSubmitted(true)
    } catch {
      setError('No se pudo procesar la solicitud. Inténtalo de nuevo más tarde.')
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

          {submitted ? (
            /* ── Estado: email enviado ── */
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-emerald-900/40 border border-emerald-700/50 mb-4">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-7 h-7 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <h2 className="text-xl font-semibold text-white mb-2">Revisa tu email</h2>
              <p className="text-slate-400 text-sm leading-relaxed mb-6">
                Si existe una cuenta asociada a <span className="text-white font-medium">{email}</span>,
                recibirás un enlace para restablecer tu contraseña en los próximos minutos.
              </p>
              <p className="text-slate-500 text-xs mb-6">
                No olvides revisar la carpeta de spam.
              </p>
              <Link
                to="/login"
                className="inline-block w-full text-center bg-slate-700/70 hover:bg-slate-700 border border-slate-600 text-white font-medium py-2.5 rounded-xl transition text-sm"
              >
                Volver al inicio de sesión
              </Link>
            </div>
          ) : (
            /* ── Estado: formulario ── */
            <>
              <h2 className="text-xl font-semibold text-white mb-1">¿Olvidaste tu contraseña?</h2>
              <p className="text-slate-400 text-sm mb-6">
                Introduce tu email y te enviaremos un enlace para restablecerla.
              </p>

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

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 disabled:from-blue-800 disabled:to-blue-800 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl transition-all text-sm shadow-lg shadow-blue-500/20"
                >
                  {isLoading ? 'Enviando...' : 'Enviar enlace de recuperación'}
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

export default ForgotPasswordPage
