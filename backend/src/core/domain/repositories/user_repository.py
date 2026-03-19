"""
user_repository.py — Contrato (interfaz) del repositorio de usuarios.

Define las operaciones que el dominio necesita para gestionar usuarios.
No sabe si se usa PostgreSQL, MongoDB, Redis o un archivo JSON.
La capa de infraestructura proporciona la implementación concreta.

Principio aplicado: Inversión de Dependencias (DIP).
"""

from abc import ABC, abstractmethod
from typing import Optional
from core.domain.entities.user import UserEntity


class IUserRepository(ABC):
    """
    Interfaz abstracta del repositorio de usuarios.

    Los casos de uso dependen de esta interfaz, nunca de la
    implementación concreta. Esto permite cambiar la base de datos
    sin tocar la lógica de negocio.
    """

    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[UserEntity]:
        """Obtener usuario por su identificador único."""
        ...

    @abstractmethod
    def get_by_email(self, email: str) -> Optional[UserEntity]:
        """Obtener usuario por email (usado en autenticación)."""
        ...

    @abstractmethod
    def save(self, user: UserEntity) -> UserEntity:
        """Persistir un usuario nuevo o actualizar uno existente."""
        ...

    @abstractmethod
    def delete(self, user_id: int) -> None:
        """Eliminar un usuario del sistema por su ID."""
        ...

    @abstractmethod
    def exists_by_email(self, email: str) -> bool:
        """Comprobar si existe un usuario con ese email."""
        ...
