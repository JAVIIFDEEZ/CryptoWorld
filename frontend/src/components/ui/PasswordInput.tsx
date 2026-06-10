/**
 * components/ui/PasswordInput.tsx — Input de contraseña con toggle de visibilidad.
 *
 * Unifica los campos de contraseña repartidos por Ajustes, modales y
 * formularios de auth: input + botón ojo accesible (aria-pressed) sin
 * duplicar los SVG en cada página.
 */

import { useState } from 'react'

interface PasswordInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  required?: boolean
  autoComplete?: string
  /** Color del anillo de foco; 'danger' para zonas destructivas. */
  tone?: 'primary' | 'danger'
  id?: string
}

function EyeOffIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.242m4.242 4.242L9.88 9.88" />
    </svg>
  )
}

function EyeIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  )
}

export default function PasswordInput({
  value,
  onChange,
  placeholder,
  required = false,
  autoComplete = 'current-password',
  tone = 'primary',
  id,
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false)

  const ring =
    tone === 'danger'
      ? 'focus:ring-red-500 focus:border-red-500'
      : 'focus:ring-blue-500 focus:border-blue-500'

  return (
    <div className="relative">
      <input
        id={id}
        type={visible ? 'text' : 'password'}
        required={required}
        autoComplete={autoComplete}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2.5 pr-10 text-white focus:ring-2 ${ring} outline-none`}
        placeholder={placeholder}
      />
      <button
        type="button"
        aria-label={visible ? 'Ocultar contraseña' : 'Mostrar contraseña'}
        aria-pressed={visible}
        onClick={() => setVisible(!visible)}
        className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-white"
      >
        {visible ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </div>
  )
}
