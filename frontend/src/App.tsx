/**
 * App.tsx — Componente raíz de la aplicación.
 *
 * Responsabilidad: proporcionar el contexto de autenticación global
 * y conectar el sistema de rutas. Es el único punto donde viven
 * los providers que deben envolver a toda la app.
 *
 * BrowserRouter: activa el enrutamiento basado en History API.
 * AuthProvider: distribuye el estado de autenticación a toda la app.
 */

import { BrowserRouter } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { queryClient } from '@/lib/queryClient'
import { AuthProvider } from '@/hooks/useAuth'
import { CurrencyProvider } from '@/hooks/useCurrency'
import { ToastProvider } from '@/components/ui/Toast'
import { ThemeProvider } from '@/hooks/useTheme'
import AppRoutes from '@/routes'
import ErrorBoundary from '@/components/layout/ErrorBoundary'

function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
      <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        {/*
          AuthProvider debe envolver AppRoutes para que ProtectedRoute
          pueda acceder al contexto de autenticación en cualquier nivel.
          CurrencyProvider depende de useAuth (sincroniza la moneda del
          usuario autenticado); ToastProvider expone useToast() a toda la app.
          QueryClientProvider da caché de datos compartida a todas las vistas.
        */}
        <AuthProvider>
          <CurrencyProvider>
            <ToastProvider>
              <AppRoutes />
            </ToastProvider>
          </CurrencyProvider>
        </AuthProvider>
      </BrowserRouter>
      </QueryClientProvider>
      </ThemeProvider>
    </ErrorBoundary>
  )
}

export default App
