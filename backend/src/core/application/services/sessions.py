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


def issue_session(user) -> dict:
    """
    Emitir un par de tokens nuevo para el usuario.

    Se usa tras revocar las sesiones en una operación que el propio
    usuario ha iniciado y autenticado (cambio de contraseña): expulsa a
    todos los demás dispositivos sin echar al que está haciendo el
    cambio, que es el comportamiento esperado.
    """
    refresh = RefreshToken.for_user(user)
    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    }
