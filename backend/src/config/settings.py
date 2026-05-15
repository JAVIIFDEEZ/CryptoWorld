"""
settings.py — Configuración central de Django.

Esta capa pertenece a la INFRAESTRUCTURA del proyecto.
Su responsabilidad es orquestar todos los adaptadores externos:
base de datos, autenticación, middleware, apps instaladas, etc.

No contiene lógica de negocio. Solo configuración del framework.
"""

from pathlib import Path
from datetime import timedelta
import os
import dj_database_url
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# ------------------------------------------------------------------
# Rutas base
# ------------------------------------------------------------------
# BASE_DIR apunta a  backend/src/
BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------
# Seguridad
# ------------------------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-this-in-production-key-12345"
)

DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost 127.0.0.1").split(" ")

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

    # Apps del proyecto (capa interfaces expone los endpoints)
    "core",
]

# ------------------------------------------------------------------
# Middleware
# ------------------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",          # Debe ir primero
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
        "DIRS": [],
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
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

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
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
}

# ------------------------------------------------------------------
# SimpleJWT — Configuración de tokens
# ------------------------------------------------------------------
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
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
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173 http://127.0.0.1:5173"
).split(" ")

CORS_ALLOW_CREDENTIALS = True

# ------------------------------------------------------------------
# Email — Console backend en desarrollo, SMTP en producción
# Para producción: define EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
#   + EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, EMAIL_USE_TLS
# ------------------------------------------------------------------
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",  # Imprime en logs Docker
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "noreply@cryptoworld.com")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

# URL del frontend para construir links en emails
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

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True  # Evita CPendingDeprecationWarning en Celery 6

# Tareas periódicas (celery beat)
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    # Evaluar alertas activas cada 2 minutos
    "check-price-alerts": {
        "task": "core.tasks.check_price_alerts",
        "schedule": 120.0,  # segundos
    },
    # Sincronizar precios de mercado cada 10 minutos
    "sync-market-prices": {
        "task": "core.tasks.sync_market_prices",
        "schedule": 600.0,  # segundos
    },
}

