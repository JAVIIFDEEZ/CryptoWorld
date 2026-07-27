"""
tests/integration/test_account_and_admin.py — Tests de cuenta y administración.

Cubren las funcionalidades añadidas en la fase de profesionalización:
  - Preferencias persistentes (GET/PATCH /api/auth/me/)
  - Protecciones del panel de administración
  - Códigos de recuperación 2FA (flujo completo de login)
  - Health check con componentes
  - Fallback síncrono de dispatch_task sin broker Celery
"""

import pyotp
import pytest


class TestMePreferences:

    @pytest.mark.integration
    def test_me_includes_preference_defaults(self, authenticated_client):
        response = authenticated_client.get("/api/auth/me/")
        assert response.status_code == 200
        assert response.data["preferred_currency"] == "usd"
        assert response.data["notify_price_alerts"] is True
        assert response.data["notify_market_digest"] is False

    @pytest.mark.integration
    def test_patch_updates_preferences(self, authenticated_client, test_user):
        response = authenticated_client.patch(
            "/api/auth/me/",
            {"preferred_currency": "eur", "notify_market_digest": True},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["preferred_currency"] == "eur"
        assert response.data["notify_market_digest"] is True

        test_user.refresh_from_db()
        assert test_user.preferred_currency == "eur"
        assert test_user.notify_market_digest is True

    @pytest.mark.integration
    def test_patch_rejects_empty_body(self, authenticated_client):
        response = authenticated_client.patch("/api/auth/me/", {}, format="json")
        assert response.status_code == 400

    @pytest.mark.integration
    def test_patch_rejects_invalid_currency(self, authenticated_client):
        response = authenticated_client.patch(
            "/api/auth/me/", {"preferred_currency": "jpy"}, format="json"
        )
        assert response.status_code == 400


class TestAdminProtections:

    @pytest.mark.integration
    def test_non_admin_cannot_list_users(self, authenticated_client):
        response = authenticated_client.get("/api/admin/users/")
        assert response.status_code == 403

    @pytest.mark.integration
    def test_admin_list_includes_date_joined(self, admin_client):
        response = admin_client.get("/api/admin/users/")
        assert response.status_code == 200
        assert "date_joined" in response.data[0]

    @pytest.mark.integration
    def test_admin_search_filters_by_email(self, admin_client, test_user):
        response = admin_client.get("/api/admin/users/", {"search": "test@example"})
        assert response.status_code == 200
        emails = [u["email"] for u in response.data]
        assert "test@example.com" in emails
        assert "admin@example.com" not in emails

    @pytest.mark.integration
    def test_admin_cannot_block_self(self, admin_client, admin_user):
        response = admin_client.patch(
            f"/api/admin/users/{admin_user.pk}/", {"is_active": False}, format="json"
        )
        assert response.status_code == 400
        admin_user.refresh_from_db()
        assert admin_user.is_active is True

    @pytest.mark.integration
    def test_admin_cannot_demote_self(self, admin_client, admin_user):
        response = admin_client.patch(
            f"/api/admin/users/{admin_user.pk}/", {"is_admin": False}, format="json"
        )
        assert response.status_code == 400
        admin_user.refresh_from_db()
        assert admin_user.is_staff is True

    @pytest.mark.integration
    def test_admin_can_block_other_user(self, admin_client, test_user):
        response = admin_client.patch(
            f"/api/admin/users/{test_user.pk}/", {"is_active": False}, format="json"
        )
        assert response.status_code == 200
        test_user.refresh_from_db()
        assert test_user.is_active is False

    @pytest.mark.integration
    def test_resend_verification_rejected_if_verified(self, admin_client, test_user):
        test_user.is_email_verified = True
        test_user.save(update_fields=["is_email_verified"])
        response = admin_client.post(
            f"/api/admin/users/{test_user.pk}/resend-verification/"
        )
        assert response.status_code == 400

    @pytest.mark.integration
    def test_create_admin_rejects_weak_password(self, admin_client):
        response = admin_client.post(
            "/api/admin/users/",
            {"email": "new-admin@example.com", "username": "newadmin", "password": "12345678"},
            format="json",
        )
        assert response.status_code == 400


class Test2FARecoveryCodes:

    @staticmethod
    def _enable_2fa(client) -> list[str]:
        """Setup + enable de 2FA; devuelve los códigos de recuperación."""
        setup = client.post("/api/auth/2fa/setup/")
        assert setup.status_code == 200
        secret = setup.data["totp_secret"]

        enable = client.post(
            "/api/auth/2fa/enable/",
            {"totp_code": pyotp.TOTP(secret).now()},
            format="json",
        )
        assert enable.status_code == 200
        return enable.data["recovery_codes"]

    @pytest.mark.integration
    def test_enable_returns_ten_recovery_codes(self, authenticated_client):
        codes = self._enable_2fa(authenticated_client)
        assert len(codes) == 10
        assert all("-" in code for code in codes)

    @pytest.mark.integration
    def test_login_with_recovery_code_consumes_it(self, api_client, authenticated_client, test_user):
        test_user.is_email_verified = True
        test_user.save(update_fields=["is_email_verified"])
        codes = self._enable_2fa(authenticated_client)

        # Paso 1 del login: credenciales correctas → pre_auth_token
        login = api_client.post(
            "/api/auth/login/",
            {"email": "test@example.com", "password": "testpass123"},
            format="json",
        )
        assert login.status_code == 200
        assert login.data["requires_2fa"] is True
        pre_auth = login.data["pre_auth_token"]

        # Paso 2 con código de recuperación en lugar de TOTP
        verify = api_client.post(
            "/api/auth/2fa/login/",
            {"pre_auth_token": pre_auth, "recovery_code": codes[0]},
            format="json",
        )
        assert verify.status_code == 200
        assert "access_token" in verify.data

        # El mismo código no puede reutilizarse
        login2 = api_client.post(
            "/api/auth/login/",
            {"email": "test@example.com", "password": "testpass123"},
            format="json",
        )
        verify2 = api_client.post(
            "/api/auth/2fa/login/",
            {"pre_auth_token": login2.data["pre_auth_token"], "recovery_code": codes[0]},
            format="json",
        )
        assert verify2.status_code == 401

    @pytest.mark.integration
    def test_2fa_login_requires_exactly_one_factor(self, api_client, db):
        response = api_client.post(
            "/api/auth/2fa/login/",
            {"pre_auth_token": "x"},
            format="json",
        )
        assert response.status_code == 400


class TestHealthComponents:

    @pytest.mark.integration
    def test_health_reports_components(self, api_client, db):
        response = api_client.get("/api/health/")
        assert response.status_code == 200
        components = response.data["components"]
        assert components["database"] == "ok"
        assert "cache" in components
        assert "celery_broker" in components
        assert components["email_backend"] in ("sendgrid", "smtp", "console")


class TestDispatchTaskFallback:

    @pytest.mark.unit
    def test_falls_back_to_sync_when_broker_unavailable(self, monkeypatch):
        """Si .delay() falla (sin broker), la tarea se ejecuta con .apply()."""
        from core import tasks

        executed = {}

        def failing_delay(*args, **kwargs):
            raise RuntimeError("broker no disponible")

        def fake_apply(args=(), kwargs=None):
            executed["args"] = args
            return "eager-result"

        monkeypatch.setattr(tasks.send_verification_email, "delay", failing_delay)
        monkeypatch.setattr(tasks.send_verification_email, "apply", fake_apply)

        result = tasks.dispatch_task(tasks.send_verification_email, 42)

        assert result == "eager-result"
        assert executed["args"] == (42,)


class TestUsernameChange:

    @pytest.mark.integration
    def test_patch_updates_username(self, authenticated_client, test_user):
        response = authenticated_client.patch(
            "/api/auth/me/", {"username": "nuevonombre"}, format="json"
        )
        assert response.status_code == 200
        assert response.data["username"] == "nuevonombre"
        test_user.refresh_from_db()
        assert test_user.username == "nuevonombre"

    @pytest.mark.integration
    def test_patch_rejects_duplicate_username(self, authenticated_client, admin_user):
        response = authenticated_client.patch(
            "/api/auth/me/", {"username": "adminuser"}, format="json"
        )
        assert response.status_code == 400

    @pytest.mark.integration
    def test_patch_rejects_short_username(self, authenticated_client):
        response = authenticated_client.patch(
            "/api/auth/me/", {"username": "ab"}, format="json"
        )
        assert response.status_code == 400


class TestEmailChange:

    @pytest.mark.integration
    def test_request_requires_correct_password(self, authenticated_client):
        response = authenticated_client.post(
            "/api/auth/change-email/",
            {"new_email": "nuevo@example.com", "password": "incorrecta"},
            format="json",
        )
        assert response.status_code == 400

    @pytest.mark.integration
    def test_request_rejects_email_in_use(self, authenticated_client, admin_user):
        response = authenticated_client.post(
            "/api/auth/change-email/",
            {"new_email": "admin@example.com", "password": "testpass123"},
            format="json",
        )
        assert response.status_code == 400

    @pytest.mark.integration
    def test_request_sets_pending_email(self, authenticated_client, test_user):
        response = authenticated_client.post(
            "/api/auth/change-email/",
            {"new_email": "Nuevo@Example.com", "password": "testpass123"},
            format="json",
        )
        assert response.status_code == 200
        test_user.refresh_from_db()
        # Normalizado a minusculas; el email de login NO cambia todavia
        assert test_user.pending_email == "nuevo@example.com"
        assert test_user.email == "test@example.com"

    @pytest.mark.integration
    def test_confirm_swaps_email_and_verifies(self, authenticated_client, test_user, api_client):
        from django.core import signing
        from core.application.use_cases.change_email import EMAIL_CHANGE_SALT

        # Peticion previa que deja la direccion pendiente
        authenticated_client.post(
            "/api/auth/change-email/",
            {"new_email": "nuevo@example.com", "password": "testpass123"},
            format="json",
        )

        token = signing.dumps(
            {"user_id": test_user.pk, "new_email": "nuevo@example.com"},
            salt=EMAIL_CHANGE_SALT,
        )
        response = api_client.post(
            "/api/auth/change-email/confirm/", {"token": token}, format="json"
        )
        assert response.status_code == 200

        test_user.refresh_from_db()
        assert test_user.email == "nuevo@example.com"
        assert test_user.pending_email is None
        assert test_user.is_email_verified is True

    @pytest.mark.integration
    def test_confirm_rejects_token_without_pending_request(self, api_client, test_user):
        from django.core import signing
        from core.application.use_cases.change_email import EMAIL_CHANGE_SALT

        # Token bien firmado pero sin peticion pendiente en BD
        token = signing.dumps(
            {"user_id": test_user.pk, "new_email": "otro@example.com"},
            salt=EMAIL_CHANGE_SALT,
        )
        response = api_client.post(
            "/api/auth/change-email/confirm/", {"token": token}, format="json"
        )
        assert response.status_code == 400

    @pytest.mark.integration
    def test_confirm_rejects_garbage_token(self, api_client, db):
        response = api_client.post(
            "/api/auth/change-email/confirm/", {"token": "no-es-un-token"}, format="json"
        )
        assert response.status_code == 400
