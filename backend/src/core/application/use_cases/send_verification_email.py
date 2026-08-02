"""
use_cases/send_verification_email.py — Enviar email de verificación al registrarse.

Puede llamarse también manualmente si el usuario solicita reenviar el email.
"""

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from core.application.use_cases.verify_email import EMAIL_VERIFICATION_SALT
from core.infrastructure.persistence.models import User as UserModel


class SendVerificationEmailUseCase:
    """
    Enviar email de activación de cuenta al usuario.

    El link incluye un token firmado con TimestampSigner (HMAC sobre SECRET_KEY).
    No depende de last_login ni del hash de contraseña, por lo que no se
    invalida al hacer login. Expira tras EMAIL_VERIFICATION_TIMEOUT segundos
    (por defecto 3 días).

    Envía tanto versión texto plano como HTML (email responsive oscuro).
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

        # Sal específica del propósito: el token de verificación no debe
        # ser reutilizable en ningún otro flujo firmado del proyecto.
        signer = signing.TimestampSigner(salt=EMAIL_VERIFICATION_SALT)
        # El token codifica el pk del usuario firmado con HMAC
        token = signer.sign(str(user.pk))

        verify_url = (
            f"{settings.FRONTEND_URL}/auth/verify-email"
            f"?token={token}"
        )

        context = {"username": user.username, "verify_url": verify_url}

        html_body = render_to_string("email/verification.html", context)
        text_body = (
            f"Hola {user.username},\n\n"
            f"Gracias por registrarte en CryptoWorld.\n\n"
            f"Confirma tu email haciendo clic en el siguiente enlace:\n{verify_url}\n\n"
            f"El enlace es válido durante 3 días.\n\n"
            f"El equipo de CryptoWorld"
        )

        msg = EmailMultiAlternatives(
            subject="[CryptoWorld] Confirma tu dirección de email",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)

