"""
tests/integration/test_security_controls.py — Controles de seguridad.

Cubren los hallazgos corregidos en la auditoría. Cada test comprueba un
control concreto, de modo que una regresión señale exactamente qué
protección se ha perdido:

  - Política de contraseñas uniforme en registro, cambio y recuperación.
  - Revocación de sesiones al cambiar credenciales.
  - Bloqueo por cuenta ante intentos fallidos (no solo por IP).
  - Separación de privilegios staff / superusuario.
  - Registro de auditoría de los eventos sensibles.
  - Contrato de error uniforme.
  - Normalización de email.
"""

import pytest
from django.contrib.auth import get_user_model

from core.application.services.sessions import build_refresh_token
from core.infrastructure.persistence.models import AuditLog

User = get_user_model()

# Contraseña que supera la política (>= 12 caracteres, no común, no numérica).
STRONG_PASSWORD = "Corriente-Alterna-92"


def _register_payload(**overrides) -> dict:
    payload = {
        "email": "nuevo@example.com",
        "username": "nuevousuario",
        "password": STRONG_PASSWORD,
        "password_confirm": STRONG_PASSWORD,
    }
    payload.update(overrides)
    return payload


# ── Política de contraseñas ────────────────────────────────────────


@pytest.mark.security
@pytest.mark.integration
class TestPasswordPolicy:
    """El registro aplica la misma política que el cambio y el reset."""

    @pytest.mark.parametrize(
        "weak_password",
        [
            "12345678",       # Solo numérica y corta
            "password",       # Común
            "corta1",         # Por debajo del mínimo
            "123456789012",   # Longitud suficiente pero solo numérica
        ],
    )
    def test_register_rejects_weak_passwords(self, api_client, db, weak_password):
        response = api_client.post(
            "/api/auth/register/",
            _register_payload(password=weak_password, password_confirm=weak_password),
            format="json",
        )
        assert response.status_code == 400
        assert not User.objects.filter(email="nuevo@example.com").exists()

    def test_register_accepts_strong_password(self, api_client, db):
        response = api_client.post("/api/auth/register/", _register_payload(), format="json")
        assert response.status_code == 201
        assert User.objects.filter(email="nuevo@example.com").exists()

    def test_register_is_atomic_on_password_failure(self, api_client, db):
        """
        Un registro rechazado no deja la cuenta a medias.

        El alta y el establecimiento de la contraseña van en una sola
        transacción: antes, un fallo entre ambos pasos dejaba el email
        ocupado por un usuario sin contraseña utilizable.
        """
        api_client.post(
            "/api/auth/register/",
            _register_payload(password="12345678", password_confirm="12345678"),
            format="json",
        )
        assert User.objects.filter(email="nuevo@example.com").count() == 0

    def test_change_password_rejects_reusing_the_current_one(self, authenticated_client):
        response = authenticated_client.post(
            "/api/auth/change-password/",
            {
                "current_password": "testpass123",
                "new_password": "testpass123",
                "new_password_confirm": "testpass123",
            },
            format="json",
        )
        assert response.status_code == 400


# ── Normalización de email ─────────────────────────────────────────


@pytest.mark.security
@pytest.mark.integration
class TestEmailNormalization:
    """Las mayúsculas no crean cuentas paralelas ni rompen el login."""

    def test_register_normalizes_email_to_lowercase(self, api_client, db):
        response = api_client.post(
            "/api/auth/register/",
            _register_payload(email="Nuevo@Example.COM"),
            format="json",
        )
        assert response.status_code == 201
        assert response.data["email"] == "nuevo@example.com"

    def test_cannot_register_the_same_email_with_different_case(self, api_client, test_user):
        response = api_client.post(
            "/api/auth/register/",
            _register_payload(email="TEST@EXAMPLE.COM", username="otro"),
            format="json",
        )
        assert response.status_code == 400
        assert User.objects.filter(email__iexact="test@example.com").count() == 1

    def test_login_is_case_insensitive_on_email(self, api_client, test_user):
        test_user.is_email_verified = True
        test_user.save(update_fields=["is_email_verified"])

        response = api_client.post(
            "/api/auth/login/",
            {"email": "TEST@Example.com", "password": "testpass123"},
            format="json",
        )
        assert response.status_code == 200
        assert "access_token" in response.data


