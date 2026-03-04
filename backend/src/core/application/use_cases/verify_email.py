"""
use_cases/verify_email.py — Caso de uso: Verificar dirección de email.

Usa el sistema de tokens estándar de Django (PasswordResetTokenGenerator)
para validar que el link de verificación es genuino y no ha expirado.
"""

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str

from core.infrastructure.persistence.models import User as UserModel
from core.application.dto.auth_dto import VerifyEmailInputDTO


class VerifyEmailUseCase:
    """
    Verifica un link de confirmación de email.

    El link tiene la forma:
      /verify-email/?uid=<uid_b64>&token=<token>

    uid: pk del usuario codificado en base64url
    token: firmado con HMAC usando la contraseña actual del usuario
           → si el usuario cambia la contraseña, el token queda invalidado.
    """

    def execute(self, dto: VerifyEmailInputDTO) -> None:
        """
        Marca el email del usuario como verificado.

        Lanza ValueError si uid o token son inválidos / expirados.
        """
        try:
            uid = force_str(urlsafe_base64_decode(dto.uid))
            user = UserModel.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, UserModel.DoesNotExist) as exc:
            raise ValueError("Enlace de verificación inválido.") from exc

        if not default_token_generator.check_token(user, dto.token):
            raise ValueError("El enlace de verificación ha expirado o ya fue usado.")

        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])
