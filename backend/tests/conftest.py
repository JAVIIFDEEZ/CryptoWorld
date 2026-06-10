"""
tests/conftest.py — Fixtures compartidas de pytest.

Los fixtures son configuraciones reutilizables entre tests.
Este archivo es detectado automáticamente por pytest.
"""

import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from django.core.cache import cache

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
        pass  # Sin Redis disponible los tests que no lo usan deben poder correr
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
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(test_user)
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
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient()
    refresh = RefreshToken.for_user(admin_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client
