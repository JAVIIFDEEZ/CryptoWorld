"""
use_cases/logout.py — Caso de uso: Cerrar sesión.

Añade el refresh_token a la blacklist de SimpleJWT.
Tras esto, ese token ya no puede usarse para obtener nuevos access tokens.
"""

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from core.application.dto.auth_dto import LogoutInputDTO


class LogoutUseCase:
    """
    Invalidar el refresh_token del usuario cerrando su sesión activa.

    SimpleJWT permite blacklistear tokens cuando
    rest_framework_simplejwt.token_blacklist está en INSTALLED_APPS.
    """

    def execute(self, dto: LogoutInputDTO) -> None:
        """
        Añade el refresh_token a la blacklist.

        Lanza ValueError si el token ya es inválido o está en la blacklist.
        """
        try:
            token = RefreshToken(dto.refresh_token)
            token.blacklist()
        except TokenError as exc:
            raise ValueError(f"Token de refresco inválido: {exc}") from exc
