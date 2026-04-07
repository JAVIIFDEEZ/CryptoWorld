"""
admin_update_user.py — Caso de uso: Actualizar usuario (admin).
"""

from core.domain.repositories.user_repository import IUserRepository
from core.application.dto.admin_dto import AdminUpdateUserInputDTO, AdminUserOutputDTO


class AdminUpdateUserUseCase:
    """Caso de uso: editar un usuario desde el panel de admin."""

    def __init__(self, user_repository: IUserRepository) -> None:
        self._user_repo = user_repository

    def execute(self, input_dto: AdminUpdateUserInputDTO) -> AdminUserOutputDTO:
        user = self._user_repo.get_by_id(input_dto.user_id)
        if user is None:
            raise ValueError("Usuario no encontrado.")

        if input_dto.is_active is not None:
            user.is_active = input_dto.is_active

        if input_dto.role is not None:
            if input_dto.role not in ("user", "admin"):
                raise ValueError(f"Rol inválido: '{input_dto.role}'.")
            user.role = input_dto.role
            if input_dto.role == "admin":
                user.is_staff = True

        if input_dto.is_email_verified is not None:
            user.is_email_verified = input_dto.is_email_verified

        saved = self._user_repo.save(user)

        # Sync is_email_verified through the dedicated ORM method
        if input_dto.is_email_verified is True:
            self._user_repo.set_email_verified(saved.id)

        return AdminUserOutputDTO(
            id=saved.id,
            email=saved.email,
            username=saved.username,
            is_active=saved.is_active,
            is_staff=saved.is_staff,
            role=saved.role,
            is_email_verified=saved.is_email_verified,
            is_2fa_enabled=saved.is_2fa_enabled,
            date_joined=saved.date_joined.isoformat() if hasattr(saved.date_joined, 'isoformat') else str(saved.date_joined),
        )
