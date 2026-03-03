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
 * en desarrollo, evitando problemas de CORS.
 */
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
      // Durante desarrollo, redirige /api/* al backend Django
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
