"""
auth_dto.py — DTOs para operaciones de autenticación.

Los DTOs de entrada (Input) representan datos que llegan del cliente.
Los DTOs de salida (Output) representan datos que se devuelven al cliente.

NO contienen lógica de negocio. Solo estructura y tipos.
"""

from dataclasses import dataclass
from typing import Optional


# ── Entrada ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RegisterUserInputDTO:
    """
    Datos necesarios para registrar un nuevo usuario.
    Viene del cuerpo de la petición HTTP POST /api/auth/register.
    """
    email: str
    username: str
    password: str


@dataclass(frozen=True)
class LoginInputDTO:
    """
    Credenciales para autenticar un usuario existente.
    Viene del cuerpo de la petición HTTP POST /api/auth/login.
    """
    email: str
    password: str


@dataclass(frozen=True)
class LogoutInputDTO:
    """Token de refresco a añadir a la blacklist en el logout."""
    refresh_token: str


@dataclass(frozen=True)
class VerifyEmailInputDTO:
    """Token firmado generado por Django para verificación de email."""
    uid: str          # user id codificado en base64
    token: str        # token generado por default_token_generator


@dataclass(frozen=True)
class PasswordResetRequestDTO:
    """Email del usuario que solicita recuperar su contraseña."""
    email: str


@dataclass(frozen=True)
class PasswordResetConfirmDTO:
    """Datos para confirmar el restablecimiento de contraseña."""
    uid: str
    token: str
    new_password: str


@dataclass(frozen=True)
class ChangePasswordDTO:
    """Datos para cambiar contraseña estando autenticado."""
    user_id: int
    current_password: str
    new_password: str


@dataclass(frozen=True)
class Enable2FADTO:
    """Código TOTP para confirmar que el usuario tiene configurada la app."""
    user_id: int
    totp_code: str


@dataclass(frozen=True)
class Disable2FADTO:
    """Código TOTP requerido para desactivar 2FA."""
    user_id: int
    totp_code: str


@dataclass(frozen=True)
class Verify2FALoginDTO:
    """Token temporal de pre-autenticación + código TOTP."""
    pre_auth_token: str
    totp_code: str


# ── Salida ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AuthTokenOutputDTO:
    """
    Par de tokens JWT devueltos tras autenticación exitosa.
    access_token: corta duración (60 min), para peticiones API.
    refresh_token: larga duración (7 días), para renovar el access.
    """
    access_token: str
    refresh_token: str
    user_id: int
    username: str
    email: str


@dataclass(frozen=True)
class UserOutputDTO:
    """Representación pública de un usuario (sin contraseña)."""
    id: int
    email: str
    username: str
    is_active: bool
    is_email_verified: bool = False
    is_2fa_enabled: bool = False


@dataclass(frozen=True)
class Setup2FAOutputDTO:
    """
    Devuelto al iniciar el setup de 2FA.
    El cliente muestra el QR al usuario para que lo escanee con su app.
    """
    totp_secret: str        # Secreto base32 (también para entrada manual)
    qr_code_uri: str        # otpauth:// URI para generar el QR code
    qr_code_base64: str     # imagen PNG del QR en base64 (data:image/png;base64,…)


@dataclass(frozen=True)
class PreAuthTokenOutputDTO:
    """
    Token temporal emitido cuando el login requiere 2FA.
    El cliente debe hacer POST /api/auth/2fa/login/ con este token + TOTP.
    """
    requires_2fa: bool
    pre_auth_token: str
