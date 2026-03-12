/**
 * routes.tsx — Definición del sistema de rutas de la SPA.
 *
 * Usa React Router v6 con rutas anidadas para proteger secciones
 * autenticadas sin repetir lógica en cada página.
 *
 * Estructura:
 *   / (público)          → redirige a /dashboard o /login según auth
 *   /login               → LoginPage (público)
 *   /dashboard           → DashboardPage (protegido)
 *   /assets/:symbol      → AssetDetailPage (protegido)
 */

import { Routes, Route, Navigate } from 'react-router-dom'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import DashboardPage from '@/pages/DashboardPage'
import AssetDetailPage from '@/pages/AssetDetailPage'
import ProtectedRoute from '@/components/ProtectedRoute'
import Navbar from '@/components/Navbar'

function AppRoutes() {
  return (
    <Routes>
      {/* Rutas públicas */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Rutas protegidas: envueltas en el guard de autenticación */}
      <Route element={<ProtectedRoute />}>
        {/* Navbar persiste entre páginas protegidas */}
        <Route element={<LayoutWithNav />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/assets/:symbol" element={<AssetDetailPage />} />
        </Route>
      </Route>

      {/* Ruta raíz: redirige a dashboard */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />

      {/* 404 catch-all */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

/**
 * Layout interno que incluye la barra de navegación.
 * Usa Outlet de React Router para renderizar la ruta hija.
 */
import { Outlet } from 'react-router-dom'

function LayoutWithNav() {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <main className="flex-1 container mx-auto px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}

export default AppRoutes
