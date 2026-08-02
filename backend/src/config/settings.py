"""
settings.py — Configuración central de Django.

Esta capa pertenece a la INFRAESTRUCTURA del proyecto.
Su responsabilidad es orquestar todos los adaptadores externos:
base de datos, autenticación, middleware, apps instaladas, etc.

No contiene lógica de negocio. Solo configuración del framework.
"""

import os
import re
from datetime import timedelta
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# ------------------------------------------------------------------
# Rutas base
# ------------------------------------------------------------------
# BASE_DIR apunta a  backend/src/
BASE_DIR = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------
# Helpers de lectura de entorno
#
# Toda la configuración sensible entra por variables de entorno. Estos
# helpers centralizan el parseo para que ningún bloque de abajo tenga
# que repetir comparaciones de cadenas ni `split` a mano.
# ------------------------------------------------------------------

def _env_bool(name: str, default: bool) -> bool:
    """Leer un booleano tolerando 'True'/'true'/'1'/'yes'/'on'."""
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_list(name: str, default: str = "") -> list[str]:
    """Leer una lista separada por comas y/o espacios, sin elementos vacíos."""
    raw = os.environ.get(name, default).strip()
    if not raw:
        return []
    return [item for item in re.split(r"[,\s]+", raw) if item]


# ------------------------------------------------------------------
# Seguridad
#
# Política de despliegue: la configuración por defecto es la SEGURA.
# Un despliegue al que se le olvida definir una variable crítica no
# arranca en modo inseguro — falla de forma ruidosa en el arranque.
# ------------------------------------------------------------------
DEBUG = _env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()

# La SECRET_KEY firma los JWT (HS256), los tokens de verificación de email
# y los de recuperación de contraseña. Una clave conocida equivale a poder
# emitir sesiones y tokens de cualquier usuario, así que en producción no
# se admite ni ausente ni corta (Django genera claves de 50 caracteres).
_MIN_SECRET_KEY_LENGTH = 50

if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY es obligatoria cuando DJANGO_DEBUG=False. "
            "Genérala con: python -c \"from django.core.management.utils import "
            "get_random_secret_key; print(get_random_secret_key())\""
        )
    # Solo en desarrollo: clave efímera distinta en cada arranque. No se
    # define una constante en el código fuente precisamente para que sea
    # imposible que una clave del repositorio acabe firmando en producción.
    from django.core.management.utils import get_random_secret_key

    SECRET_KEY = get_random_secret_key()
elif not DEBUG and len(SECRET_KEY) < _MIN_SECRET_KEY_LENGTH:
    raise ImproperlyConfigured(
        f"DJANGO_SECRET_KEY debe tener al menos {_MIN_SECRET_KEY_LENGTH} "
        f"caracteres en producción (recibidos {len(SECRET_KEY)})."
    )

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost 127.0.0.1")

if not DEBUG and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS debe listar los dominios reales del servicio "
        "cuando DJANGO_DEBUG=False (el comodín '*' no está permitido)."
    )

# ------------------------------------------------------------------
# Aplicaciones instaladas
# ------------------------------------------------------------------
INSTALLED_APPS = [
    # Apps de Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Terceros
    "rest_framework",                          # Django REST Framework
    "rest_framework_simplejwt",                # Autenticación JWT
    "rest_framework_simplejwt.token_blacklist", # Blacklist para logout seguro
    "corsheaders",                             # CORS para comunicación con el frontend
    "django_celery_beat",                      # Scheduler persistente para Celery beat
    "anymail",                                 # SendGrid API nativa (mejor que SMTP)
    "drf_spectacular",                         # Esquema OpenAPI 3 autogenerado

    # Apps del proyecto (capa interfaces expone los endpoints)
    "core",
]

