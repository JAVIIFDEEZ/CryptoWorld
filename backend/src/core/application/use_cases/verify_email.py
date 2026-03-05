"""
use_cases/verify_email.py — Caso de uso: Verificar dirección de email.

Usa el sistema de tokens estándar de Django (PasswordResetTokenGenerator)
para validar que el link de verificación es genuino y no ha expirado.
"""

from django.core import signing

from core.infrastructure.persistence.models import User as UserModel
from core.application.dto.auth_dto import VerifyEmailInputDTO

# Tiempo de validez del token: 3 días en segundos
VERIFICATION_MAX_AGE = 60 * 60 * 24 * 3


class VerifyEmailUseCase:
    """
    Verifica un link de confirmación de email.

    El link tiene la forma:
      /verify-email/?token=<token_firmado>

    El token es un TimestampSigner que codifica el pk del usuario.
    No se invalida al hacer login ni al cambiar la contraseña.
    Expira a los 3 días (VERIFICATION_MAX_AGE).
    """

    def execute(self, dto: VerifyEmailInputDTO) -> None:
        """
        Marca el email del usuario como verificado.

        Lanza ValueError si el token es inválido o ha expirado.
        """
        signer = signing.TimestampSigner()
        try:
            user_pk = signer.unsign(dto.token, max_age=VERIFICATION_MAX_AGE)
        except signing.SignatureExpired:
            raise ValueError("El enlace de verificación ha expirado (válido 3 días).")
        except signing.BadSignature:
            raise ValueError("Enlace de verificación inválido.")

        try:
            user = UserModel.objects.get(pk=user_pk)
        except UserModel.DoesNotExist:
            raise ValueError("Enlace de verificación inválido.")

        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
