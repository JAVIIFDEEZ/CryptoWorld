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