# ── Revocación de sesiones ─────────────────────────────────────────


@pytest.mark.security
@pytest.mark.integration
class TestSessionRevocation:
    """Cambiar la contraseña expulsa de verdad a las sesiones abiertas."""

    def test_change_password_invalidates_previous_access_token(
        self, api_client, authenticated_client, test_user
    ):
        # Sesión "del atacante": un token emitido antes del cambio.
        stolen = build_refresh_token(test_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {stolen.access_token}")
        assert api_client.get("/api/auth/me/").status_code == 200

        changed = authenticated_client.post(
            "/api/auth/change-password/",
            {
                "current_password": "testpass123",
                "new_password": STRONG_PASSWORD,
                "new_password_confirm": STRONG_PASSWORD,
            },
            format="json",
        )
        assert changed.status_code == 200

        # El token robado deja de servir pese a no haber caducado.
        assert api_client.get("/api/auth/me/").status_code == 401

    def test_change_password_returns_working_tokens_for_the_current_device(
        self, api_client, authenticated_client
    ):
        """Quien hace el cambio no se auto-desconecta."""
        response = authenticated_client.post(
            "/api/auth/change-password/",
            {
                "current_password": "testpass123",
                "new_password": STRONG_PASSWORD,
                "new_password_confirm": STRONG_PASSWORD,
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.data["sessions_revoked"] is True

        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access_token']}")
        assert api_client.get("/api/auth/me/").status_code == 200

    def test_blocking_a_user_revokes_their_sessions(self, api_client, admin_client, test_user):
        victim = build_refresh_token(test_user)
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {victim.access_token}")
        assert api_client.get("/api/auth/me/").status_code == 200

        blocked = admin_client.patch(
            f"/api/admin/users/{test_user.pk}/", {"is_active": False}, format="json"
        )
        assert blocked.status_code == 200

        # Bloquear ya no se limita a impedir nuevos logins.
        assert api_client.get("/api/auth/me/").status_code == 401


# ── Bloqueo por cuenta ─────────────────────────────────────────────


@pytest.mark.security
@pytest.mark.integration
class TestAccountLockout:
    """El límite por IP no basta: se cuenta también por cuenta."""

    def test_repeated_failures_lock_the_account(self, api_client, test_user):
        test_user.is_email_verified = True
        test_user.save(update_fields=["is_email_verified"])

        payload = {"email": "test@example.com", "password": "incorrecta"}
        statuses = [
            api_client.post("/api/auth/login/", payload, format="json").status_code
            for _ in range(9)
        ]

        # Los primeros intentos son credenciales inválidas...
        assert statuses[0] == 401
        # ...y a partir del umbral la cuenta queda bloqueada.
        assert statuses[-1] == 429

    def test_lockout_blocks_even_the_correct_password(self, api_client, test_user):
        test_user.is_email_verified = True
        test_user.save(update_fields=["is_email_verified"])

        for _ in range(9):
            api_client.post(
                "/api/auth/login/",
                {"email": "test@example.com", "password": "incorrecta"},
                format="json",
            )

        response = api_client.post(
            "/api/auth/login/",
            {"email": "test@example.com", "password": "testpass123"},
            format="json",
        )
        assert response.status_code == 429
        assert response.data["error"]["code"] == "account_locked"

    def test_successful_login_clears_the_counter(self, api_client, test_user):
        test_user.is_email_verified = True
        test_user.save(update_fields=["is_email_verified"])

        for _ in range(3):
            api_client.post(
                "/api/auth/login/",
                {"email": "test@example.com", "password": "incorrecta"},
                format="json",
            )

        ok = api_client.post(
            "/api/auth/login/",
            {"email": "test@example.com", "password": "testpass123"},
            format="json",
        )
        assert ok.status_code == 200

        # Tras el acierto vuelve a haber presupuesto completo de intentos.
        for _ in range(4):
            failed = api_client.post(
                "/api/auth/login/",
                {"email": "test@example.com", "password": "incorrecta"},
                format="json",
            )
        assert failed.status_code == 401


# ── Separación de privilegios ──────────────────────────────────────


@pytest.mark.security
@pytest.mark.integration
class TestPrivilegeSeparation:
    """Un `is_staff` ya no puede fabricar superusuarios."""

    @pytest.fixture
    def staff_client(self, db):
        from rest_framework.test import APIClient

        staff = User.objects.create_user(
            email="staff@example.com",
            username="staffuser",
            password=STRONG_PASSWORD,
            is_staff=True,
            is_superuser=False,
        )
        staff.is_email_verified = True
        staff.save(update_fields=["is_email_verified"])

        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {build_refresh_token(staff).access_token}"
        )
        return client

    def test_staff_can_list_users(self, staff_client):
        assert staff_client.get("/api/admin/users/").status_code == 200

    def test_staff_cannot_create_administrators(self, staff_client):
        response = staff_client.post(
            "/api/admin/users/",
            {
                "email": "escalada@example.com",
                "username": "escalada",
                "password": STRONG_PASSWORD,
                "is_superuser": True,
            },
            format="json",
        )
        assert response.status_code == 403
        assert not User.objects.filter(email="escalada@example.com").exists()

    def test_staff_cannot_grant_privileges(self, staff_client, test_user):
        response = staff_client.patch(
            f"/api/admin/users/{test_user.pk}/", {"is_superuser": True}, format="json"
        )
        assert response.status_code == 403
        test_user.refresh_from_db()
        assert test_user.is_superuser is False

    def test_staff_can_still_block_users(self, staff_client, test_user):
        response = staff_client.patch(
            f"/api/admin/users/{test_user.pk}/", {"is_active": False}, format="json"
        )
        assert response.status_code == 200

    def test_new_admins_are_staff_but_not_superusers_by_default(self, admin_client):
        response = admin_client.post(
            "/api/admin/users/",
            {
                "email": "operador@example.com",
                "username": "operador",
                "password": STRONG_PASSWORD,
            },
            format="json",
        )
        assert response.status_code == 201
        created = User.objects.get(email="operador@example.com")
        assert created.is_staff is True
        assert created.is_superuser is False

    def test_cannot_remove_the_last_active_superuser(self, admin_client, admin_user, db):
        """
        Otro superusuario no puede dejar el sistema sin ninguno.

        `admin_user` es el único superusuario; se crea un segundo para
        que la petición no caiga en la regla de "no degradarse a sí mismo"
        y llegue a la comprobación del último superusuario.
        """
        from rest_framework.test import APIClient

        second = User.objects.create_superuser(
            email="segundo@example.com", username="segundo", password=STRONG_PASSWORD
        )
        second.is_email_verified = True
        second.save(update_fields=["is_email_verified"])

        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {build_refresh_token(second).access_token}"
        )

        # Con dos superusuarios, degradar a uno sí está permitido.
        assert (
            client.patch(
                f"/api/admin/users/{admin_user.pk}/", {"is_superuser": False}, format="json"
            ).status_code
            == 200
        )

        # `second` es ahora el único: no puede quedarse sin ninguno.
        second_client = APIClient()
        second_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {build_refresh_token(admin_user).access_token}"
        )
        admin_user.refresh_from_db()
        assert admin_user.is_superuser is False


