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

import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import ProtectedRoute from '@/components/layout/ProtectedRoute'
import { AdminRoute } from '@/components/layout/AdminRoute'
import AppShell from '@/components/layout/AppShell'

// Code splitting: cada página se carga sólo cuando se navega a ella
const LandingPage = lazy(() => import('@/pages/LandingPage'))
const LoginPage = lazy(() => import('@/pages/LoginPage'))
const RegisterPage = lazy(() => import('@/pages/RegisterPage'))
const VerifyEmailPage = lazy(() => import('@/pages/VerifyEmailPage'))
const ConfirmEmailChangePage = lazy(() => import('@/pages/ConfirmEmailChangePage'))
const ForgotPasswordPage = lazy(() => import('@/pages/ForgotPasswordPage'))
const ResetPasswordPage = lazy(() => import('@/pages/ResetPasswordPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const AssetDetailPage = lazy(() => import('@/pages/AssetDetailPage'))
const MarketPage = lazy(() => import('@/pages/MarketPage'))
const TechnicalAnalysisPage = lazy(() => import('@/pages/TechnicalAnalysisPage'))
const StrategyGeneratorPage = lazy(() => import('@/pages/StrategyGeneratorPage'))
const StrategyDossierPage = lazy(() => import('@/pages/StrategyDossierPage'))
const AddressDossierPage = lazy(() => import('@/pages/AddressDossierPage'))
const PortfolioPage = lazy(() => import('@/pages/PortfolioPage'))
const TradingPage = lazy(() => import('@/pages/TradingPage'))
const AlertsPage = lazy(() => import('@/pages/AlertsPage'))
const NewsPage = lazy(() => import('@/pages/NewsPage'))
const BlockchainPage = lazy(() => import('@/pages/BlockchainPage'))
const Security2FAPage = lazy(() => import('@/pages/Security2FAPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))
const AdminDashboardPage = lazy(() => import('@/pages/AdminDashboardPage'))

function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-slate-900">
      <div className="w-8 h-8 border-2 border-slate-600 border-t-slate-300 rounded-full animate-spin" />
    </div>
  )
}

function AppRoutes() {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
      {/* Rutas públicas */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/auth/verify-email" element={<VerifyEmailPage />} />
      <Route path="/auth/confirm-email-change" element={<ConfirmEmailChangePage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/auth/password-reset/confirm" element={<ResetPasswordPage />} />

      {/* Rutas protegidas: envueltas en el guard de autenticación */}
      <Route element={<ProtectedRoute />}>
        {/* Dossiers imprimibles: protegidos pero SIN AppShell (imprimen limpio) */}
        <Route path="/strategies/:id/dossier" element={<StrategyDossierPage />} />
        <Route path="/blockchain/address/:chain/:address/dossier" element={<AddressDossierPage />} />
        {/* AppShell persiste entre páginas protegidas */}
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/analysis" element={<TechnicalAnalysisPage />} />
          <Route path="/strategies" element={<StrategyGeneratorPage />} />
          <Route path="/blockchain" element={<BlockchainPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/trading" element={<TradingPage />} />
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
    </Suspense>
  )
}

export default AppRoutes
