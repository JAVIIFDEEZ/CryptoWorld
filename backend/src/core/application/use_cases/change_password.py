"""
use_cases/change_password.py — Caso de uso: Cambiar contraseña (autenticado).

El usuario debe proporcionar su contraseña actual como verificación adicional.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


from core.infrastructure.persistence.models import User as UserModel
from core.application.dto.auth_dto import ChangePasswordDTO


class ChangePasswordUseCase:
    """
    Cambiar contraseña de un usuario autenticado.

    Requiere la contraseña actual para prevenir ataques de sesión robada.
    """

    def execute(self, dto: ChangePasswordDTO) -> None:
        """
        Verifica contraseña actual y aplica la nueva.

        Lanza ValueError si la contraseña actual es incorrecta
        o si la nueva no supera los validadores de Django.
        """
        try:
            user = UserModel.objects.get(pk=dto.user_id)
        except UserModel.DoesNotExist as exc:
            raise ValueError("Usuario no encontrado.") from exc

        if not user.check_password(dto.current_password):
            raise ValueError("La contraseña actual es incorrecta.")

        try:
            validate_password(dto.new_password, user)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

        user.set_password(dto.new_password)
        user.save(update_fields=["password"])
