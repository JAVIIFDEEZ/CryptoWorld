"""
crypto.py — Cifrado simétrico de secretos de usuario (claves API de exchanges).

Fernet (AES-128-CBC + HMAC-SHA256, de la librería `cryptography`) sobre un
anillo de claves con rotación:

  · El material viene de ``settings.CREDENTIALS_ENCRYPTION_KEYS`` — una lista
    donde la PRIMERA clave cifra y TODAS descifran. Rotar es poner la nueva al
    principio: lo ya guardado se sigue leyendo y se recifra solo al guardarse
    de nuevo (ver :func:`needs_rotation`).
  · Cada entrada puede ser una clave Fernet ya formada (32 bytes en base64
    urlsafe) o una passphrase arbitraria, de la que se deriva la clave con
    HKDF-SHA256 y un `info` de dominio. HKDF, y no un SHA-256 a secas, es lo
    que evita que la misma passphrase reutilizada en otro subsistema produzca
    exactamente la misma clave.
  · Si no hay claves configuradas se deriva de ``SECRET_KEY`` con el esquema
    legado (SHA-256 directo). Esto mantiene legibles las credenciales ya
    guardadas; es un modo de compatibilidad, no el recomendado.

El anillo se separa a propósito de SECRET_KEY: esa clave firma tokens JWT y
cookies y se rota con frecuencia, y rotarla no debería dejar sin acceso a las
credenciales de exchange de todos los usuarios. Las credenciales se descifran
solo al construir el cliente del exchange; la API nunca las devuelve.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

# Etiqueta de dominio de HKDF: ata la clave derivada a este uso concreto.
_HKDF_INFO = b"cryptoworld.exchange-credentials.v1"


class DecryptionError(Exception):
    """El secreto no puede descifrarse (clave fuera del anillo o dato corrupto)."""


def _is_fernet_key(material: str) -> bool:
    """¿El material ya es una clave Fernet (32 bytes en base64 urlsafe)?"""
    try:
        return len(base64.urlsafe_b64decode(material.encode("utf-8"))) == 32
    except (ValueError, TypeError):
        return False


def _derive(material: str) -> bytes:
    """Passphrase → clave Fernet vía HKDF-SHA256.

    Sin sal: el material de entrada es un secreto de alta entropía tomado del
    entorno, no una contraseña de usuario, y la derivación debe ser
    determinista entre procesos y reinicios (no hay dónde persistir una sal
    junto a cada token). El `info` de dominio aporta la separación de usos.
    """
    kdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_HKDF_INFO)
    return base64.urlsafe_b64encode(kdf.derive(material.encode("utf-8")))


def _key_to_fernet(material: str) -> Fernet:
    return Fernet(material if _is_fernet_key(material) else _derive(material))


def _legacy_fernet() -> Fernet:
    """Esquema histórico: SHA-256 directo sobre SECRET_KEY.

    Se conserva SOLO para descifrar lo guardado antes de introducir el anillo
    de claves. Nunca cifra mientras haya alguna clave configurada.
    """
    from django.conf import settings

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


@lru_cache(maxsize=1)
def _ring() -> MultiFernet:
    """Anillo de claves: la primera cifra, todas descifran."""
    from django.conf import settings

    materials = list(getattr(settings, "CREDENTIALS_ENCRYPTION_KEYS", []) or [])
    keys = [_key_to_fernet(m) for m in materials]

    # La clave legada va SIEMPRE al final: descifra lo antiguo sin ser nunca
    # la clave de cifrado mientras haya alguna configurada.
    keys.append(_legacy_fernet())

    if not materials:
        logger.warning(
            "CREDENTIALS_ENCRYPTION_KEYS no está configurada: las credenciales de "
            "exchange se cifran con una clave derivada de SECRET_KEY, de modo que "
            "rotar SECRET_KEY las dejará ilegibles."
        )
    return MultiFernet(keys)


def reset_key_cache() -> None:
    """Descarta el anillo memorizado (tests y recarga de configuración)."""
    _ring.cache_clear()


def encrypt_secret(plain: str) -> str:
    """Cifra un secreto → token Fernet (str) con la clave activa."""
    return _ring().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    """Descifra un token Fernet con cualquier clave del anillo → secreto en claro."""
    try:
        return _ring().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise DecryptionError("No se pudo descifrar la credencial guardada.") from exc


def needs_rotation(token: str) -> bool:
    """¿El token está cifrado con una clave que ya no es la activa?

    Permite recifrar de forma perezosa (al leer o guardar) sin migración
    masiva: la credencial queda bajo la clave nueva la próxima vez que se toca.
    """
    from django.conf import settings

    materials = list(getattr(settings, "CREDENTIALS_ENCRYPTION_KEYS", []) or [])
    if not materials:
        return False
    try:
        _key_to_fernet(materials[0]).decrypt(token.encode("utf-8"))
        return False
    except (InvalidToken, ValueError):
        return True


def rotate_secret(token: str) -> str:
    """Recifra un token con la clave activa, conservando el secreto."""
    return encrypt_secret(decrypt_secret(token))
