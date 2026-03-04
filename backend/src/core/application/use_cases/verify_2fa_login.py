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

import pyotp
from datetime import timedelta

from rest_framework_simplejwt.tokens import RefreshToken, Token
from rest_framework_simplejwt.exceptions import TokenError

from core.infrastructure.persistence.models import User as UserModel
from core.application.dto.auth_dto import Verify2FALoginDTO, AuthTokenOutputDTO


class PreAuthToken(Token):
    """
    Token JWT de corta duración emitido cuando el login requiere 2FA.

    Es un token especial con type='pre_2fa' que solo sirve para
    completar el segundo factor. No puede usarse como access token.
    """
    token_type = "pre_2fa"
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

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(dto.totp_code, valid_window=1):
            raise ValueError("Código TOTP incorrecto.")

        # Emitir tokens JWT completos
        refresh = RefreshToken.for_user(user)

        return AuthTokenOutputDTO(
            access_token=str(refresh.access_token),
            refresh_token=str(refresh),
            user_id=user.pk,
            email=user.email,
            username=user.username,
        )
