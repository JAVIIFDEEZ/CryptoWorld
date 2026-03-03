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

    # ── Auth ────────────────────────────────────────────────────────
    path("auth/register/", views.RegisterView.as_view(), name="auth-register"),
    path("auth/login/", views.LoginView.as_view(), name="auth-login"),
    # Renovar access_token usando refresh_token (SimpleJWT built-in)
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # ── Assets ──────────────────────────────────────────────────────
    path("assets/", views.AssetListView.as_view(), name="asset-list"),

    # ── Analysis ────────────────────────────────────────────────────
    path("analysis/run/", views.RunAnalysisView.as_view(), name="analysis-run"),
]
