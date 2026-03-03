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
import { AuthProvider } from '@/hooks/useAuth'
import AppRoutes from '@/routes'

function App() {
  return (
    <BrowserRouter>
      {/*
        AuthProvider debe envolver AppRoutes para que ProtectedRoute
        pueda acceder al contexto de autenticación en cualquier nivel.
      */}
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
