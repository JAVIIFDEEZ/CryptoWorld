"""
use_cases/send_verification_email.py — Enviar email de verificación al registrarse.

Puede llamarse también manualmente si el usuario solicita reenviar el email.
"""

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings

from core.infrastructure.persistence.models import User as UserModel


class SendVerificationEmailUseCase:
    """
    Enviar email de activación de cuenta al usuario.

    El link incluye uid (user pk en base64) + token firmado con HMAC.
    El token queda invalidado cuando el usuario verifica su email
    (porque Django usa datos del usuario en la firma).
    """

    def execute(self, user_id: int) -> None:
        """
        Enviar email de verificación al usuario indicado.

        Lanza ValueError si el usuario no existe.
        """
        try:
            user = UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist as exc:
            raise ValueError("Usuario no encontrado.") from exc

        if user.is_email_verified:
            return  # Ya verificado, no reenviar

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        verify_url = (
            f"{settings.FRONTEND_URL}/auth/verify-email/"
            f"?uid={uid}&token={token}"
        )

        send_mail(
            subject="[CryptoWorld] Confirma tu dirección de email",
            message=(
                f"Hola {user.username},\n\n"
                f"Gracias por registrarte en CryptoWorld.\n\n"
                f"Confirma tu email haciendo clic en el siguiente enlace:\n{verify_url}\n\n"
                f"El enlace es válido durante 24 horas.\n\n"
                f"El equipo de CryptoWorld"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
