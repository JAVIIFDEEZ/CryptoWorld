"""
tests/integration/test_api_endpoints.py — Tests de integración de la API.

Verifican que los endpoints HTTP funcionan correctamente de extremo a extremo:
  - Rutas correctas
  - Códigos de estado HTTP correctos
  - Estructura de respuesta JSON correcta
  - Autenticación JWT funcionando

Marcados con @pytest.mark.integration; requieren base de datos de test.
"""

import pytest


class TestHealthEndpoint:

    @pytest.mark.integration
    def test_health_returns_200(self, api_client):
        response = api_client.get("/api/health/")
        assert response.status_code == 200
        assert response.data["status"] == "ok"

    @pytest.mark.integration
    def test_health_no_auth_required(self, api_client):
        """El health check debe ser público."""
        response = api_client.get("/api/health/")
        assert response.status_code == 200


class TestAuthEndpoints:

    @pytest.mark.integration
    def test_register_creates_user(self, api_client, db):
        payload = {
            "email": "new@example.com",
            "username": "newuser",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        response = api_client.post("/api/auth/register/", payload, format="json")
        assert response.status_code == 201
        assert response.data["email"] == "new@example.com"

    @pytest.mark.integration
    def test_register_fails_with_duplicate_email(self, api_client, test_user):
        payload = {
            "email": "test@example.com",   # Ya existe (fixture test_user)
            "username": "otheruser",
            "password": "securepass123",
            "password_confirm": "securepass123",
        }
        response = api_client.post("/api/auth/register/", payload, format="json")
        assert response.status_code == 400

    @pytest.mark.integration
    def test_login_returns_tokens(self, api_client, test_user):
        payload = {"email": "test@example.com", "password": "testpass123"}
        response = api_client.post("/api/auth/login/", payload, format="json")
        assert response.status_code == 200
        assert "access_token" in response.data
        assert "refresh_token" in response.data

    @pytest.mark.integration
    def test_login_fails_with_wrong_password(self, api_client, test_user):
        payload = {"email": "test@example.com", "password": "wrongpassword"}
        response = api_client.post("/api/auth/login/", payload, format="json")
        assert response.status_code == 401


class TestAssetsEndpoint:

    @pytest.mark.integration
    def test_assets_requires_authentication(self, api_client):
        response = api_client.get("/api/assets/")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_assets_returns_list_when_authenticated(self, authenticated_client):
        response = authenticated_client.get("/api/assets/")
        assert response.status_code == 200
        assert isinstance(response.data, list)
