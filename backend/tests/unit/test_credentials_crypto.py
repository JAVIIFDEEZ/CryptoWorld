"""
tests/unit/test_credentials_crypto.py — Anillo de claves de cifrado.

Las claves API de los exchanges son el secreto más sensible que guarda la
plataforma: con ellas se opera dinero real. Estos tests fijan las propiedades
que debe cumplir su cifrado:

  · round-trip correcto y ciphertext que no filtra el claro;
  · la clave de cifrado se separa de SECRET_KEY (rotar la de firma no puede
    dejar ilegibles las credenciales de todo el mundo);
  · rotación sin downtime: la clave nueva cifra, las antiguas siguen leyendo;
  · lo cifrado con el esquema legado (derivado de SECRET_KEY) se sigue
    descifrando tras introducir el anillo — ninguna credencial se pierde.
"""

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from core.infrastructure.security import crypto


@pytest.fixture(autouse=True)
def _clear_ring():
    """El anillo se memoriza; cada test parte de uno limpio."""
    crypto.reset_key_cache()
    yield
    crypto.reset_key_cache()


KEY_A = Fernet.generate_key().decode()
KEY_B = Fernet.generate_key().decode()


class TestRoundTrip:

    @pytest.mark.unit
    @override_settings(CREDENTIALS_ENCRYPTION_KEYS=[KEY_A])
    def test_roundtrip_and_opaque_ciphertext(self):
        token = crypto.encrypt_secret("clave-api-secreta")
        assert "clave-api-secreta" not in token
        assert crypto.decrypt_secret(token) == "clave-api-secreta"

    @pytest.mark.unit
    @override_settings(CREDENTIALS_ENCRYPTION_KEYS=[KEY_A])
    def test_ciphertext_is_not_deterministic(self):
        """Fernet lleva IV aleatorio: dos cifrados del mismo secreto difieren,
        así que el ciphertext no delata que dos usuarios comparten clave."""
        assert crypto.encrypt_secret("misma") != crypto.encrypt_secret("misma")

    @pytest.mark.unit
    @override_settings(CREDENTIALS_ENCRYPTION_KEYS=["passphrase-larga-de-entorno"])
    def test_passphrase_is_accepted_via_hkdf(self):
        """El material no tiene por qué ser una clave Fernet: una passphrase
        se deriva con HKDF-SHA256."""
        token = crypto.encrypt_secret("secreto")
        assert crypto.decrypt_secret(token) == "secreto"

    @pytest.mark.unit
    @override_settings(CREDENTIALS_ENCRYPTION_KEYS=[KEY_A])
    def test_corrupt_token_raises_decryption_error(self):
        with pytest.raises(crypto.DecryptionError):
            crypto.decrypt_secret("esto-no-es-un-token")


class TestSecretKeyIndependence:

    @pytest.mark.unit
    def test_rotating_secret_key_does_not_break_credentials(self):
        """El punto de todo el cambio: con clave dedicada, rotar SECRET_KEY
        deja de invalidar las credenciales guardadas."""
        with override_settings(CREDENTIALS_ENCRYPTION_KEYS=[KEY_A], SECRET_KEY="clave-de-firma-vieja"):
            token = crypto.encrypt_secret("api-key")

        crypto.reset_key_cache()
        with override_settings(CREDENTIALS_ENCRYPTION_KEYS=[KEY_A], SECRET_KEY="clave-de-firma-NUEVA"):
            assert crypto.decrypt_secret(token) == "api-key"

    @pytest.mark.unit
    def test_legacy_tokens_remain_readable(self):
        """Compatibilidad: lo cifrado antes del anillo (derivado de SECRET_KEY)
        se sigue leyendo tras configurar claves dedicadas."""
        with override_settings(CREDENTIALS_ENCRYPTION_KEYS=[], SECRET_KEY="clave-de-firma-estable"):
            legacy_token = crypto.encrypt_secret("credencial-antigua")

        crypto.reset_key_cache()
        with override_settings(CREDENTIALS_ENCRYPTION_KEYS=[KEY_A], SECRET_KEY="clave-de-firma-estable"):
            assert crypto.decrypt_secret(legacy_token) == "credencial-antigua"


class TestRotation:

    @pytest.mark.unit
    def test_new_key_encrypts_old_key_still_decrypts(self):
        with override_settings(CREDENTIALS_ENCRYPTION_KEYS=[KEY_A]):
            old_token = crypto.encrypt_secret("secreto")

        crypto.reset_key_cache()
        # Rotación: la nueva va delante, la anterior se conserva para leer.
        with override_settings(CREDENTIALS_ENCRYPTION_KEYS=[KEY_B, KEY_A]):
            assert crypto.decrypt_secret(old_token) == "secreto"
            assert crypto.needs_rotation(old_token) is True

            rotated = crypto.rotate_secret(old_token)
            assert crypto.decrypt_secret(rotated) == "secreto"
            assert crypto.needs_rotation(rotated) is False

    @pytest.mark.unit
    @override_settings(CREDENTIALS_ENCRYPTION_KEYS=[])
    def test_no_rotation_reported_without_configured_keys(self):
        """Sin anillo configurado no hay 'clave activa' que perseguir."""
        assert crypto.needs_rotation(crypto.encrypt_secret("x")) is False
