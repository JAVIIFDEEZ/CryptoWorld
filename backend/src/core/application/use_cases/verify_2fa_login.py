"""
use_cases/verify_2fa_login.py — Caso de uso: Segunda fase del login con 2FA.

El flujo completo es:
  1. POST /api/auth/login/ → credenciales válidas + 2FA activo
     → devuelve PreAuthToken (JWT especial, 5 min de validez)
  2. POST /api/auth/2fa/login/ → pre_auth_token + código TOTP
     → valida el token temporal, valida el TOTP
     → devuelve los tokens JWT completos (access + refresh)

Este use case gestiona el paso 2.
"""

from datetime import timedelta

import pyotp
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import Token

from core.application.dto.auth_dto import AuthTokenOutputDTO, Verify2FALoginDTO
from core.application.services.sessions import build_refresh_token
from core.infrastructure.persistence.models import User as UserModel


class PreAuthToken(Token):
    """
    Token JWT de corta duración emitido cuando el login requiere 2FA.

    Es un token especial con type='pre_2fa' que solo sirve para
    completar el segundo factor. No puede usarse como access token.
    """
    # No es una credencial: es el discriminante de tipo del JWT que
    # SimpleJWT verifica para que un access token no sirva como
    # pre-autenticacion.
    token_type = "pre_2fa"  # noqa: S105
    lifetime = timedelta(minutes=5)


class Verify2FALoginUseCase:
    """
    Validar el código TOTP y emitir tokens JWT completos.

    Requiere un PreAuthToken válido (emitido en el paso 1 del login)
    más el código TOTP correcto del usuario.
    """

    def execute(self, dto: Verify2FALoginDTO) -> AuthTokenOutputDTO:
        """
        Verifica el token temporal y el código TOTP.

        Lanza ValueError si:
        - El pre_auth_token es inválido o ha expirado
        - El tipo de token no es 'pre_2fa'
        - El código TOTP es incorrecto
        """
        try:
            token = PreAuthToken(dto.pre_auth_token)
        except TokenError as exc:
            raise ValueError("Token de pre-autenticación inválido o expirado.") from exc

        user_id = token.get("user_id")
        if not user_id:
            raise ValueError("Token de pre-autenticación malformado.")

        try:
            user = UserModel.objects.get(pk=user_id, is_active=True)
        except UserModel.DoesNotExist as exc:
            raise ValueError("Usuario no encontrado o inactivo.") from exc

        if not user.is_2fa_enabled or not user.totp_secret:
            raise ValueError("2FA no está habilitado para este usuario.")

        # Segundo factor: código TOTP o código de recuperación de un solo uso
        if dto.totp_code:
            totp = pyotp.TOTP(user.totp_secret)
            if not totp.verify(dto.totp_code, valid_window=1):
                raise ValueError("Código TOTP incorrecto.")
        elif dto.recovery_code:
            from core.application.use_cases.recovery_codes import consume_recovery_code

            if not consume_recovery_code(user, dto.recovery_code):
                raise ValueError("Código de recuperación inválido o ya utilizado.")
        else:
            raise ValueError("Debes proporcionar un código TOTP o de recuperación.")

        # Emitir tokens JWT completos con el claim de revocación.
        refresh = build_refresh_token(user)

        return AuthTokenOutputDTO(
            access_token=str(refresh.access_token),
            refresh_token=str(refresh),
            user_id=user.pk,
            email=user.email,
            username=user.username,
            is_admin=user.is_staff or user.is_superuser,
        )
