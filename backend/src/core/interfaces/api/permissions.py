"""
interfaces/api/permissions.py — Permisos personalizados de DRF.

Define clases de permisos que se aplican a las views de administración
para restringir el acceso solo a usuarios con rol de admin.
"""

from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """
    Permiso que solo permite acceso a usuarios autenticados con role='admin'.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "admin"
        )
