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
