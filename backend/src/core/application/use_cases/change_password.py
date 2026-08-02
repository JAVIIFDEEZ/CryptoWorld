"""
use_cases/change_password.py — Caso de uso: Cambiar contraseña (autenticado).

El usuario debe proporcionar su contraseña actual como verificación adicional.
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from core.application.dto.auth_dto import ChangePasswordDTO
from core.application.services.sessions import issue_session, revoke_all_sessions
from core.infrastructure.persistence.models import User as UserModel


class ChangePasswordUseCase:
    """
    Cambiar contraseña de un usuario autenticado.

    Requiere la contraseña actual para prevenir ataques de sesión robada,
    y revoca todas las sesiones abiertas: cambiar la contraseña es la
    respuesta natural ante una sospecha de compromiso, así que tiene que
    expulsar de verdad a quien estuviera dentro.

    Devuelve un par de tokens nuevo para que el dispositivo que hace el
    cambio no se auto-desconecte.
    """

    def execute(self, dto: ChangePasswordDTO) -> dict:
        """
        Verifica contraseña actual y aplica la nueva.

        Returns:
            dict con `access_token` y `refresh_token` recién emitidos.

        Raises:
            ValueError: si la contraseña actual es incorrecta, si la nueva
                no supera los validadores de Django o si coincide con la
                anterior.
        """
        try:
            user = UserModel.objects.get(pk=dto.user_id)
        except UserModel.DoesNotExist as exc:
            raise ValueError("Usuario no encontrado.") from exc

        if not user.check_password(dto.current_password):
            raise ValueError("La contraseña actual es incorrecta.")

        if dto.current_password == dto.new_password:
            raise ValueError("La nueva contraseña debe ser distinta de la actual.")

        try:
            validate_password(dto.new_password, user)
        except ValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc

        with transaction.atomic():
            user.set_password(dto.new_password)
            user.save(update_fields=["password"])
            revoke_all_sessions(user)

        return issue_session(user)
