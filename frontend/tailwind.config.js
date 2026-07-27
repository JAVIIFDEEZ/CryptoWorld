/** @type {import('tailwindcss').Config} */
export default {
  // Escanear estos archivos para generar solo las clases CSS usadas
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      // Colores del sistema CryptoWorld
      colors: {
        // Paleta neutra mapeada a variables CSS (canales RGB) para soportar tema
        // claro/oscuro sin tocar los componentes: en oscuro (por defecto) los
        // valores son los de slate reales (cero regresión); en .theme-light se
        // invierte la rampa. `white` también se mapea para que los titulares en
        // blanco se oscurezcan en modo claro.
        slate: {
          50:  'rgb(var(--c-slate-50) / <alpha-value>)',
          100: 'rgb(var(--c-slate-100) / <alpha-value>)',
          200: 'rgb(var(--c-slate-200) / <alpha-value>)',
          300: 'rgb(var(--c-slate-300) / <alpha-value>)',
          400: 'rgb(var(--c-slate-400) / <alpha-value>)',
          500: 'rgb(var(--c-slate-500) / <alpha-value>)',
          600: 'rgb(var(--c-slate-600) / <alpha-value>)',
          700: 'rgb(var(--c-slate-700) / <alpha-value>)',
          800: 'rgb(var(--c-slate-800) / <alpha-value>)',
          900: 'rgb(var(--c-slate-900) / <alpha-value>)',
          950: 'rgb(var(--c-slate-950) / <alpha-value>)',
        },
        white: 'rgb(var(--c-white) / <alpha-value>)',
        // Acentos mapeados a variables solo en los tonos que cambian entre
        // temas (texto 200-400, fondos 700-950); 50-600 siguen siendo los de
        // Tailwind y se comportan igual en ambos temas.
        red: {
          200: 'rgb(var(--c-red-200) / <alpha-value>)',
          300: 'rgb(var(--c-red-300) / <alpha-value>)',
          400: 'rgb(var(--c-red-400) / <alpha-value>)',
          700: 'rgb(var(--c-red-700) / <alpha-value>)',
          800: 'rgb(var(--c-red-800) / <alpha-value>)',
          900: 'rgb(var(--c-red-900) / <alpha-value>)',
          950: 'rgb(var(--c-red-950) / <alpha-value>)',
        },
        green: {
          200: 'rgb(var(--c-green-200) / <alpha-value>)',
          300: 'rgb(var(--c-green-300) / <alpha-value>)',
          400: 'rgb(var(--c-green-400) / <alpha-value>)',
          700: 'rgb(var(--c-green-700) / <alpha-value>)',
          800: 'rgb(var(--c-green-800) / <alpha-value>)',
          900: 'rgb(var(--c-green-900) / <alpha-value>)',
          950: 'rgb(var(--c-green-950) / <alpha-value>)',
        },
        blue: {
          200: 'rgb(var(--c-blue-200) / <alpha-value>)',
          300: 'rgb(var(--c-blue-300) / <alpha-value>)',
          400: 'rgb(var(--c-blue-400) / <alpha-value>)',
          700: 'rgb(var(--c-blue-700) / <alpha-value>)',
          800: 'rgb(var(--c-blue-800) / <alpha-value>)',
          900: 'rgb(var(--c-blue-900) / <alpha-value>)',
          950: 'rgb(var(--c-blue-950) / <alpha-value>)',
        },
        emerald: {
          200: 'rgb(var(--c-emerald-200) / <alpha-value>)',
          300: 'rgb(var(--c-emerald-300) / <alpha-value>)',
          400: 'rgb(var(--c-emerald-400) / <alpha-value>)',
          700: 'rgb(var(--c-emerald-700) / <alpha-value>)',
          800: 'rgb(var(--c-emerald-800) / <alpha-value>)',
          900: 'rgb(var(--c-emerald-900) / <alpha-value>)',
          950: 'rgb(var(--c-emerald-950) / <alpha-value>)',
        },
        yellow: {
          200: 'rgb(var(--c-yellow-200) / <alpha-value>)',
          300: 'rgb(var(--c-yellow-300) / <alpha-value>)',
          400: 'rgb(var(--c-yellow-400) / <alpha-value>)',
          700: 'rgb(var(--c-yellow-700) / <alpha-value>)',
          800: 'rgb(var(--c-yellow-800) / <alpha-value>)',
          900: 'rgb(var(--c-yellow-900) / <alpha-value>)',
          950: 'rgb(var(--c-yellow-950) / <alpha-value>)',
        },
        amber: {
          200: 'rgb(var(--c-amber-200) / <alpha-value>)',
          300: 'rgb(var(--c-amber-300) / <alpha-value>)',
          400: 'rgb(var(--c-amber-400) / <alpha-value>)',
          700: 'rgb(var(--c-amber-700) / <alpha-value>)',
          800: 'rgb(var(--c-amber-800) / <alpha-value>)',
          900: 'rgb(var(--c-amber-900) / <alpha-value>)',
          950: 'rgb(var(--c-amber-950) / <alpha-value>)',
        },
        purple: {
          200: 'rgb(var(--c-purple-200) / <alpha-value>)',
          300: 'rgb(var(--c-purple-300) / <alpha-value>)',
          400: 'rgb(var(--c-purple-400) / <alpha-value>)',
          700: 'rgb(var(--c-purple-700) / <alpha-value>)',
          800: 'rgb(var(--c-purple-800) / <alpha-value>)',
          900: 'rgb(var(--c-purple-900) / <alpha-value>)',
          950: 'rgb(var(--c-purple-950) / <alpha-value>)',
        },
        sky: {
          200: 'rgb(var(--c-sky-200) / <alpha-value>)',
          300: 'rgb(var(--c-sky-300) / <alpha-value>)',
          400: 'rgb(var(--c-sky-400) / <alpha-value>)',
          700: 'rgb(var(--c-sky-700) / <alpha-value>)',
          800: 'rgb(var(--c-sky-800) / <alpha-value>)',
          900: 'rgb(var(--c-sky-900) / <alpha-value>)',
          950: 'rgb(var(--c-sky-950) / <alpha-value>)',
        },
        cyan: {
          200: 'rgb(var(--c-cyan-200) / <alpha-value>)',
          300: 'rgb(var(--c-cyan-300) / <alpha-value>)',
          400: 'rgb(var(--c-cyan-400) / <alpha-value>)',
          700: 'rgb(var(--c-cyan-700) / <alpha-value>)',
          800: 'rgb(var(--c-cyan-800) / <alpha-value>)',
          900: 'rgb(var(--c-cyan-900) / <alpha-value>)',
          950: 'rgb(var(--c-cyan-950) / <alpha-value>)',
        },
        orange: {
          200: 'rgb(var(--c-orange-200) / <alpha-value>)',
          300: 'rgb(var(--c-orange-300) / <alpha-value>)',
          400: 'rgb(var(--c-orange-400) / <alpha-value>)',
          700: 'rgb(var(--c-orange-700) / <alpha-value>)',
          800: 'rgb(var(--c-orange-800) / <alpha-value>)',
          900: 'rgb(var(--c-orange-900) / <alpha-value>)',
          950: 'rgb(var(--c-orange-950) / <alpha-value>)',
        },
        indigo: {
          200: 'rgb(var(--c-indigo-200) / <alpha-value>)',
          300: 'rgb(var(--c-indigo-300) / <alpha-value>)',
          400: 'rgb(var(--c-indigo-400) / <alpha-value>)',
          700: 'rgb(var(--c-indigo-700) / <alpha-value>)',
          800: 'rgb(var(--c-indigo-800) / <alpha-value>)',
          900: 'rgb(var(--c-indigo-900) / <alpha-value>)',
          950: 'rgb(var(--c-indigo-950) / <alpha-value>)',
        },
        brand: {
          50: '#eff6ff',
          100: '#dbeafe',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          900: '#1e3a8a',
        },
        success: '#22c55e',
        danger: '#ef4444',
        // Tokens semánticos de trading (verde sube, rojo baja, ámbar neutral).
        // Cada uno con su fondo "soft" y borde "ring" para chips y badges.
        positive: {
          DEFAULT: '#22c55e',
          soft: 'rgba(34,197,94,0.12)',
          ring: 'rgba(34,197,94,0.28)',
        },
        negative: {
          DEFAULT: '#ef4444',
          soft: 'rgba(239,68,68,0.12)',
          ring: 'rgba(239,68,68,0.28)',
        },
        caution: {
          DEFAULT: '#eab308',
          soft: 'rgba(234,179,8,0.12)',
          ring: 'rgba(234,179,8,0.28)',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
