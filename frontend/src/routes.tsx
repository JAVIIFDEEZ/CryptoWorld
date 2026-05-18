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
import LandingPage from '@/pages/LandingPage'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import VerifyEmailPage from '@/pages/VerifyEmailPage'
import ForgotPasswordPage from '@/pages/ForgotPasswordPage'
import ResetPasswordPage from '@/pages/ResetPasswordPage'
import DashboardPage from '@/pages/DashboardPage'
import AssetDetailPage from '@/pages/AssetDetailPage'
import MarketPage from '@/pages/MarketPage'
import TechnicalAnalysisPage from '@/pages/TechnicalAnalysisPage'
import PortfolioPage from '@/pages/PortfolioPage'
import AlertsPage from '@/pages/AlertsPage'
import NewsPage from '@/pages/NewsPage'
import BlockchainPage from '@/pages/BlockchainPage'
import Security2FAPage from '@/pages/Security2FAPage'
import SettingsPage from '@/pages/SettingsPage'
import ProtectedRoute from '@/components/ProtectedRoute'
import { AdminRoute } from '@/components/AdminRoute'
import AppShell from '@/components/AppShell'
import AdminDashboardPage from '@/pages/AdminDashboardPage'

function AppRoutes() {
  return (
    <Routes>
      {/* Rutas públicas */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/auth/verify-email" element={<VerifyEmailPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/auth/password-reset/confirm" element={<ResetPasswordPage />} />

      {/* Rutas protegidas: envueltas en el guard de autenticación */}
      <Route element={<ProtectedRoute />}>
        {/* AppShell persiste entre páginas protegidas */}
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/analysis" element={<TechnicalAnalysisPage />} />
          <Route path="/blockchain" element={<BlockchainPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/news" element={<NewsPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/security/2fa" element={<Security2FAPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/assets/:symbol" element={<AssetDetailPage />} />
          <Route
            path="/admin"
            element={
              <AdminRoute>
                <AdminDashboardPage />
              </AdminRoute>
            }
          />
        </Route>
      </Route>

      {/* Ruta raíz: landing page pública (redirige a /dashboard si autenticado) */}
      <Route path="/" element={<LandingPage />} />

      {/* 404 catch-all */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default AppRoutes
