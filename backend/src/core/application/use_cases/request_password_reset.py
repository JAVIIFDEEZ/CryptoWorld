"""
use_cases/request_password_reset.py — Caso de uso: Solicitar recuperación de contraseña.

Genera un link seguro (uid + token) y lo envía por email.
Usa el generador de tokens estándar de Django para máxima seguridad.
"""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from core.application.dto.auth_dto import PasswordResetRequestDTO
from core.infrastructure.persistence.models import User as UserModel

logger = logging.getLogger(__name__)


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
            logger.debug("[password-reset] Email no encontrado o inactivo: %s", dto.email)
            return

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        reset_url = (
            f"{settings.FRONTEND_URL}/auth/password-reset/confirm/"
            f"?uid={uid}&token={token}"
        )

        context = {"username": user.username, "reset_url": reset_url}

        html_body = render_to_string("email/password_reset.html", context)
        text_body = (
            f"Hola {user.username},\n\n"
            f"Hemos recibido una solicitud para restablecer la contraseña de tu cuenta.\n\n"
            f"Usa el siguiente enlace (válido 24 horas):\n{reset_url}\n\n"
            f"Si no solicitaste esto, ignora este mensaje.\n\n"
            f"El equipo de CryptoWorld"
        )

        msg = EmailMultiAlternatives(
            subject="[CryptoWorld] Restablece tu contraseña",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)

        # En desarrollo el email se imprime en los logs Docker (console backend)
        logger.info(
            "\n[DEV] PasswordReset para %s\n  Link: %s\n",
            user.email,
            reset_url,
        )
