"""
use_cases/request_password_reset.py — Caso de uso: Solicitar recuperación de contraseña.

Genera un link seguro (uid + token) y lo envía por email.
Usa el generador de tokens estándar de Django para máxima seguridad.
"""

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings

from core.infrastructure.persistence.models import User as UserModel
from core.application.dto.auth_dto import PasswordResetRequestDTO


class RequestPasswordResetUseCase:
    """
    Envía un email con el link para restablecer contraseña.

    Por seguridad NO se indica si el email existe o no (evita enumeración).
    Si el email no existe, simplemente no se envía nada.
    """

    def execute(self, dto: PasswordResetRequestDTO) -> None:
        """Enviar email de recuperación si el usuario existe."""
        try:
            user = UserModel.objects.get(email=dto.email, is_active=True)
        except UserModel.DoesNotExist:
            # Silencioso: no revelar si el email existe
            return

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        reset_url = (
            f"{settings.FRONTEND_URL}/auth/password-reset/confirm/"
            f"?uid={uid}&token={token}"
        )

        send_mail(
            subject="[CryptoWorld] Restablece tu contraseña",
            message=(
                f"Hola {user.username},\n\n"
                f"Hemos recibido una solicitud para restablecer la contraseña de tu cuenta.\n\n"
                f"Usa el siguiente enlace (válido 24 horas):\n{reset_url}\n\n"
                f"Si no solicitaste esto, ignora este mensaje.\n\n"
                f"El equipo de CryptoWorld"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
