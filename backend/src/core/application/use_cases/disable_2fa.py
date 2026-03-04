"""
use_cases/disable_2fa.py — Caso de uso: Desactivar 2FA.

Requiere un código TOTP válido para evitar que alguien con
acceso temporal a la sesión pueda desactivar la protección.
"""

import pyotp

from core.infrastructure.persistence.models import User as UserModel
from core.application.dto.auth_dto import Disable2FADTO


class Disable2FAUseCase:
    """
    Desactiva 2FA para un usuario autenticado.

    Para mayor seguridad, se exige un código TOTP actual
    antes de desactivarlo, evitando ataques de sesión secuestrada.
    """

    def execute(self, dto: Disable2FADTO) -> None:
        """
        Desactiva 2FA si el código TOTP es válido.

        Lanza ValueError si el código es incorrecto o 2FA no estaba activo.
        """
        try:
            user = UserModel.objects.get(pk=dto.user_id)
        except UserModel.DoesNotExist as exc:
            raise ValueError("Usuario no encontrado.") from exc

        if not user.is_2fa_enabled:
            raise ValueError("2FA no está activado en esta cuenta.")

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(dto.totp_code, valid_window=1):
            raise ValueError("Código TOTP incorrecto.")

        user.is_2fa_enabled = False
        user.totp_secret = None
        user.save(update_fields=["is_2fa_enabled", "totp_secret"])
