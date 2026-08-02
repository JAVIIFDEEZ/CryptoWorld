"""
use_cases/confirm_password_reset.py — Caso de uso: Confirmar nueva contraseña.

Valida el token del link de recuperación y aplica la nueva contraseña.
"""

from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode

from core.application.dto.auth_dto import PasswordResetConfirmDTO
from core.application.services.sessions import revoke_all_sessions
from core.infrastructure.persistence.models import User as UserModel


class ConfirmPasswordResetUseCase:
    """
    Aplica la nueva contraseña si el token del link es válido.

    El token se invalida automáticamente tras el uso porque Django
    incluye el hash de la contraseña actual en la firma del token.

    Al completarse se revocan todas las sesiones: quien recupera la
    contraseña normalmente lo hace porque perdió el control de la cuenta,
    y las sesiones del atacante deben caer con el cambio.
    """

    def execute(self, dto: PasswordResetConfirmDTO) -> UserModel:
        """
        Restablece la contraseña del usuario.

        Returns:
            El usuario afectado (para poder auditarlo en la capa de interfaces).

        Raises:
            ValueError: si uid/token son inválidos o la contraseña es débil.
        """
        try:
            uid = force_str(urlsafe_base64_decode(dto.uid))
            user = UserModel.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, UserModel.DoesNotExist) as exc:
            raise ValueError("Enlace de recuperación inválido.") from exc

        if not default_token_generator.check_token(user, dto.token):
            raise ValueError("El enlace ha expirado o ya fue usado.")

        # Validar la nueva contraseña con los validadores de Django
        try:
            validate_password(dto.new_password, user)
        except ValidationError as exc:
            raise ValueError(" ".join(exc.messages)) from exc

        with transaction.atomic():
            user.set_password(dto.new_password)
            user.save(update_fields=["password"])
            revoke_all_sessions(user)

        return user
