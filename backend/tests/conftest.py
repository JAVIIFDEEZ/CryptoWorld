"""
tests/conftest.py — Fixtures compartidas de pytest.

Los fixtures son configuraciones reutilizables entre tests.
Este archivo es detectado automáticamente por pytest.
"""

import logging

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture(autouse=True)
def _clear_cache():
    """
    Limpia la cache Redis antes de cada test.

    Evita contaminación cruzada: contadores de rate limiting
    (ScopedRateThrottle) y respuestas cacheadas de tests anteriores.
    """
    try:
        cache.clear()
    except Exception:
        # Sin Redis los tests que no dependen de la cache deben poder
        # correr igualmente, pero el motivo se registra: un fallo mudo
        # aquí explicaría después resultados desconcertantes en los
        # tests de throttling.
        logging.getLogger(__name__).warning(
            "Cache no disponible al preparar el test", exc_info=True
        )
    yield


@pytest.fixture
def api_client():
    """Cliente HTTP de DRF para tests de la API."""
    return APIClient()


@pytest.fixture
def test_user(db):
    """Usuario de prueba precreado en la base de datos."""
    return User.objects.create_user(
        email="test@example.com",
        username="testuser",
        password="testpass123",
    )


@pytest.fixture
def authenticated_client(api_client, test_user):
    """Cliente HTTP con JWT del usuario de prueba ya configurado."""
    from core.application.services.sessions import build_refresh_token
    refresh = build_refresh_token(test_user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return api_client


@pytest.fixture
def admin_user(db):
    """Administrador de prueba precreado en la base de datos."""
    user = User.objects.create_superuser(
        email="admin@example.com",
        username="adminuser",
        password="adminpass123",
    )
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified"])
    return user


@pytest.fixture
def admin_client(admin_user):
    """Cliente HTTP con JWT del administrador de prueba."""
    from core.application.services.sessions import build_refresh_token
    client = APIClient()
    refresh = build_refresh_token(admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client
