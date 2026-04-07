"""
interfaces/api/admin_urls.py — Enrutador de endpoints de administración.

Todos los endpoints bajo /api/admin/ requieren autenticación con rol admin.
"""

from django.urls import path
from core.interfaces.api import admin_views

urlpatterns = [
    # ── Stats ──────────────────────────────────────────────────────
    path("stats/", admin_views.AdminStatsView.as_view(), name="admin-stats"),

    # ── Users ──────────────────────────────────────────────────────
    path("users/", admin_views.AdminUserListView.as_view(), name="admin-user-list"),
    path("users/<int:user_id>/", admin_views.AdminUserDetailView.as_view(), name="admin-user-detail"),

    # ── Assets ─────────────────────────────────────────────────────
    path("assets/", admin_views.AdminAssetListView.as_view(), name="admin-asset-list"),
    path("assets/<int:asset_id>/", admin_views.AdminAssetDetailView.as_view(), name="admin-asset-detail"),
]
