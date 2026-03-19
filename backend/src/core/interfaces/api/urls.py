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

    # ── Assets ──────────────────────────────────────────────────────
    path("assets/", views.AssetListView.as_view(), name="asset-list"),
    path("assets/<str:symbol>/ohlcv/", views.AssetOhlcvView.as_view(), name="asset-ohlcv"),

    # ── Analysis ────────────────────────────────────────────────────
    path("analysis/run/", views.RunAnalysisView.as_view(), name="analysis-run"),

    # ── Market Intelligence ─────────────────────────────────────────
    path("market/overview/", views.MarketOverviewView.as_view(), name="market-overview"),
    path("blockchain/metrics/", views.BlockchainMetricsView.as_view(), name="blockchain-metrics"),
    path("news/", views.NewsFeedView.as_view(), name="news-feed"),
]
