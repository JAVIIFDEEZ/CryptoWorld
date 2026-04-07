"""
admin_delete_user.py — Caso de uso: Eliminar usuario (admin).
"""

from core.domain.repositories.user_repository import IUserRepository


class AdminDeleteUserUseCase:
    """Caso de uso: eliminar un usuario del sistema desde el panel de admin."""

    def __init__(self, user_repository: IUserRepository) -> None:
        self._user_repo = user_repository

    def execute(self, user_id: int, admin_user_id: int) -> None:
        """
        Elimina un usuario. El admin no puede eliminarse a sí mismo.

        Raises:
            ValueError: si el usuario no existe o intenta eliminarse a sí mismo.
        """
        if user_id == admin_user_id:
            raise ValueError("No puedes eliminar tu propia cuenta de admin.")

        user = self._user_repo.get_by_id(user_id)
        if user is None:
            raise ValueError("Usuario no encontrado.")

        self._user_repo.delete(user_id)
