"""
use_cases/recovery_codes.py — Gestión de códigos de recuperación 2FA.

Los códigos son la vía de acceso de emergencia si el usuario pierde su
dispositivo TOTP. Reglas:
  - 10 códigos por usuario, formato XXXX-XXXX con alfabeto sin caracteres
    ambiguos (sin 0/O, 1/I/L).
  - Solo se almacena el hash; el código en claro se muestra una vez.
  - Cada código es de un solo uso (used_at marca el consumo).
  - Regenerar invalida todos los anteriores.
"""

import secrets

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from core.infrastructure.persistence.models import TwoFactorRecoveryCode, User

# Alfabeto sin caracteres ambiguos (0/O, 1/I/L)
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_COUNT = 10
_GROUP_LEN = 4


def _random_code() -> str:
    groups = [
        "".join(secrets.choice(_ALPHABET) for _ in range(_GROUP_LEN))
        for _ in range(2)
    ]
    return "-".join(groups)


def generate_recovery_codes(user: User) -> list[str]:
    """
    Genera un juego nuevo de códigos para el usuario.

    Invalida (borra) cualquier código anterior, usado o no.
    Devuelve los códigos en claro — única vez que existen sin hashear.
    """
    TwoFactorRecoveryCode.objects.filter(user=user).delete()

    plain_codes = [_random_code() for _ in range(_CODE_COUNT)]
    TwoFactorRecoveryCode.objects.bulk_create(
        TwoFactorRecoveryCode(user=user, code_hash=make_password(code))
        for code in plain_codes
    )
    return plain_codes


def consume_recovery_code(user: User, code: str) -> bool:
    """
    Verifica un código de recuperación y lo marca como usado.

    Devuelve True si el código era válido y estaba disponible.
    """
    normalized = code.strip().upper()
    if not normalized:
        return False

    available = TwoFactorRecoveryCode.objects.filter(user=user, used_at__isnull=True)
    for stored in available:
        if check_password(normalized, stored.code_hash):
            stored.used_at = timezone.now()
            stored.save(update_fields=["used_at"])
            return True
    return False


def remaining_recovery_codes(user: User) -> int:
    """Número de códigos aún disponibles (no usados)."""
    return TwoFactorRecoveryCode.objects.filter(user=user, used_at__isnull=True).count()


def delete_recovery_codes(user: User) -> None:
    """Elimina todos los códigos (al desactivar 2FA)."""
    TwoFactorRecoveryCode.objects.filter(user=user).delete()