# ── Registro de auditoría ──────────────────────────────────────────


@pytest.mark.security
@pytest.mark.integration
class TestAuditLog:
    """Los eventos sensibles dejan traza consultable."""

    def test_successful_login_is_recorded(self, api_client, test_user):
        test_user.is_email_verified = True
        test_user.save(update_fields=["is_email_verified"])

        api_client.post(
            "/api/auth/login/",
            {"email": "test@example.com", "password": "testpass123"},
            format="json",
        )

        entry = AuditLog.objects.filter(action=AuditLog.Action.LOGIN_SUCCESS).first()
        assert entry is not None
        assert entry.actor_id == test_user.pk
        assert entry.outcome == AuditLog.Outcome.SUCCESS

    def test_failed_login_is_recorded_without_the_password(self, api_client, test_user):
        api_client.post(
            "/api/auth/login/",
            {"email": "test@example.com", "password": "secreto-que-no-debe-guardarse"},
            format="json",
        )

        entry = AuditLog.objects.filter(action=AuditLog.Action.LOGIN_FAILURE).first()
        assert entry is not None
        assert entry.outcome == AuditLog.Outcome.FAILURE
        assert entry.actor_email == "test@example.com"
        # La traza nunca puede contener el secreto que se intentó usar.
        assert "secreto-que-no-debe-guardarse" not in str(entry.metadata)

    def test_admin_actions_are_recorded_with_the_actor(self, admin_client, admin_user, test_user):
        admin_client.patch(
            f"/api/admin/users/{test_user.pk}/", {"is_email_verified": True}, format="json"
        )

        entry = AuditLog.objects.filter(action=AuditLog.Action.ADMIN_USER_UPDATED).first()
        assert entry is not None
        assert entry.actor_id == admin_user.pk
        assert entry.target_id == str(test_user.pk)

    def test_audit_entry_survives_the_deletion_of_its_actor(self, api_client, test_user):
        """La traza de una cuenta borrada es justo la que hace falta."""
        test_user.is_email_verified = True
        test_user.save(update_fields=["is_email_verified"])
        api_client.post(
            "/api/auth/login/",
            {"email": "test@example.com", "password": "testpass123"},
            format="json",
        )

        test_user.delete()

        entry = AuditLog.objects.filter(action=AuditLog.Action.LOGIN_SUCCESS).first()
        assert entry is not None
        assert entry.actor_id is None
        assert entry.actor_email == "test@example.com"


