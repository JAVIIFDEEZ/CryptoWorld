"""
application/services/login_guard.py — Bloqueo temporal por cuenta.

El `ScopedRateThrottle` de DRF limita por **IP**, lo que no cubre el
ataque realista: una botnet repartiendo intentos contra una sola cuenta
desde miles de direcciones distintas nunca alcanza el límite por IP.

Este guardia cuenta los fallos **por cuenta** y bloquea temporalmente el
acceso a esa cuenta cuando se superan. Se aplica a los dos factores:

  - Contraseña en `/api/auth/login/`.
  - Código TOTP y de recuperación en `/api/auth/2fa/login/`, donde el
    espacio de búsqueda es de solo un millón de combinaciones.

El contador vive en la cache (Redis) con expiración automática, de modo
que el bloqueo se levanta solo y no requiere intervención ni tabla extra.
Si la cache no está disponible el guardia se abre (fail-open): preferimos
un servicio degradado antes que dejar a todos los usuarios fuera.
"""

import logging
from dataclasses import dataclass

from django.core.cache import cache

logger = logging.getLogger(__name__)

# Umbrales por factor. El segundo factor es más estricto porque su
# espacio de claves (6 dígitos) es mucho menor que el de una contraseña.
PASSWORD_MAX_ATTEMPTS = 8
PASSWORD_LOCKOUT_SECONDS = 15 * 60

TOTP_MAX_ATTEMPTS = 5
TOTP_LOCKOUT_SECONDS = 15 * 60


@dataclass(frozen=True)
class GuardPolicy:
    """Parámetros de un guardia concreto."""

    scope: str
    max_attempts: int
    lockout_seconds: int


PASSWORD_POLICY = GuardPolicy("login", PASSWORD_MAX_ATTEMPTS, PASSWORD_LOCKOUT_SECONDS)
TOTP_POLICY = GuardPolicy("2fa", TOTP_MAX_ATTEMPTS, TOTP_LOCKOUT_SECONDS)


class AccountLockedError(Exception):
    """La cuenta está temporalmente bloqueada por exceso de intentos."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        minutes = max(1, round(retry_after_seconds / 60))
        super().__init__(
            "Demasiados intentos fallidos. La cuenta está bloqueada "
            f"temporalmente; inténtalo de nuevo en {minutes} minutos."
        )


def _key(policy: GuardPolicy, identity: str) -> str:
    # La identidad se normaliza para que 'User@X.com' y 'user@x.com'
    # compartan contador y no dupliquen el presupuesto de intentos.
    return f"loginguard:{policy.scope}:{identity.strip().lower()}"


def ensure_not_locked(policy: GuardPolicy, identity: str) -> None:
    """
    Comprobar el contador antes de validar la credencial.

    Raises:
        AccountLockedError: si la cuenta agotó los intentos permitidos.
    """
    if not identity:
        return
    try:
        attempts = cache.get(_key(policy, identity), 0)
    except Exception:
        logger.warning("Cache no disponible: el guardia de login se abre", exc_info=True)
        return

    if attempts >= policy.max_attempts:
        raise AccountLockedError(policy.lockout_seconds)


def register_failure(policy: GuardPolicy, identity: str) -> int:
    """
    Contabilizar un intento fallido. Devuelve el total acumulado.

    El TTL se fija en la primera escritura y no se renueva con cada
    fallo: así el bloqueo dura una ventana fija desde el primer intento
    y no se prolonga indefinidamente mientras el atacante siga probando.
    """
    if not identity:
        return 0

    key = _key(policy, identity)
    try:
        # `add` solo escribe si la clave no existía: crea la ventana con
        # su TTL. Si ya existía, `incr` suma sin tocar la expiración.
        if cache.add(key, 1, policy.lockout_seconds):
            return 1
        return cache.incr(key)
    except ValueError:
        # La clave expiró entre el `add` y el `incr`: reiniciar ventana.
        cache.set(key, 1, policy.lockout_seconds)
        return 1
    except Exception:
        logger.warning("No se pudo contabilizar el intento fallido", exc_info=True)
        return 0


def reset(policy: GuardPolicy, identity: str) -> None:
    """Limpiar el contador tras una autenticación correcta."""
    if not identity:
        return
    try:
        cache.delete(_key(policy, identity))
    except Exception:
        logger.warning("No se pudo limpiar el contador de intentos", exc_info=True)
