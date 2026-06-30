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
import re
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

ALLOWED_HOSTS = re.split(r'[,\s]+', os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost 127.0.0.1").strip())

# ------------------------------------------------------------------
# Aplicaciones instaladas
# ------------------------------------------------------------------
INSTALLED_APPS = [
    # Daphne (servidor ASGI) debe ir el primero para que `runserver` sirva
    # WebSockets en desarrollo (Channels). En producción se usa daphne/uvicorn.
    "daphne",

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
    "channels",                                # WebSockets / ASGI (tiempo real)

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
# Agrupa miles con el separador del locale (es-ES: "64.307,35") en las
# plantillas server-side. Da formato numérico consistente a las landings SEO.
USE_THOUSAND_SEPARATOR = True

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
    # Rate limiting por IP en endpoints sensibles de auth (ScopedRateThrottle
    # declarado view a view). El contador vive en la cache Redis.
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": "10/min",
        "auth_register": "10/hour",
        "auth_password_reset": "5/hour",
        "auth_resend_verification": "5/hour",
        "auth_change_email": "5/hour",
        "auth_2fa": "10/min",
        # Endpoints costosos (lanzan cientos de backtests en Celery): se limitan
        # por usuario/IP para proteger el worker. El contador vive en Redis.
        "robust_backtest": "30/hour",
        "strategy_generate": "10/hour",
        "strategy_robustness": "40/hour",
    },
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
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL.rstrip("/0") + "/1",  # DB 1 → no colisiona con Celery (DB 0)
        "TIMEOUT": 300,  # TTL por defecto: 5 minutos
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

# ------------------------------------------------------------------
# Channels / WebSockets (tiempo real)
# ------------------------------------------------------------------
# La capa de canales usa Redis (DB 2, sin colisión con Celery /0 ni la caché /1).
# En producción se sirve con un servidor ASGI (daphne/uvicorn) apuntando a
# config.asgi:application. Los tests sustituyen esta capa por InMemory.
ASGI_APPLICATION = "config.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [REDIS_URL.rstrip("/0") + "/2"]},
    }
}

# Despliegues SIN worker dedicado (p. ej. Railway con un solo servicio):
# con CELERY_TASK_ALWAYS_EAGER=True las llamadas .delay() se ejecutan de
# forma sincrona en el propio proceso web. Sin esta variable y sin worker,
# las tareas se encolan en Redis y nadie las consume jamas (los emails de
# verificacion se quedan en la cola). Los errores no se propagan
# (task_eager_propagates=False por defecto): un fallo de SendGrid no
# convierte el registro de usuario en un 500.
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "False") == "True"

# Estado STARTED visible al hacer polling de un job (suite de robustez).
CELERY_TASK_TRACK_STARTED = True
# En modo eager (tests) guarda el resultado en el backend para que
# AsyncResult(job_id) lo recupere igual que con un worker real.
CELERY_TASK_STORE_EAGER_RESULT = True

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
    # Señales en vivo de estrategias generadas monitorizadas (cada 15 min)
    "evaluate-monitored-strategies": {
        "task": "core.tasks.evaluate_monitored_strategies",
        "schedule": 900.0,  # segundos — cada 15 min
    },
    # Verificar predicciones ML cuyo horizonte ha vencido (cada 30 min)
    "resolve-predictions": {
        "task": "core.tasks.resolve_predictions",
        "schedule": 1800.0,  # segundos — cada 30 min
    },
    # Ejecutar señales de las carteras de paper trading activas (cada 15 min)
    "evaluate-paper-trading": {
        "task": "core.tasks.evaluate_paper_trading",
        "schedule": 900.0,  # segundos — cada 15 min
    },
    # Reoptimizar las estrategias de los activos seguidos (lunes 03:00 UTC)
    "reoptimize-strategies": {
        "task": "core.tasks.reoptimize_strategies",
        "schedule": crontab(day_of_week=1, hour=3, minute=0),
    },
    # Vigilar direcciones on-chain de la watchlist y alertar movimientos (cada 30 min)
    "monitor-watched-addresses": {
        "task": "core.tasks.monitor_watched_addresses",
        "schedule": 1800.0,  # segundos — cada 30 min
    },
    # Persistir grandes movimientos on-chain para el indicador de presión (cada 15 min)
    "scan-whale-movements": {
        "task": "core.tasks.scan_whale_movements",
        "schedule": 900.0,  # segundos — cada 15 min
    },
}

