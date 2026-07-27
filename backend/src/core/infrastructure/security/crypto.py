"""
crypto.py — Cifrado simétrico de secretos de usuario (claves API de exchanges).

Fernet (AES-128-CBC + HMAC, de la librería cryptography) con clave derivada de
SECRET_KEY vía SHA-256. Las credenciales se cifran al guardar y solo se
descifran en el momento de construir el cliente del exchange; la API nunca las
devuelve. Si SECRET_KEY rota, las conexiones guardadas dejan de descifrar y el
usuario debe reintroducirlas (comportamiento deseado: no hay puerta trasera).
"""

import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


class DecryptionError(Exception):
    """El secreto no puede descifrarse (SECRET_KEY rotada o dato corrupto)."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    from django.conf import settings

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    """Cifra un secreto → token Fernet (str)."""
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    """Descifra un token Fernet → secreto en claro."""
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise DecryptionError("No se pudo descifrar la credencial guardada.") from exc
