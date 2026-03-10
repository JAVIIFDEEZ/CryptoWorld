"""
tests/unit/domain/entities/test_user.py — Tests unitarios de UserEntity.

Verifica todas las reglas de negocio de la entidad de usuario:
  - Construcción válida e inválida
  - Valores por defecto
  - Operaciones de dominio (deactivate, promote_to_staff)
  - Campos de autenticación extendida (2FA, email verified)

No necesitan base de datos ni Django. Solo lógica pura.
Ejecutar: pytest tests/unit/domain/entities/test_user.py -v
"""

import pytest
from datetime import datetime
from core.domain.entities.user import UserEntity


class TestUserEntityCreation:
    """Tests de construcción y validación inicial de UserEntity."""

    @pytest.mark.unit
    def test_create_valid_user_minimum_fields(self):
        user = UserEntity(email="user@example.com", username="testuser")
        assert user.email == "user@example.com"
        assert user.username == "testuser"

    @pytest.mark.unit
    def test_default_is_active_true(self):
        user = UserEntity(email="user@example.com", username="testuser")
        assert user.is_active is True

    @pytest.mark.unit
    def test_default_is_staff_false(self):
        user = UserEntity(email="user@example.com", username="testuser")
        assert user.is_staff is False

    @pytest.mark.unit
    def test_default_id_is_none(self):
        user = UserEntity(email="user@example.com", username="testuser")
        assert user.id is None

    @pytest.mark.unit
    def test_default_is_email_verified_false(self):
        user = UserEntity(email="user@example.com", username="testuser")
        assert user.is_email_verified is False

    @pytest.mark.unit
    def test_default_totp_secret_is_none(self):
        user = UserEntity(email="user@example.com", username="testuser")
        assert user.totp_secret is None

    @pytest.mark.unit
    def test_default_is_2fa_enabled_false(self):
        user = UserEntity(email="user@example.com", username="testuser")
        assert user.is_2fa_enabled is False

    @pytest.mark.unit
    def test_date_joined_is_set_automatically(self):
        user = UserEntity(email="user@example.com", username="testuser")
        assert isinstance(user.date_joined, datetime)

    @pytest.mark.unit
    def test_create_user_with_all_fields(self):
        user = UserEntity(
            email="admin@example.com",
            username="adminuser",
            is_active=True,
            is_staff=True,
            id=42,
            is_email_verified=True,
            totp_secret="JBSWY3DPEHPK3PXP",
            is_2fa_enabled=True,
        )
        assert user.id == 42
        assert user.is_staff is True
        assert user.is_email_verified is True
        assert user.totp_secret == "JBSWY3DPEHPK3PXP"
        assert user.is_2fa_enabled is True


class TestUserEntityEmailValidation:
    """Tests de validación del campo email."""

    @pytest.mark.unit
    def test_email_without_at_raises_value_error(self):
        with pytest.raises(ValueError, match="Email inválido"):
            UserEntity(email="invalidemail.com", username="testuser")

    @pytest.mark.unit
    def test_empty_email_raises_value_error(self):
        with pytest.raises(ValueError, match="Email inválido"):
            UserEntity(email="", username="testuser")

    @pytest.mark.unit
    def test_email_with_spaces_does_not_raise(self):
        """
        UserEntity solo valida presencia de '@'. La validación de formato
        completo (regex) es responsabilidad del Value Object Email.
        'user @example.com' contiene '@' y pasa el check de la entidad.
        """
        user = UserEntity(email="user @example.com", username="testuser")
        assert "@" in user.email

    @pytest.mark.unit
    def test_email_only_at_does_not_raise(self):
        """
        '@' solo contiene '@', por lo que pasa la validación mínima
        de UserEntity. El formato estricto lo valida el Value Object Email.
        """
        user = UserEntity(email="@", username="testuser")
        assert user.email == "@"


class TestUserEntityUsernameValidation:
    """Tests de validación del campo username."""

    @pytest.mark.unit
    def test_username_two_chars_raises_value_error(self):
        with pytest.raises(ValueError, match="al menos 3 caracteres"):
            UserEntity(email="user@example.com", username="ab")

    @pytest.mark.unit
    def test_username_one_char_raises_value_error(self):
        with pytest.raises(ValueError, match="al menos 3 caracteres"):
            UserEntity(email="user@example.com", username="a")

    @pytest.mark.unit
    def test_empty_username_raises_value_error(self):
        with pytest.raises(ValueError, match="al menos 3 caracteres"):
            UserEntity(email="user@example.com", username="")

    @pytest.mark.unit
    def test_username_exactly_three_chars_is_valid(self):
        user = UserEntity(email="user@example.com", username="abc")
        assert user.username == "abc"

    @pytest.mark.unit
    def test_username_long_string_is_valid(self):
        user = UserEntity(email="user@example.com", username="a" * 150)
        assert len(user.username) == 150


class TestUserEntityDomainOperations:
    """Tests de las operaciones de dominio (métodos de negocio)."""

    @pytest.mark.unit
    def test_deactivate_sets_is_active_false(self):
        user = UserEntity(email="user@example.com", username="testuser")
        user.deactivate()
        assert user.is_active is False

    @pytest.mark.unit
    def test_deactivate_already_inactive_stays_inactive(self):
        user = UserEntity(email="user@example.com", username="testuser", is_active=False)
        user.deactivate()
        assert user.is_active is False

    @pytest.mark.unit
    def test_promote_to_staff_sets_is_staff_true(self):
        user = UserEntity(email="user@example.com", username="testuser")
        user.promote_to_staff()
        assert user.is_staff is True

    @pytest.mark.unit
    def test_promote_to_staff_already_staff_stays_staff(self):
        user = UserEntity(email="user@example.com", username="testuser", is_staff=True)
        user.promote_to_staff()
        assert user.is_staff is True
