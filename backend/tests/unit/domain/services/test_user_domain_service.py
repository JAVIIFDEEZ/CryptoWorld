"""
tests/unit/domain/services/test_user_domain_service.py — Tests de UserDomainService.

UserDomainService encapsula reglas de negocio que requieren consultar
el repositorio de usuarios. Se testea con un repositorio stub (in-memory)
que implementa la interfaz IUserRepository.

Patrón usado: Stub — implementación mínima de la interfaz para aislar el test.
No necesitan base de datos real ni Django.
Ejecutar: pytest tests/unit/domain/services/test_user_domain_service.py -v
"""

import pytest
from typing import Optional
from core.domain.services.user_domain_service import UserDomainService
from core.domain.repositories.user_repository import IUserRepository
from core.domain.entities.user import UserEntity


# ── Stub del repositorio ───────────────────────────────────────────

class StubUserRepository(IUserRepository):
    """
    Implementación stub de IUserRepository para tests.
    Almacena usuarios en memoria; no toca la base de datos.
    """

    def __init__(self, existing_emails: list[str] = None):
        self._emails = set(existing_emails or [])

    def exists_by_email(self, email: str) -> bool:
        return email in self._emails

    def get_by_id(self, user_id: int) -> Optional[UserEntity]:
        return None

    def get_by_email(self, email: str) -> Optional[UserEntity]:
        return None

    def save(self, user: UserEntity) -> UserEntity:
        self._emails.add(user.email)
        return user


# ── TestUserDomainService ──────────────────────────────────────────

class TestUserDomainServiceIsEmailAvailable:
    """Tests del método is_email_available."""

    @pytest.mark.unit
    def test_email_available_when_not_registered(self):
        repo = StubUserRepository(existing_emails=[])
        service = UserDomainService(repo)
        assert service.is_email_available("new@example.com") is True

    @pytest.mark.unit
    def test_email_not_available_when_already_registered(self):
        repo = StubUserRepository(existing_emails=["taken@example.com"])
        service = UserDomainService(repo)
        assert service.is_email_available("taken@example.com") is False

    @pytest.mark.unit
    def test_email_available_when_other_emails_exist(self):
        repo = StubUserRepository(existing_emails=["other@example.com", "another@example.com"])
        service = UserDomainService(repo)
        assert service.is_email_available("new@example.com") is True

    @pytest.mark.unit
    def test_email_not_available_is_case_sensitive(self):
        """El servicio delega a exists_by_email del repo, que es case-sensitive aquí."""
        repo = StubUserRepository(existing_emails=["User@Example.com"])
        service = UserDomainService(repo)
        # El email en minúsculas es distinto al registrado
        assert service.is_email_available("user@example.com") is True


class TestUserDomainServiceEnsureEmailAvailable:
    """Tests del método ensure_email_available."""

    @pytest.mark.unit
    def test_ensure_available_does_not_raise_when_free(self):
        repo = StubUserRepository(existing_emails=[])
        service = UserDomainService(repo)
        # No debe lanzar excepción
        service.ensure_email_available("free@example.com")

    @pytest.mark.unit
    def test_ensure_available_raises_value_error_when_taken(self):
        repo = StubUserRepository(existing_emails=["taken@example.com"])
        service = UserDomainService(repo)
        with pytest.raises(ValueError, match="ya está registrado"):
            service.ensure_email_available("taken@example.com")

    @pytest.mark.unit
    def test_error_message_contains_the_email(self):
        email = "specific@example.com"
        repo = StubUserRepository(existing_emails=[email])
        service = UserDomainService(repo)
        with pytest.raises(ValueError, match=email):
            service.ensure_email_available(email)

    @pytest.mark.unit
    def test_ensure_available_multiple_calls_with_different_emails(self):
        repo = StubUserRepository(existing_emails=["taken@example.com"])
        service = UserDomainService(repo)
        # Email libre → no lanza
        service.ensure_email_available("free@example.com")
        # Email ocupado → lanza
        with pytest.raises(ValueError):
            service.ensure_email_available("taken@example.com")


class TestUserDomainServiceWithRepository:
    """Tests de interacción entre el servicio y el repositorio."""

    @pytest.mark.unit
    def test_service_receives_repository_via_injection(self):
        """Verifica que el servicio almacena la referencia al repositorio."""
        repo = StubUserRepository()
        service = UserDomainService(repo)
        assert service._user_repo is repo

    @pytest.mark.unit
    def test_email_becomes_unavailable_after_saving_user(self):
        repo = StubUserRepository()
        service = UserDomainService(repo)

        assert service.is_email_available("new@example.com") is True

        user = UserEntity(email="new@example.com", username="newuser")
        repo.save(user)

        assert service.is_email_available("new@example.com") is False
