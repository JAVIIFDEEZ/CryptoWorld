"""
tests/unit/test_settings_hardening.py — Postura de seguridad de la configuración.

`config.settings` decide, en función del entorno, si la aplicación arranca y
con qué cabeceras. Es código, y como tal se prueba: un despliegue que arranque
con la clave de ejemplo o sin HSTS es un incidente, no un detalle de estilo.

Se recarga el módulo con `os.environ` sustituido para observar el efecto real
de cada variable, que es justo lo que no se puede comprobar con override_settings.
"""

import importlib
import sys
from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured

BASE_PROD_ENV = {
    "DJANGO_DEBUG": "False",
    "DJANGO_SECRET_KEY": "una-clave-de-produccion-larga-y-aleatoria-0123456789",
    "DJANGO_ALLOWED_HOSTS": "cryptoworld.example.com",
    "CORS_ALLOWED_ORIGINS": "https://cryptoworld.example.com",
}


def _load_settings(env: dict):
    """Importa config.settings de cero con el entorno dado."""
    # load_dotenv() rellenaría huecos desde un .env local y haría el test
    # dependiente de la máquina; se neutraliza.
    with mock.patch.dict("os.environ", env, clear=True), \
            mock.patch("dotenv.load_dotenv", lambda *a, **k: False):
        sys.modules.pop("config.settings", None)
        return importlib.import_module("config.settings")


@pytest.fixture(autouse=True)
def _restore_settings_module():
    """Deja el módulo real cargado: otros tests dependen de él."""
    yield
    sys.modules.pop("config.settings", None)
    importlib.import_module("config.settings")


class TestFailFast:
    """Un despliegue mal configurado debe abortar, no servir tráfico inseguro."""

    @pytest.mark.unit
    def test_example_secret_key_aborts_in_production(self):
        env = BASE_PROD_ENV | {"DJANGO_SECRET_KEY": "django-insecure-change-this-in-production-key-12345"}
        with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
            _load_settings(env)

    @pytest.mark.unit
    def test_short_secret_key_aborts_in_production(self):
        with pytest.raises(ImproperlyConfigured, match="corta"):
            _load_settings(BASE_PROD_ENV | {"DJANGO_SECRET_KEY": "corta"})

    @pytest.mark.unit
    def test_wildcard_allowed_hosts_aborts_in_production(self):
        with pytest.raises(ImproperlyConfigured, match="ALLOWED_HOSTS"):
            _load_settings(BASE_PROD_ENV | {"DJANGO_ALLOWED_HOSTS": "*"})

    @pytest.mark.unit
    def test_development_tolerates_the_example_key(self):
        """En local la clave de ejemplo es aceptable: sin ella no se arranca
        el proyecto recién clonado."""
        settings = _load_settings({"DJANGO_DEBUG": "True"})
        assert settings.DEBUG is True


class TestSecurityHeaders:

    @pytest.mark.unit
    def test_production_enables_https_hardening(self):
        settings = _load_settings(BASE_PROD_ENV)
        assert settings.SECURE_SSL_REDIRECT is True
        assert settings.SECURE_HSTS_SECONDS >= 31536000
        assert settings.SECURE_HSTS_INCLUDE_SUBDOMAINS is True
        assert settings.SECURE_HSTS_PRELOAD is True
        assert settings.SESSION_COOKIE_SECURE is True
        assert settings.CSRF_COOKIE_SECURE is True
        # Detrás de un proxy que termina TLS, sin esto Django entra en bucle
        # de redirección.
        assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")

    @pytest.mark.unit
    def test_transport_independent_headers_apply_always(self):
        settings = _load_settings({"DJANGO_DEBUG": "True"})
        assert settings.SECURE_CONTENT_TYPE_NOSNIFF is True
        assert settings.X_FRAME_OPTIONS == "DENY"
        assert settings.SESSION_COOKIE_HTTPONLY is True
        assert settings.SECURE_REFERRER_POLICY == "strict-origin-when-cross-origin"

    @pytest.mark.unit
    def test_csrf_trusted_origins_derive_from_cors(self):
        settings = _load_settings(BASE_PROD_ENV)
        assert settings.CSRF_TRUSTED_ORIGINS == ["https://cryptoworld.example.com"]

    @pytest.mark.unit
    def test_explicit_csrf_trusted_origins_win(self):
        settings = _load_settings(
            BASE_PROD_ENV | {"CSRF_TRUSTED_ORIGINS": "https://admin.example.com"}
        )
        assert settings.CSRF_TRUSTED_ORIGINS == ["https://admin.example.com"]


class TestThrottling:

    @pytest.mark.unit
    def test_global_throttle_classes_are_declared(self):
        """Antes solo estaban limitados los endpoints con scope declarado: el
        resto de la API (más de cien rutas) no tenía techo alguno."""
        settings = _load_settings({"DJANGO_DEBUG": "True"})
        classes = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"]
        assert "rest_framework.throttling.AnonRateThrottle" in classes
        assert "rest_framework.throttling.UserRateThrottle" in classes

    @pytest.mark.unit
    def test_trading_order_scope_exists(self):
        settings = _load_settings({"DJANGO_DEBUG": "True"})
        assert "trading_order" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]


class TestEnvBool:
    """La lectura de booleanos tolera las formas habituales."""

    @pytest.mark.unit
    @pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "on", "True"])
    def test_truthy_forms(self, raw):
        assert _load_settings({"DJANGO_DEBUG": raw}).DEBUG is True

    @pytest.mark.unit
    @pytest.mark.parametrize("raw", ["false", "0", "no", "off", "False"])
    def test_falsy_forms(self, raw):
        assert _load_settings(BASE_PROD_ENV | {"DJANGO_DEBUG": raw}).DEBUG is False
