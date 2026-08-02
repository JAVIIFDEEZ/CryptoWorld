"""
application/services/sessions.py — Invalidación de sesiones.

Cambiar la contraseña es la acción con la que un usuario responde a una
sospecha de compromiso. Si las sesiones ya emitidas siguen vivas, la
acción no sirve para nada: el atacante conserva el acceso hasta que
caduque su refresh token (siete días).

La revocación tiene dos mitades, porque los dos tipos de token se
invalidan de forma distinta:

  - **Refresh tokens**: se listan en `OutstandingToken` y se meten en la
    blacklist de SimpleJWT, de modo que dejan de poder renovar nada.
  - **Access tokens**: no son revocables de uno en uno (son autónomos y
    se validan solo con la firma). Se invalidan en bloque marcando en el
    usuario el instante del cambio (`credentials_changed_at`); la clase
    de autenticación rechaza cualquier token emitido antes de esa marca.
"""

import logging

from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)

# Claim que transporta la marca de revocación vigente cuando se emitió el
# token. La clase de autenticación lo compara con la del usuario.
CREDENTIAL_EPOCH_CLAIM = "cred_epoch"


def revoke_all_sessions(user) -> int:
    """
    Revocar todas las sesiones activas del usuario.

    Args:
        user: instancia del modelo User.

    Returns:
        Número de refresh tokens añadidos a la blacklist.
    """
    revoked = 0
    outstanding = OutstandingToken.objects.filter(user=user).only("id")
    for token in outstanding.iterator():
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        if created:
            revoked += 1

    # Marca temporal que invalida los access tokens ya emitidos. Se guarda
    # después de la blacklist para que no exista una ventana en la que los
    # access sigan siendo válidos y los refresh ya no.
    user.credentials_changed_at = timezone.now()
    user.save(update_fields=["credentials_changed_at"])

    logger.info(
        "Sesiones revocadas para user_id=%s (%d refresh tokens en blacklist)",
        user.pk,
        revoked,
    )
    return revoked


def build_refresh_token(user) -> RefreshToken:
    """
    Crear el refresh token de un usuario con su marca de revocación.

    Todos los puntos que emiten sesión (login, segundo factor, cambio de
    contraseña) pasan por aquí para que ninguno olvide el claim.

    Sobre `CREDENTIAL_EPOCH_CLAIM`: la alternativa evidente sería comparar
    el `iat` del token con `credentials_changed_at`, pero `iat` tiene
    resolución de **un segundo**. Un token emitido en el mismo segundo que
    el cambio de credenciales es indistinguible de uno emitido justo
    antes, así que o se cuela una sesión antigua o se invalida la recién
    creada. El claim lleva la marca exacta con microsegundos y elimina
    esa ambigüedad por completo.

    SimpleJWT copia los claims personalizados del refresh al access
    (NO_COPY_CLAIMS solo excluye tipo, expiración y jti), de modo que
    basta con ponerlo una vez.
    """
    refresh = RefreshToken.for_user(user)
    refresh[CREDENTIAL_EPOCH_CLAIM] = _epoch_of(user)
    return refresh


def issue_session(user) -> dict:
    """
    Emitir un par de tokens nuevo para el usuario.

    Se usa tras revocar las sesiones en una operación que el propio
    usuario ha iniciado y autenticado (cambio de contraseña): expulsa a
    todos los demás dispositivos sin echar al que está haciendo el
    cambio, que es el comportamiento esperado.
    """
    refresh = build_refresh_token(user)
    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    }


def _epoch_of(user) -> float:
    """
    Marca de revocación del usuario como timestamp Unix con decimales.

    Cero para las cuentas que nunca han cambiado credenciales: cualquier
    token suyo es válido mientras no caduque.
    """
    changed_at = getattr(user, "credentials_changed_at", None)
    return changed_at.timestamp() if changed_at else 0.0
