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
