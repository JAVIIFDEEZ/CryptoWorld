import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

/**
 * vite.config.ts — Configuración de Vite.
 *
 * El alias '@' permite imports absolutos desde src/:
 *   import { authService } from '@/services/authService'
 *
 * El proxy reescribe peticiones a /api/* hacia el backend Django
 * en desarrollo, evitando problemas de CORS. También proxea las rutas
 * SEO renderizadas por servidor (/cripto, /sitemap.xml, /robots.txt) para
 * que en desarrollo se comporten igual que en producción (donde Vercel
 * las redirige a Railway, ver vercel.json) y no las capture el router SPA.
 */
const BACKEND_TARGET = 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],

  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },

  server: {
    port: 5173,
    proxy: {
      // Durante desarrollo, redirige al backend Django
      '/api': { target: BACKEND_TARGET, changeOrigin: true, secure: false },
      // WebSockets (Channels): proxy con ws habilitado hacia el ASGI del backend
      '/ws': { target: BACKEND_TARGET, ws: true, changeOrigin: true, secure: false },
      '/cripto': { target: BACKEND_TARGET, changeOrigin: true, secure: false },
      '/sitemap.xml': { target: BACKEND_TARGET, changeOrigin: true, secure: false },
      '/robots.txt': { target: BACKEND_TARGET, changeOrigin: true, secure: false },
    },
  },
})