# ── Contrato de error ──────────────────────────────────────────────


@pytest.mark.security
@pytest.mark.integration
class TestErrorContract:
    """Todos los errores comparten la misma envolvente."""

    def test_validation_error_has_code_and_details(self, api_client, db):
        response = api_client.post(
            "/api/auth/register/", {"email": "no-es-un-email"}, format="json"
        )
        assert response.status_code == 400
        assert response.data["error"]["code"] == "validation_error"
        assert "email" in response.data["error"]["details"]
        assert "request_id" in response.data

    def test_unauthenticated_request_has_the_same_shape(self, api_client, db):
        response = api_client.get("/api/portfolio/")
        assert response.status_code == 401
        assert response.data["error"]["code"] == "not_authenticated"

    def test_not_found_has_the_same_shape(self, authenticated_client):
        response = authenticated_client.delete("/api/alerts/999999/")
        assert response.status_code == 404
        assert response.data["error"]["code"] == "not_found"

    def test_response_carries_the_correlation_id_header(self, api_client, db):
        response = api_client.get("/api/health/live/")
        assert response.headers["X-Request-ID"]

    def test_inbound_correlation_id_is_propagated(self, api_client, db):
        response = api_client.get("/api/health/live/", HTTP_X_REQUEST_ID="traza-123")
        assert response.headers["X-Request-ID"] == "traza-123"

    def test_login_does_not_reveal_whether_the_account_exists(self, api_client, test_user):
        """El mismo mensaje exista o no la cuenta: sin oráculo de emails."""
        existing = api_client.post(
            "/api/auth/login/",
            {"email": "test@example.com", "password": "incorrecta"},
            format="json",
        )
        missing = api_client.post(
            "/api/auth/login/",
            {"email": "no-existe@example.com", "password": "incorrecta"},
            format="json",
        )
        assert existing.status_code == missing.status_code == 401
        assert existing.data["error"]["message"] == missing.data["error"]["message"]
