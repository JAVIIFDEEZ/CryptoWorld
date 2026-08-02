"""
interfaces/api/authentication.py — Autenticación JWT con corte por epoch.

`JWTAuthentication` de SimpleJWT valida firma y caducidad, pero no puede
saber que las credenciales del usuario cambiaron después de emitir el
token: un access token robado sigue funcionando hasta agotar su vida
útil aunque la víctima ya haya cambiado la contraseña.

Esta subclase añade esa comprobación. Cada token emitido lleva el claim
`cred_epoch` con la marca de revocación vigente en ese momento; si el
usuario ha revocado sus sesiones después, su marca es mayor que la del
token y este se rechaza.

Es la mitad que le faltaba a la blacklist de refresh tokens para que la
revocación sea completa: la blacklist corta la renovación, el claim corta
los access tokens que ya están en circulación.
"""

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from core.application.services.sessions import CREDENTIAL_EPOCH_CLAIM

_REVOKED_MESSAGE = (
    "La sesión ha caducado porque las credenciales de la cuenta han "
    "cambiado. Vuelve a iniciar sesión."
)


class CredentialEpochJWTAuthentication(JWTAuthentication):
    """JWT que además respeta la marca de revocación global del usuario."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        changed_at = getattr(user, "credentials_changed_at", None)
        if changed_at is None:
            # La cuenta nunca ha revocado sesiones: nada que comprobar.
            return user

        token_epoch = validated_token.get(CREDENTIAL_EPOCH_CLAIM)
        if token_epoch is None:
            # Token emitido antes de que existiera el claim, o manipulado
            # para omitirlo. Con una revocación vigente sobre la cuenta, la
            # única respuesta segura es rechazarlo.
            raise AuthenticationFailed(_REVOKED_MESSAGE, code="session_revoked")

        if float(token_epoch) < changed_at.timestamp():
            raise AuthenticationFailed(_REVOKED_MESSAGE, code="session_revoked")

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
