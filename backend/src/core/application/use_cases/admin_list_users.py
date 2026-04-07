"""
admin_list_users.py — Caso de uso: Listar todos los usuarios (admin).
"""

from typing import List
from core.domain.repositories.user_repository import IUserRepository
from core.application.dto.admin_dto import AdminUserOutputDTO


class AdminListUsersUseCase:
    """Caso de uso: listar todos los usuarios del sistema."""

    def __init__(self, user_repository: IUserRepository) -> None:
        self._user_repo = user_repository

    def execute(self) -> List[AdminUserOutputDTO]:
        users = self._user_repo.get_all()
        return [
            AdminUserOutputDTO(
                id=u.id,
                email=u.email,
                username=u.username,
                is_active=u.is_active,
                is_staff=u.is_staff,
                role=u.role,
                is_email_verified=u.is_email_verified,
                is_2fa_enabled=u.is_2fa_enabled,
                date_joined=u.date_joined.isoformat() if hasattr(u.date_joined, 'isoformat') else str(u.date_joined),
            )
            for u in users
        ]