# ------------------------------------------------------------------
# Middleware
# ------------------------------------------------------------------
MIDDLEWARE = [
    # Genera/propaga el identificador de correlación antes que nada, para
    # que cualquier log emitido durante la petición lo lleve.
    "config.middleware.RequestIDMiddleware",
    "corsheaders.middleware.CorsMiddleware",          # Debe ir después del request-id
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",     # Archivos estáticos sin Nginx (Railway)
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "core" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ------------------------------------------------------------------
# Base de datos — PostgreSQL
# Se configura completamente desde variables de entorno para
# facilitar despliegue en Docker y producción sin cambios en código.
# ------------------------------------------------------------------
# Railway inyecta DATABASE_URL automáticamente desde el plugin PostgreSQL.
# Si existe, tiene prioridad. Si no, se usan las variables individuales (Docker).
_database_url = os.environ.get("DATABASE_URL")
if _database_url:
    DATABASES = {"default": dj_database_url.parse(_database_url, conn_max_age=600)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "cryptoworld_db"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }

# ------------------------------------------------------------------
# Validadores de contraseña
# ------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        # 12 caracteres: recomendación de NIST SP 800-63B para secretos
        # memorizados sin composición forzada de caracteres.
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Longitud mínima de contraseña expuesta a la capa de interfaces para que
# los serializers no dupliquen la constante.
PASSWORD_MIN_LENGTH = 12

# ------------------------------------------------------------------
# Cabeceras de seguridad HTTP y cookies
#
# Las que no dependen de TLS se aplican siempre (también en desarrollo,
# para que un fallo se detecte antes de producción). Las que romperían
# el desarrollo en HTTP plano se activan solo con DEBUG=False.
# ------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
# La API no se sirve nunca dentro de un iframe; DENY es más estricto que
# SAMEORIGIN y elimina el vector de clickjacking sobre el admin de Django.
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# El admin de Django es la única superficie con sesión de cookie; su
# duración se acota para reducir la ventana de una cookie robada.
SESSION_COOKIE_AGE = int(os.environ.get("DJANGO_SESSION_COOKIE_AGE", str(60 * 60 * 8)))
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Orígenes autorizados a enviar formularios con CSRF token (admin de Django
# tras un proxy TLS). Sin esto Django rechaza el login del admin en HTTPS.
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")

if not DEBUG:
    # Detrás de nginx/Railway la conexión al backend es HTTP plano; la
    # cabecera del proxy es lo que indica que el cliente venía por HTTPS.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    # Los healthchecks del orquestador consultan por HTTP dentro de la red
    # privada: redirigirlos a HTTPS los haría fallar y tumbaría el
    # servicio. El patrón cubre tanto `/api/health/` (readiness) como
    # `/api/health/live/` (liveness, la que usa el HEALTHCHECK de Docker);
    # los patrones se comparan contra la ruta sin la barra inicial.
    SECURE_REDIRECT_EXEMPT = [r"^api/health/"]

    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", str(60 * 60 * 24 * 365)))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", True)
    SECURE_HSTS_PRELOAD = _env_bool("DJANGO_HSTS_PRELOAD", True)

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    if not CSRF_TRUSTED_ORIGINS:
        # Por defecto, los mismos orígenes que ya confiamos para CORS.
        CSRF_TRUSTED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS")

# ------------------------------------------------------------------
# Internacionalización
# ------------------------------------------------------------------
LANGUAGE_CODE = "es-es"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ------------------------------------------------------------------
# Archivos estáticos
# ------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------
# Modelo de usuario personalizado
# Apuntamos al modelo extendido definido en la capa de infraestructura.
# Esto permite añadir campos sin romper contratos con Django auth.
# ------------------------------------------------------------------
AUTH_USER_MODEL = "core.User"

# ------------------------------------------------------------------
# Django REST Framework
# Se configura autenticación JWT por defecto para todos los endpoints.
# ------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        # Subclase propia: además de firma y caducidad, rechaza los tokens
        # emitidos antes del último cambio de credenciales del usuario.
        "core.interfaces.api.authentication.CredentialEpochJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    # Contrato de error uniforme para toda la API (ver
    # core/interfaces/api/exception_handler.py).
    "EXCEPTION_HANDLER": "core.interfaces.api.exception_handler.api_exception_handler",
    # Paginación por defecto de los listados (?page= y ?page_size=).
    "DEFAULT_PAGINATION_CLASS": "core.interfaces.api.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    # Esquema OpenAPI 3 generado con drf-spectacular.
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Rate limiting global por IP (anónimos) y por usuario (autenticados),
    # además del ScopedRateThrottle declarado view a view en los endpoints
    # sensibles de auth. El contador vive en la cache Redis.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("THROTTLE_ANON", "120/min"),
        "user": os.environ.get("THROTTLE_USER", "1000/hour"),
        "auth_login": "10/min",
        "auth_register": "10/hour",
        "auth_password_reset": "5/hour",
        "auth_resend_verification": "5/hour",
        "auth_change_email": "5/hour",
        "auth_2fa": "10/min",
        # Los endpoints de análisis disparan cálculo pesado (ML, backtesting)
        # y llamadas a APIs externas con cuota: se limitan aparte.
        "analysis": os.environ.get("THROTTLE_ANALYSIS", "60/min"),
    },
}

