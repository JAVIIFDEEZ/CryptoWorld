"""
register_user.py — Caso de uso: Registrar nuevo usuario.

Orquesta toda la lógica necesaria para registrar un usuario:
1. Validar que el email no esté en uso (servicio de dominio)
2. Crear la entidad de usuario (dominio)
3. Persistir usando el repositorio (infraestructura, inyectada)
4. Devolver DTO de salida (sin exponer entidades internas)

Este caso de uso NO sabe que existe Django, PostgreSQL ni HTTP.
Solo trabaja con las abstracciones del dominio.
"""

from core.domain.entities.user import UserEntity
from core.domain.repositories.user_repository import IUserRepository
from core.domain.services.user_domain_service import UserDomainService
from core.application.dto.auth_dto import RegisterUserInputDTO, UserOutputDTO


class RegisterUserUseCase:
    """
    Caso de uso: registro de usuario.

    Recibe el repositorio y el servicio de dominio por inyección
    de dependencias. En producción se pasan las implementaciones
    concretas (Django ORM); en tests se pasan mocks/stubs.
    """

    def __init__(
        self,
        user_repository: IUserRepository,
        user_domain_service: UserDomainService,
    ) -> None:
        self._user_repo = user_repository
        self._user_domain_service = user_domain_service

    def execute(self, input_dto: RegisterUserInputDTO) -> UserOutputDTO:
        """
        Ejecutar el caso de uso de registro.

        Args:
            input_dto: datos validados del cliente.

        Returns:
            UserOutputDTO con los datos públicos del usuario creado.

        Raises:
            ValueError: si el email ya existe o los datos son inválidos.
        """
        # Paso 1: Regla de dominio — email único
        self._user_domain_service.ensure_email_available(input_dto.email)

        # Paso 2: Crear entidad de dominio (las validaciones son internas a la entidad)
        user_entity = UserEntity(
            email=input_dto.email,
            username=input_dto.username,
        )

        # Paso 3: Persistir a través del contrato del repositorio
        # La implementación concreta se decide fuera de este caso de uso (DIP)
        saved_user = self._user_repo.save(user_entity)
        # Nota: el hash de la contraseña lo gestiona la infraestructura (modelo Django)

        # Paso 4: Construir y devolver DTO de salida (nunca la entidad directamente)
        return UserOutputDTO(
            id=saved_user.id,
            email=saved_user.email,
            username=saved_user.username,
            is_active=saved_user.is_active,
        )
