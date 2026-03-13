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
import MarketPage from '@/pages/MarketPage'
import TechnicalAnalysisPage from '@/pages/TechnicalAnalysisPage'
import PrototypePlaceholderPage from '@/pages/PrototypePlaceholderPage'
import ProtectedRoute from '@/components/ProtectedRoute'
import AppShell from '@/components/AppShell'

function AppRoutes() {
  return (
    <Routes>
      {/* Rutas públicas */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Rutas protegidas: envueltas en el guard de autenticación */}
      <Route element={<ProtectedRoute />}>
        {/* AppShell persiste entre páginas protegidas */}
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/analysis" element={<TechnicalAnalysisPage />} />
          <Route
            path="/blockchain"
            element={<PrototypePlaceholderPage title="Blockchain Analytics" description="Pantalla preparada para metricas on-chain del prototipo." />}
          />
          <Route
            path="/portfolio"
            element={<PrototypePlaceholderPage title="Portfolio" description="Pendiente integrar holdings reales y PnL." />}
          />
          <Route
            path="/news"
            element={<PrototypePlaceholderPage title="Noticias" description="Pendiente integrar feed de noticias y sentimiento." />}
          />
          <Route
            path="/alerts"
            element={<PrototypePlaceholderPage title="Alertas" description="Pendiente integrar reglas y notificaciones de precio." />}
          />
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

export default AppRoutes
