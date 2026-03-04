"""
use_cases/enable_2fa.py — Caso de uso: Activar 2FA tras verificar el primer código.

El usuario escanea el QR en su app y envía el primer código TOTP.
Si el código es correcto, is_2fa_enabled pasa a True.
"""

import pyotp

from core.infrastructure.persistence.models import User as UserModel
from core.application.dto.auth_dto import Enable2FADTO


class Enable2FAUseCase:
    """
    Segundo paso del setup de 2FA: confirmación.

    Valida que el código TOTP coincide con el secreto guardado
    y, si es correcto, activa el 2FA para el usuario.
    """

    def execute(self, dto: Enable2FADTO) -> None:
        """
        Activa 2FA si el código TOTP es válido.

        Lanza ValueError si:
        - El usuario no existe
        - No hay secreto TOTP guardado (setup no iniciado)
        - El código TOTP es incorrecto
        """
        try:
            user = UserModel.objects.get(pk=dto.user_id)
        except UserModel.DoesNotExist as exc:
            raise ValueError("Usuario no encontrado.") from exc

        if not user.totp_secret:
            raise ValueError(
                "Debes iniciar el setup de 2FA antes de activarlo."
            )

        if user.is_2fa_enabled:
            raise ValueError("2FA ya está activado.")

        totp = pyotp.TOTP(user.totp_secret)
        # valid_window=1 permite un margen de ±30 segundos
        if not totp.verify(dto.totp_code, valid_window=1):
            raise ValueError("Código TOTP incorrecto.")

        user.is_2fa_enabled = True
        user.save(update_fields=["is_2fa_enabled"])
