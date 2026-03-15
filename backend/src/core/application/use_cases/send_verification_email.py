"""
use_cases/send_verification_email.py — Enviar email de verificación al registrarse.

Puede llamarse también manualmente si el usuario solicita reenviar el email.
"""

from django.core import signing
from django.core.mail import send_mail
from django.conf import settings

from core.infrastructure.persistence.models import User as UserModel


class SendVerificationEmailUseCase:
    """
    Enviar email de activación de cuenta al usuario.

    El link incluye un token firmado con TimestampSigner (HMAC sobre SECRET_KEY).
    No depende de last_login ni del hash de contraseña, por lo que no se
    invalida al hacer login. Expira tras EMAIL_VERIFICATION_TIMEOUT segundos
    (por defecto 3 días).
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

        signer = signing.TimestampSigner()
        # El token codifica el pk del usuario firmado con HMAC
        token = signer.sign(str(user.pk))

        verify_url = (
            f"{settings.FRONTEND_URL}/auth/verify-email"
            f"?token={token}"
        )

        send_mail(
            subject="[CryptoWorld] Confirma tu dirección de email",
            message=(
                f"Hola {user.username},\n\n"
                f"Gracias por registrarte en CryptoWorld.\n\n"
                f"Confirma tu email haciendo clic en el siguiente enlace:\n{verify_url}\n\n"
                f"El enlace es válido durante 3 días.\n\n"
                f"El equipo de CryptoWorld"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
