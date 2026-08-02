"""
interfaces/api/authentication.py — Autenticación JWT con corte por epoch.

`JWTAuthentication` de SimpleJWT valida firma y caducidad, pero no puede
saber que las credenciales del usuario cambiaron después de emitir el
token: un access token robado sigue funcionando hasta agotar su vida
útil aunque la víctima ya haya cambiado la contraseña.

Esta subclase añade esa comprobación: si el token se emitió (`iat`) antes
de `user.credentials_changed_at`, se rechaza. Es la mitad que le faltaba
a la blacklist de refresh tokens para que la revocación sea completa.
"""

from datetime import datetime, timezone as dt_timezone

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


class CredentialEpochJWTAuthentication(JWTAuthentication):
    """JWT que además respeta la marca de revocación global del usuario."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        changed_at = getattr(user, "credentials_changed_at", None)
        if changed_at is None:
            return user

        issued_at_raw = validated_token.get("iat")
        if issued_at_raw is None:
            # Un token sin `iat` no se puede fechar; con una revocación
            # vigente sobre la cuenta, la única respuesta segura es
            # rechazarlo.
            raise AuthenticationFailed(
                "La sesión ya no es válida. Vuelve a iniciar sesión.",
                code="session_revoked",
            )

        issued_at = datetime.fromtimestamp(int(issued_at_raw), tz=dt_timezone.utc)
        if issued_at < changed_at.replace(microsecond=0):
            # Se compara contra el segundo exacto porque `iat` tiene
            # resolución de segundo: sin truncar los microsegundos, el
            # token recién emitido en el mismo segundo que el cambio se
            # rechazaría a sí mismo.
            raise AuthenticationFailed(
                "La sesión ha caducado porque las credenciales han cambiado. "
                "Vuelve a iniciar sesión.",
                code="session_revoked",
            )

        return user


class CredentialEpochJWTScheme(OpenApiAuthenticationExtension):
    """
    Declara el esquema de seguridad en OpenAPI.

    Sin esta extensión, drf-spectacular no reconoce la clase propia de
    autenticación y genera el esquema sin ningún `securityScheme`: la
    documentación resultante no indicaría que los endpoints necesitan un
    Bearer token.
    """

    target_class = "core.interfaces.api.authentication.CredentialEpochJWTAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": (
                "Token JWT de acceso obtenido en `/api/auth/login/`. "
                "Se invalida al cambiar la contraseña o el email."
            ),
        }
