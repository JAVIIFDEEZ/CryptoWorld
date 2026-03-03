"""
tests/conftest.py — Fixtures compartidas de pytest.

Los fixtures son configuraciones reutilizables entre tests.
Este archivo es detectado automáticamente por pytest.
"""

import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

User = get_user_model()


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
