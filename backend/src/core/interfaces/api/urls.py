"""
interfaces/api/urls.py — Enrutador de la API REST.

Define las URLs de los endpoints de la aplicación.
Cada URL apunta a un View que delega en un caso de uso.

Convención REST aplicada:
  - Recursos en plural y minúsculas
  - Verbos HTTP para las operaciones (GET, POST, PUT, DELETE)
  - Sin verbos en la URL (/api/auth/login, no /api/login-user)
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from core.interfaces.api import views
from core.interfaces.api import admin_views

urlpatterns = [
    # ── Health ─────────────────────────────────────────────────────
    path("health/", views.HealthCheckView.as_view(), name="health-check"),

    # ── Auth — Registro y login ─────────────────────────────────────
    path("auth/register/", views.RegisterView.as_view(), name="auth-register"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    path("auth/logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", views.MeView.as_view(), name="auth-me"),

    # Renovar access_token usando refresh_token (SimpleJWT built-in)
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # ── Auth — Verificación de email ───────────────────────────────
    path("auth/verify-email/", views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path(
        "auth/verify-email/resend/",
        views.ResendVerificationEmailView.as_view(),
        name="auth-verify-email-resend",
    ),

    # ── Auth — Recuperación de contraseña ──────────────────────────
    path(
        "auth/password-reset/",
        views.PasswordResetRequestView.as_view(),
        name="auth-password-reset",
    ),
    path(
        "auth/password-reset/confirm/",
        views.PasswordResetConfirmView.as_view(),
        name="auth-password-reset-confirm",
    ),

    # ── Auth — Cambio de contraseña (autenticado) ──────────────────
    path(
        "auth/change-password/",
        views.ChangePasswordView.as_view(),
        name="auth-change-password",
    ),    
    path(
        "auth/delete-account/",
        views.DeleteAccountView.as_view(),
        name="auth-delete-account",
    ),
    # ── Auth — 2FA (TOTP / Google Authenticator) ───────────────────
    path("auth/2fa/setup/", views.Setup2FAView.as_view(), name="auth-2fa-setup"),
    path("auth/2fa/enable/", views.Enable2FAView.as_view(), name="auth-2fa-enable"),
    path("auth/2fa/disable/", views.Disable2FAView.as_view(), name="auth-2fa-disable"),
    path("auth/2fa/login/", views.Verify2FALoginView.as_view(), name="auth-2fa-login"),
    path(
        "auth/2fa/recovery-codes/",
        views.Regenerate2FARecoveryCodesView.as_view(),
        name="auth-2fa-recovery-codes",
    ),

    # ── Assets ──────────────────────────────────────────────────────
    path("assets/", views.AssetListView.as_view(), name="asset-list"),
    path("assets/sparklines/", views.AssetSparklinesView.as_view(), name="asset-sparklines"),
    path("assets/<str:symbol>/info/", views.AssetDetailInfoView.as_view(), name="asset-detail-info"),
    path("assets/<str:symbol>/ohlcv/", views.AssetOhlcvView.as_view(), name="asset-ohlcv"),

    # ── Analysis ────────────────────────────────────────────────────
    path("analysis/run/", views.RunAnalysisView.as_view(), name="analysis-run"),
    path("analysis/calculate/", views.CalculateAnalysisView.as_view(), name="analysis-calculate"),
    path("analysis/signals/", views.SignalsDashboardView.as_view(), name="analysis-signals"),
    path("analysis/predict/", views.PredictPriceView.as_view(), name="analysis-predict"),
    path("analysis/patterns/", views.DetectPatternsView.as_view(), name="analysis-patterns"),
    path("analysis/backtest/", views.RunBacktestView.as_view(), name="analysis-backtest"),
    path("analysis/strategies/", views.AvailableStrategiesView.as_view(), name="analysis-strategies"),

    # ── Market Intelligence ─────────────────────────────────────────
    path("market/overview/", views.MarketOverviewView.as_view(), name="market-overview"),
    path("market/fx/", views.FxRatesView.as_view(), name="market-fx"),
    path("blockchain/metrics/", views.BlockchainMetricsView.as_view(), name="blockchain-metrics"),
    path("blockchain/multichain/", views.MultiChainStatsView.as_view(), name="blockchain-multichain"),
    path("news/", views.NewsFeedView.as_view(), name="news-feed"),

    # ── Admin ───────────────────────────────────────────────────────
    path("admin/users/", admin_views.AdminUserListView.as_view(), name="admin-user-list"),
    path("admin/users/<int:user_id>/", admin_views.AdminUserDetailView.as_view(), name="admin-user-detail"),
    path(
        "admin/users/<int:user_id>/resend-verification/",
        admin_views.AdminResendVerificationView.as_view(),
        name="admin-user-resend-verification",
    ),
    path("admin/market/sync/", admin_views.AdminMarketSyncView.as_view(), name="admin-market-sync"),

    # ── Portfolio ────────────────────────────────────────────────────
    path("portfolio/", views.PortfolioView.as_view(), name="portfolio-summary"),
    path("portfolio/trades/", views.TradeListView.as_view(), name="portfolio-trades"),
    path("portfolio/trades/<int:trade_id>/", views.TradeDetailView.as_view(), name="portfolio-trade-detail"),

    # ── Portfolio — Posiciones explícitas ────────────────────────────
    path("portfolio/positions/", views.PositionListView.as_view(), name="position-list"),
    path("portfolio/positions/<int:position_id>/", views.PositionDetailView.as_view(), name="position-detail"),
    path("portfolio/positions/<int:position_id>/add/", views.PositionAddView.as_view(), name="position-add"),
    path("portfolio/positions/<int:position_id>/close/", views.PositionCloseView.as_view(), name="position-close"),

    # ── Alerts ───────────────────────────────────────────────────────
    path("alerts/", views.AlertListView.as_view(), name="alert-list"),
    path("alerts/<int:alert_id>/", views.AlertDetailView.as_view(), name="alert-detail"),
    path("alerts/<int:alert_id>/toggle/", views.AlertToggleView.as_view(), name="alert-toggle"),

    # ── Watchlist ────────────────────────────────────────────────────
    path("watchlist/", views.WatchlistView.as_view(), name="watchlist-list"),
    path("watchlist/<str:symbol>/", views.WatchlistItemView.as_view(), name="watchlist-detail"),
]
