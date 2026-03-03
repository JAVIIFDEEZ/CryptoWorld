"""
urls.py — Enrutador raíz de la aplicación Django.

Responsabilidad: conectar los endpoints de alto nivel (prefijos de URL)
con los routers de cada módulo. Esta capa NO define lógica de negocio,
solo delega en los routers de la capa interfaces/.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Panel de administración de Django (solo para desarrollo/debug)
    path("admin/", admin.site.urls),

    # Todos los endpoints de la API REST se agrupan bajo /api/
    # La responsabilidad de rutas internas la tiene core/interfaces/api/urls.py
    path("api/", include("core.interfaces.api.urls")),
]
