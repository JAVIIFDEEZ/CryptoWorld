"""
use_cases/setup_2fa.py — Caso de uso: Iniciar configuración de 2FA (TOTP).

Genera un secreto TOTP y devuelve la URI otpauth:// y el QR en base64.
El 2FA NO queda activado hasta que el usuario confirme el primer código
(ver enable_2fa.py). Esto garantiza que la app está configurada correctamente.
"""

import base64
import io

import pyotp
import qrcode

from core.infrastructure.persistence.models import User as UserModel
from core.application.dto.auth_dto import Setup2FAOutputDTO


class Setup2FAUseCase:
    """
    Primer paso del setup de 2FA.

    Genera un secreto TOTP aleatorio, lo guarda en el usuario
    (aún con is_2fa_enabled=False), y devuelve el QR para escanear.
    """

    def execute(self, user_id: int) -> Setup2FAOutputDTO:
        """
        Genera secreto TOTP y QR para el usuario.

        Lanza ValueError si el usuario no existe o ya tiene 2FA activado.
        """
        try:
            user = UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist as exc:
            raise ValueError("Usuario no encontrado.") from exc

        if user.is_2fa_enabled:
            raise ValueError(
                "2FA ya está activado. Desactívalo primero para reconfigurarlo."
            )

        # Generar secreto base32 (compatible con Google Authenticator, Authy, etc.)
        secret = pyotp.random_base32()

        # Guardar el secreto (2FA aún NO activado)
        user.totp_secret = secret
        user.save(update_fields=["totp_secret"])

        # Construir la URI otpauth:// estándar
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(
            name=user.email,
            issuer_name="CryptoWorld",
        )

        # Generar imagen QR en base64 para devolver al frontend
        qr_image = qrcode.make(uri)
        buffer = io.BytesIO()
        qr_image.save(buffer, format="PNG")
        qr_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        return Setup2FAOutputDTO(
            totp_secret=secret,
            qr_code_uri=uri,
            qr_code_base64=f"data:image/png;base64,{qr_b64}",
        )
