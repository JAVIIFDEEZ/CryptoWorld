"""
use_cases/change_email.py — Cambio seguro de dirección de email.

El email es la identidad de login y debe estar verificado, así que nunca
se cambia directamente. Flujo en dos pasos:

  1. RequestEmailChangeUseCase: valida contraseña y disponibilidad,
     guarda la nueva dirección en pending_email y dispara el envío de
     un enlace de confirmación AL NUEVO correo.
  2. ConfirmEmailChangeUseCase: al abrir el enlace, valida el token
     firmado y solo entonces sustituye email por pending_email.

Así un error tipográfico no deja al usuario sin cuenta (conserva el email
antiguo hasta confirmar) y nadie puede redirigir la cuenta a un correo
que no controla.
"""

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string

from core.application.services.sessions import revoke_all_sessions
from core.infrastructure.persistence.models import User as UserModel

# Sal específica: un token de verificación normal no sirve para cambiar email
EMAIL_CHANGE_SALT = "core.email-change"
# Validez del enlace: 1 día (acción sensible, ventana corta)
EMAIL_CHANGE_MAX_AGE = 60 * 60 * 24


class RequestEmailChangeUseCase:
    """Paso 1: registrar la petición y avisar al nuevo correo."""

    def execute(self, user_id: int, new_email: str, password: str) -> None:
        """
        Lanza ValueError si la contraseña es incorrecta, el email no cambia
        o ya pertenece a otra cuenta.
        """
        try:
            user = UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist as exc:
            raise ValueError("Usuario no encontrado.") from exc

        # Acción sensible: exigir la contraseña evita que una sesión
        # secuestrada redirija la cuenta a otro correo.
        if not user.check_password(password):
            raise ValueError("Contraseña incorrecta.")

        normalized = new_email.strip().lower()
        if normalized == user.email.lower():
            raise ValueError("La nueva dirección es la misma que la actual.")

        if UserModel.objects.filter(email__iexact=normalized).exclude(pk=user.pk).exists():
            raise ValueError("Esa dirección de email ya está en uso.")

        user.pending_email = normalized
        user.save(update_fields=["pending_email"])

    @staticmethod
    def send_confirmation_email(user_id: int) -> None:
        """
        Enviar el enlace de confirmación a pending_email.
        Separado de execute() para poder despacharse como task Celery.
        """
        try:
            user = UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist as exc:
            raise ValueError("Usuario no encontrado.") from exc

        if not user.pending_email:
            return  # Nada pendiente (p. ej. ya confirmado)

        token = signing.dumps(
            {"user_id": user.pk, "new_email": user.pending_email},
            salt=EMAIL_CHANGE_SALT,
        )
        confirm_url = f"{settings.FRONTEND_URL}/auth/confirm-email-change?token={token}"

        context = {
            "username": user.username,
            "new_email": user.pending_email,
            "confirm_url": confirm_url,
        }
        html_body = render_to_string("email/email_change.html", context)
        text_body = (
            f"Hola {user.username},\n\n"
            f"Has solicitado cambiar el email de tu cuenta CryptoWorld a esta dirección.\n\n"
            f"Confirma el cambio haciendo clic en el siguiente enlace:\n{confirm_url}\n\n"
            f"El enlace es válido durante 24 horas. Si no lo solicitaste tú, "
            f"ignora este mensaje: tu email actual seguirá activo.\n\n"
            f"El equipo de CryptoWorld"
        )

        msg = EmailMultiAlternatives(
            subject="[CryptoWorld] Confirma tu nueva dirección de email",
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.pending_email],
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send(fail_silently=False)


class ConfirmEmailChangeUseCase:
    """Paso 2: validar el token y aplicar el cambio."""

    def execute(self, token: str) -> UserModel:
        """
        Sustituye el email por el pendiente.

        El email es el identificador de login, así que cambiarlo equivale
        a cambiar la credencial: se revocan todas las sesiones abiertas y
        el usuario vuelve a autenticarse con su nueva dirección.

        Returns:
            El usuario con el email ya actualizado.

        Raises:
            ValueError: si el token es inválido/expirado, no coincide con
                la petición pendiente o la dirección se ocupó entre tanto.
        """
        try:
            payload = signing.loads(
                token, salt=EMAIL_CHANGE_SALT, max_age=EMAIL_CHANGE_MAX_AGE
            )
        except signing.SignatureExpired:
            raise ValueError("El enlace ha expirado (válido 24 horas). Solicita el cambio de nuevo.")
        except signing.BadSignature:
            raise ValueError("Enlace de confirmación inválido.")

        try:
            user = UserModel.objects.get(pk=payload.get("user_id"))
        except UserModel.DoesNotExist:
            raise ValueError("Enlace de confirmación inválido.")

        new_email = payload.get("new_email", "")
        if not user.pending_email or user.pending_email != new_email:
            raise ValueError(
                "Este enlace ya no es válido (no coincide con ninguna petición pendiente)."
            )

        # La dirección pudo ocuparse entre la petición y la confirmación
        if UserModel.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
            user.pending_email = None
            user.save(update_fields=["pending_email"])
            raise ValueError("Esa dirección de email ya está en uso.")

        with transaction.atomic():
            user.email = new_email
            user.pending_email = None
            # El usuario acaba de demostrar control sobre la nueva dirección
            user.is_email_verified = True
            user.save(update_fields=["email", "pending_email", "is_email_verified"])
            revoke_all_sessions(user)

        return user
