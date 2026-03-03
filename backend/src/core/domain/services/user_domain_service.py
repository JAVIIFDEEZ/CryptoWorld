"""
user_domain_service.py — Servicio de dominio para usuarios.

Contiene lógica de negocio que involucra más de una entidad
o que requiere acceso al repositorio sin ser un caso de uso completo.

Diferencia clave:
- Entidad: lógica que solo depende de sus propios datos.
- Servicio de dominio: lógica que requiere colaboración entre entidades.
- Caso de uso (application): orquesta todo para cumplir una tarea.
"""

from core.domain.repositories.user_repository import IUserRepository
from core.domain.entities.user import UserEntity


class UserDomainService:
    """
    Servicio de dominio que encapsula reglas de negocio
    relacionadas con usuarios que requieren consultar otros objetos.
    """

    def __init__(self, user_repository: IUserRepository) -> None:
        # Inyección de dependencias: depende de la INTERFAZ, no de la implementación
        self._user_repo = user_repository

    def is_email_available(self, email: str) -> bool:
        """
        Regla de negocio: un email solo puede usarse por un usuario.
        Esta lógica necesita el repositorio, no puede vivir en la entidad.
        """
        return not self._user_repo.exists_by_email(email)

    def ensure_email_available(self, email: str) -> None:
        """
        Versión que lanza excepción si el email ya está registrado.
        Útil para que los casos de uso lo llamen directamente.
        """
        if not self.is_email_available(email):
            raise ValueError(f"El email '{email}' ya está registrado en el sistema.")
