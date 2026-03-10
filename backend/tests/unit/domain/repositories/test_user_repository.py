"""
tests/unit/domain/repositories/test_user_repository.py — Tests del contrato IUserRepository.

IUserRepository es una interfaz abstracta (ABC). Estos tests verifican:
  1. Que no se puede instanciar directamente (principio de contrato)
  2. Que una implementación stub completa satisface el contrato
  3. El comportamiento esperado de cada método del contrato

Patrón usado: In-memory repository stub para tests sin base de datos.
Ejecutar: pytest tests/unit/domain/repositories/test_user_repository.py -v
"""

import pytest
from typing import Optional
from core.domain.repositories.user_repository import IUserRepository
from core.domain.entities.user import UserEntity


# ── Implementación stub in-memory ─────────────────────────────────

class InMemoryUserRepository(IUserRepository):
    """
    Repositorio de usuarios en memoria para verificar el contrato.
    Implementa todos los métodos abstractos de IUserRepository.
    """

    def __init__(self):
        self._store: dict[int, UserEntity] = {}
        self._next_id: int = 1

    def get_by_id(self, user_id: int) -> Optional[UserEntity]:
        return self._store.get(user_id)

    def get_by_email(self, email: str) -> Optional[UserEntity]:
        for user in self._store.values():
            if user.email == email:
                return user
        return None

    def save(self, user: UserEntity) -> UserEntity:
        if user.id is None:
            from dataclasses import replace
            user = replace(user, id=self._next_id)
            self._next_id += 1
        self._store[user.id] = user
        return user

    def exists_by_email(self, email: str) -> bool:
        return any(u.email == email for u in self._store.values())


# ── Tests del contrato abstracto ──────────────────────────────────

class TestIUserRepositoryContract:
    """Verifica que el ABC no se puede instanciar directamente."""

    @pytest.mark.unit
    def test_cannot_instantiate_abstract_repository(self):
        with pytest.raises(TypeError):
            IUserRepository()

    @pytest.mark.unit
    def test_partial_implementation_raises_type_error(self):
        """Una implementación que no define todos los métodos no es válida."""
        class PartialRepo(IUserRepository):
            def get_by_id(self, user_id): return None
            # Faltan get_by_email, save, exists_by_email

        with pytest.raises(TypeError):
            PartialRepo()


# ── Tests del stub in-memory ──────────────────────────────────────

class TestInMemoryUserRepositoryGetById:
    """Tests del método get_by_id."""

    @pytest.mark.unit
    def test_get_by_id_returns_none_when_empty(self):
        repo = InMemoryUserRepository()
        assert repo.get_by_id(1) is None

    @pytest.mark.unit
    def test_get_by_id_returns_user_after_save(self):
        repo = InMemoryUserRepository()
        user = UserEntity(email="user@example.com", username="testuser")
        saved = repo.save(user)
        result = repo.get_by_id(saved.id)
        assert result is not None
        assert result.email == "user@example.com"

    @pytest.mark.unit
    def test_get_by_id_returns_none_for_nonexistent_id(self):
        repo = InMemoryUserRepository()
        user = UserEntity(email="user@example.com", username="testuser")
        repo.save(user)
        assert repo.get_by_id(9999) is None


class TestInMemoryUserRepositoryGetByEmail:
    """Tests del método get_by_email."""

    @pytest.mark.unit
    def test_get_by_email_returns_none_when_empty(self):
        repo = InMemoryUserRepository()
        assert repo.get_by_email("user@example.com") is None

    @pytest.mark.unit
    def test_get_by_email_returns_user_after_save(self):
        repo = InMemoryUserRepository()
        user = UserEntity(email="user@example.com", username="testuser")
        repo.save(user)
        result = repo.get_by_email("user@example.com")
        assert result is not None
        assert result.username == "testuser"

    @pytest.mark.unit
    def test_get_by_email_returns_none_for_unknown_email(self):
        repo = InMemoryUserRepository()
        user = UserEntity(email="user@example.com", username="testuser")
        repo.save(user)
        assert repo.get_by_email("other@example.com") is None


class TestInMemoryUserRepositorySave:
    """Tests del método save."""

    @pytest.mark.unit
    def test_save_assigns_id_to_new_user(self):
        repo = InMemoryUserRepository()
        user = UserEntity(email="user@example.com", username="testuser")
        assert user.id is None
        saved = repo.save(user)
        assert saved.id is not None

    @pytest.mark.unit
    def test_save_two_users_get_sequential_ids(self):
        repo = InMemoryUserRepository()
        u1 = repo.save(UserEntity(email="user1@example.com", username="user1"))
        u2 = repo.save(UserEntity(email="user2@example.com", username="user2"))
        assert u1.id != u2.id

    @pytest.mark.unit
    def test_save_returns_the_saved_entity(self):
        repo = InMemoryUserRepository()
        user = UserEntity(email="user@example.com", username="testuser")
        saved = repo.save(user)
        assert saved.email == "user@example.com"
        assert saved.username == "testuser"


class TestInMemoryUserRepositoryExistsByEmail:
    """Tests del método exists_by_email."""

    @pytest.mark.unit
    def test_exists_returns_false_when_empty(self):
        repo = InMemoryUserRepository()
        assert repo.exists_by_email("user@example.com") is False

    @pytest.mark.unit
    def test_exists_returns_true_after_save(self):
        repo = InMemoryUserRepository()
        user = UserEntity(email="user@example.com", username="testuser")
        repo.save(user)
        assert repo.exists_by_email("user@example.com") is True

    @pytest.mark.unit
    def test_exists_returns_false_for_different_email(self):
        repo = InMemoryUserRepository()
        user = UserEntity(email="user@example.com", username="testuser")
        repo.save(user)
        assert repo.exists_by_email("other@example.com") is False
