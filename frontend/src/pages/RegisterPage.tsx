/**
 * pages/RegisterPage.tsx — Página de registro de nuevos usuarios.
 *
 * Responsabilidad: formulario de creación de cuenta.
 * Llama directamente a authService.register() ya que el registro
 * no modifica el estado de autenticación (redirige a /login tras éxito).
 *
 * Campos: email, username, contraseña y confirmación de contraseña.
 * La validación de que ambas contraseñas coincidan se hace en cliente
 * antes de enviar al backend.
 */

import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { authService, type RegisterPayload } from '@/services/authService'

function RegisterPage() {
  const navigate = useNavigate()

  const [form, setForm] = useState<RegisterPayload & { password_confirm: string }>({
    email: '',
    username: '',
    password: '',
    password_confirm: '',
  })
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setForm(prev => ({ ...prev, [e.target.name]: e.target.value }))
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (form.password !== form.password_confirm) {
      setError('Las contraseñas no coinciden.')
      return
    }

    if (form.password.length < 8) {
      setError('La contraseña debe tener al menos 8 caracteres.')
      return
    }

    setIsLoading(true)
    try {
      await authService.register({
        email: form.email,
        username: form.username,
        password: form.password,
        password_confirm: form.password_confirm,
      })
      // Redirigir al login con mensaje de éxito
      navigate('/login', {
        state: { message: '¡Cuenta creada correctamente! Ya puedes iniciar sesión.' },
      })
    } catch (err: unknown) {
      // El backend puede devolver errores de validación en el cuerpo
      const axiosError = err as { response?: { data?: Record<string, string[]> } }
      const data = axiosError?.response?.data
      if (data) {
        // Extraer el primer mensaje de error del backend
        const firstField = Object.keys(data)[0]
        const msg = Array.isArray(data[firstField]) ? data[firstField][0] : String(data[firstField])
        setError(msg)
      } else {
        setError('No se pudo crear la cuenta. Inténtalo de nuevo.')
      }
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
          <h2 className="text-xl font-semibold text-white mb-1">Crear cuenta</h2>
          <p className="text-slate-400 text-sm mb-6">Rellena los campos para registrarte.</p>

          {error && (
            <div className="bg-red-900/30 border border-red-700/60 rounded-lg px-4 py-3 mb-5">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-300 mb-1.5">
                Email
              </label>
              <input
                id="email"
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                required
                placeholder="tu@email.com"
                className="w-full bg-slate-700/70 border border-slate-600 rounded-xl px-3.5 py-2.5 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
              />
            </div>

            {/* Username */}
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-300 mb-1.5">
                Nombre de usuario
              </label>
              <input
                id="username"
                name="username"
                type="text"
                value={form.username}
                onChange={handleChange}
                required
                placeholder="cryptouser"
                className="w-full bg-slate-700/70 border border-slate-600 rounded-xl px-3.5 py-2.5 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
              />
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-300 mb-1.5">
                Contraseña
              </label>
              <input
                id="password"
                name="password"
                type="password"
                value={form.password}
                onChange={handleChange}
                required
                placeholder="Mínimo 8 caracteres"
                className="w-full bg-slate-700/70 border border-slate-600 rounded-xl px-3.5 py-2.5 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
              />
            </div>

            {/* Confirm password */}
            <div>
              <label htmlFor="password_confirm" className="block text-sm font-medium text-slate-300 mb-1.5">
                Confirmar contraseña
              </label>
              <input
                id="password_confirm"
                name="password_confirm"
                type="password"
                value={form.password_confirm}
                onChange={handleChange}
                required
                placeholder="Repite la contraseña"
                className="w-full bg-slate-700/70 border border-slate-600 rounded-xl px-3.5 py-2.5 text-white placeholder-slate-500 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-gradient-to-r from-blue-600 to-blue-500 hover:from-blue-500 hover:to-blue-400 disabled:from-blue-800 disabled:to-blue-800 disabled:cursor-not-allowed text-white font-semibold py-2.5 rounded-xl transition-all text-sm mt-2 shadow-lg shadow-blue-500/20"
            >
              {isLoading ? 'Creando cuenta...' : 'Crear cuenta'}
            </button>
          </form>

          <p className="text-center text-slate-500 text-sm mt-6">
            ¿Ya tienes cuenta?{' '}
            <Link to="/login" className="text-blue-400 hover:text-blue-300 font-medium transition-colors">
              Inicia sesión
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

export default RegisterPage