# ------------------------------------------------------------------
# OpenAPI / drf-spectacular — documentación viva de la API
# ------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "CryptoWorld API",
    "DESCRIPTION": (
        "API REST de la plataforma de análisis cuantitativo de criptomonedas "
        "CryptoWorld. Autenticación JWT (Bearer) con soporte de doble factor TOTP."
    ),
    "VERSION": os.environ.get("APP_VERSION", "1.139.0"),
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api",
}

# ------------------------------------------------------------------
# SimpleJWT — Configuración de tokens
# ------------------------------------------------------------------
SIMPLE_JWT = {
    # Access corto: el token viaja al navegador y no se puede revocar de
    # forma individual, así que la ventana de uso de uno robado se acota
    # con su caducidad. La renovación es transparente para el cliente
    # (interceptor de Axios) mediante el refresh token.
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "15"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.environ.get("JWT_REFRESH_DAYS", "7"))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ------------------------------------------------------------------
# CORS — Permitir peticiones desde el frontend React
# ------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = re.split(r'[,\s]+', os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173 http://127.0.0.1:5173"
).strip())

CORS_ALLOW_CREDENTIALS = True

# ------------------------------------------------------------------
# Email — Selección automática de backend por variables de entorno
#
# Prioridad (de mayor a menor):
#   1. SENDGRID_API_KEY definida  → SendGrid Web API v3 (vía anymail).
#      Mejor deliverability, tracking y webhooks que SMTP puro.
#   2. EMAIL_HOST definida        → SMTP clásico (Gmail app password,
#      Brevo, Mailgun...). Alternativa sin cuenta SendGrid.
#   3. Ninguna                    → ConsoleEmailBackend (desarrollo):
#      imprime los emails en los logs → docker compose logs -f backend
# ------------------------------------------------------------------
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")

if SENDGRID_API_KEY:
    EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"
    ANYMAIL = {
        "SENDGRID_API_KEY": SENDGRID_API_KEY,
        # Webhook secret para verificar eventos (bounce, open, click)
        # Configurable en SendGrid → Settings → Mail Settings → Event Webhook
        "WEBHOOK_SECRET": os.environ.get("SENDGRID_WEBHOOK_SECRET", ""),
    }
elif EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    # TLS (587) por defecto; SSL (465) si EMAIL_USE_SSL=True
    EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "False") == "True"
    EMAIL_USE_TLS = not EMAIL_USE_SSL and os.environ.get("EMAIL_USE_TLS", "True") == "True"
    EMAIL_TIMEOUT = 15  # No bloquear el worker indefinidamente si el SMTP no responde
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# El remitente debe estar VERIFICADO como Single Sender o Domain en SendGrid.
# Formato recomendado: "Nombre <email@dominio.com>"
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "CryptoWorld <noreply@cryptoworld.com>"
)

# URL del frontend para construir links en emails (verificación, reset)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

# ── APIs externas ──────────────────────────────────────────────────
# CoinGecko Demo (gratuito) — 30 req/min sin clave, ~500 req/min con clave.
# Definir COINGECKO_API_KEY en .env (nunca hardcodear en código fuente).
COINGECKO_API_KEY = os.environ.get("COINGECKO_API_KEY", "")

# CryptoCompare News API (gratuito con API key — registro en min-api.cryptocompare.com)
CRYPTOCOMPARE_API_KEY = os.environ.get("CRYPTOCOMPARE_API_KEY", "")

# ------------------------------------------------------------------
# Celery — Worker asíncrono para alertas de precio y tareas periódicas
# Broker y backend: Redis (servicio 'redis' en docker-compose)
# ------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# ------------------------------------------------------------------
# Caché — Redis (comparte instancia con Celery, usa DB 1 separada)
# Django 4.0+ incluye backend Redis nativo; no requiere django-redis.
# ------------------------------------------------------------------
def _redis_url_with_db(url: str, db_index: int) -> str:
    """
    Reemplazar el índice de base de datos de una URL de Redis.

    Se hace sobre la ruta parseada y no con manipulación de cadena: un
    `rstrip("/0")` elimina TODOS los caracteres finales del conjunto
    {'/', '0'}, de modo que `redis://host:6379` (formato que inyectan
    Railway y Upstash, sin sufijo de BD) acabaría en `redis://host:637`
    y la cache apuntaría a un puerto inexistente.
    """
    from urllib.parse import urlsplit, urlunsplit

    parts = urlsplit(url)
    return urlunsplit(
        (parts.scheme, parts.netloc, f"/{db_index}", parts.query, parts.fragment)
    )


CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        # DB 1 → no colisiona con la cola de Celery (DB 0)
        "LOCATION": _redis_url_with_db(REDIS_URL, 1),
        "TIMEOUT": 300,  # TTL por defecto: 5 minutos
        "KEY_PREFIX": os.environ.get("CACHE_KEY_PREFIX", "cw"),
        "OPTIONS": {
            "socket_connect_timeout": 5,
            "socket_timeout": 5,
        },
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True  # Evita CPendingDeprecationWarning en Celery 6

# Despliegues SIN worker dedicado (p. ej. Railway con un solo servicio):
# con CELERY_TASK_ALWAYS_EAGER=True las llamadas .delay() se ejecutan de
# forma sincrona en el propio proceso web. Sin esta variable y sin worker,
# las tareas se encolan en Redis y nadie las consume jamas (los emails de
# verificacion se quedan en la cola). Los errores no se propagan
# (task_eager_propagates=False por defecto): un fallo de SendGrid no
# convierte el registro de usuario en un 500.
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "False") == "True"

# Tareas periódicas (celery beat)
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Evaluar alertas activas cada 2 minutos
    "check-price-alerts": {
        "task": "core.tasks.check_price_alerts",
        "schedule": 120.0,  # segundos
    },
    # Sync rápido de precios vía Binance (1 llamada, weight=40, sin cuota CoinGecko)
    "sync-prices-quick": {
        "task": "core.tasks.sync_prices_quick",
        "schedule": 60.0,   # segundos — cada 1 min
    },
    # Sync completo vía CoinGecko (market_cap, logos, MarketDataSnapshot para sparklines)
    "sync-market-prices": {
        "task": "core.tasks.sync_market_prices",
        "schedule": 300.0,  # segundos — cada 5 min (8 640 calls/mes < 10 000 límite Demo)
    },
    # Resumen semanal del mercado para usuarios suscritos (lunes 08:00 UTC)
    "send-market-digest": {
        "task": "core.tasks.send_market_digest",
        "schedule": crontab(day_of_week=1, hour=8, minute=0),
    },
    # Retención de datos: MarketDataSnapshot crece ~144 filas/día/activo.
    # Sin purga la tabla es ilimitada; se poda de madrugada (03:15 UTC).
    "purge-old-snapshots": {
        "task": "core.tasks.purge_old_market_snapshots",
        "schedule": crontab(hour=3, minute=15),
    },
    # Purga de registros de auditoría más antiguos que el periodo legal
    # de conservación (04:15 UTC).
    "purge-audit-log": {
        "task": "core.tasks.purge_audit_log",
        "schedule": crontab(hour=4, minute=15),
    },
}

# Versión de la aplicación publicada en las sondas de salud y en el
# esquema OpenAPI. La inyecta el pipeline de despliegue.
APP_VERSION = os.environ.get("APP_VERSION", "1.139.0")

# Días de conservación (configurables por entorno).
MARKET_SNAPSHOT_RETENTION_DAYS = int(os.environ.get("MARKET_SNAPSHOT_RETENTION_DAYS", "90"))
AUDIT_LOG_RETENTION_DAYS = int(os.environ.get("AUDIT_LOG_RETENTION_DAYS", "365"))

# ------------------------------------------------------------------
# Logging estructurado
#
# En producción se emite JSON por stdout: es lo que esperan los
# agregadores (Railway, CloudWatch, Loki) y permite consultar por campo
# en lugar de por expresión regular sobre texto libre. En desarrollo se
# usa formato legible por humanos.
# ------------------------------------------------------------------
LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "DEBUG" if DEBUG else "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "config.logging_filters.RequestIDFilter"},
    },
    "formatters": {
        "console": {
            "format": "[{asctime}] {levelname} {name} [{request_id}] {message}",
            "style": "{",
        },
        "json": {
            "()": "config.logging_filters.JSONFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "console" if DEBUG else "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        # Peticiones que terminan en 4xx/5xx: siempre visibles.
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # Registro de auditoría — nunca se silencia.
        "cryptoworld.audit": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "core": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

