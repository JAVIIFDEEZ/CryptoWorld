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
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    """Lee un booleano del entorno aceptando True/1/yes/on (insensible a mayúsculas).

    El proyecto usaba comparaciones `== "True"` dispersas: cualquier valor
    legítimo pero distinto ("true", "1") desactivaba silenciosamente la opción.
    En un flag de seguridad ese fallo es silencioso y grave, así que la lectura
    se centraliza aquí.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")


def _env_list(name: str, default: str = "") -> list[str]:
    """Lista separada por comas y/o espacios, sin elementos vacíos."""
    raw = os.environ.get(name, default).strip()
    return [item for item in re.split(r"[,\s]+", raw) if item]


# ------------------------------------------------------------------
# Rutas base
# ------------------------------------------------------------------
# BASE_DIR apunta a  backend/src/
BASE_DIR = Path(__file__).resolve().parent.parent

# ------------------------------------------------------------------
# Seguridad
# ------------------------------------------------------------------
INSECURE_SECRET_KEY = "django-insecure-change-this-in-production-key-12345"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", INSECURE_SECRET_KEY)

DEBUG = _env_bool("DJANGO_DEBUG", True)

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost 127.0.0.1")

# ── Fail-fast de despliegue ───────────────────────────────────────
# Arrancar en producción con la clave de ejemplo permite falsificar tokens JWT
# y descifrar las credenciales de exchange de todos los usuarios. Un despliegue
# mal configurado debe abortar en el arranque, no servir tráfico inseguro.
if not DEBUG:
    if SECRET_KEY == INSECURE_SECRET_KEY or SECRET_KEY.startswith("django-insecure-"):
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY tiene el valor de ejemplo. Genera una clave "
            "aleatoria de 50+ caracteres antes de desplegar con DJANGO_DEBUG=False."
        )
    if len(SECRET_KEY) < 32:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY es demasiado corta (mínimo 32 caracteres)."
        )
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "DJANGO_ALLOWED_HOSTS debe listar los dominios reales en producción "
            "(nunca '*': habilita ataques de cabecera Host)."
        )

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
    # Techo global: hasta ahora solo los endpoints con ScopedRateThrottle
    # declarado estaban limitados, así que los +100 endpoints restantes (varios
    # de ellos costosos: backtests, forense on-chain) eran ilimitados. Estas
    # clases ponen un suelo de protección a TODA la API; los scopes específicos
    # siguen aplicándose encima donde están declarados.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    # Rate limiting por IP en endpoints sensibles de auth (ScopedRateThrottle
    # declarado view a view). El contador vive en la cache Redis.
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.environ.get("THROTTLE_ANON", "120/min"),
        "user": os.environ.get("THROTTLE_USER", "600/min"),
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
        # Órdenes contra el exchange REAL del usuario: el límite más estricto
        # de la API. Contiene tanto el error humano (doble clic, bucle en un
        # script) como el abuso de una sesión robada.
        "trading_order": os.environ.get("THROTTLE_TRADING_ORDER", "20/min"),
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
CORS_ALLOWED_ORIGINS = _env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173 http://127.0.0.1:5173"
)

CORS_ALLOW_CREDENTIALS = True

# ------------------------------------------------------------------
# Endurecimiento HTTP
#
# Los valores que no dependen del transporte se aplican SIEMPRE (también en
# desarrollo: así lo que se prueba es lo que se despliega). Los que exigen
# HTTPS se activan solo con DEBUG=False, porque en local no hay TLS y
# romperían el flujo de login.
# ------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True          # Sin MIME sniffing
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"                    # La API nunca debe embeberse
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False                # El frontend necesita leer el token

# Orígenes de confianza para CSRF (formulario admin y vistas con sesión).
# Por defecto se derivan de CORS_ALLOWED_ORIGINS: son el mismo conjunto de
# frontends legítimos y evita el desajuste típico entre ambas listas.
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS") or [
    origin for origin in CORS_ALLOWED_ORIGINS if origin.startswith(("http://", "https://"))
]

# Límites de cuerpo de petición: contienen ataques de agotamiento de memoria
# en los endpoints que aceptan JSON (specs de estrategia, listas de activos).
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DATA_UPLOAD_MAX_MEMORY_SIZE", 2 * 1024 * 1024))
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

if not DEBUG:
    # Detrás de Nginx/Railway el TLS termina en el proxy: sin esta cabecera
    # Django cree que la petición es HTTP y entra en bucle de redirección.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = _env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", 31536000))  # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

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
    # Evaluar alertas cuantitativas (multi-métrica, disparo por flanco) cada 3 min
    "evaluate-quant-alerts": {
        "task": "core.tasks.evaluate_quant_alerts",
        "schedule": 180.0,  # segundos
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
    # Resumen diario de riesgo de cartera (días laborables 07:00 UTC)
    "send-risk-digest": {
        "task": "core.tasks.send_risk_digest",
        "schedule": crontab(day_of_week="1-5", hour=7, minute=0),
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
    # Precalentar la caché de predicción ML de los activos top (cada 10 min)
    "warm-ml-predictions": {
        "task": "core.tasks.warm_ml_predictions",
        "schedule": 600.0,   # segundos — la caché de predicción dura 15 min
    },
    # Mantener al día el almacén histórico OHLCV propio (cada 30 min)
    "sync-ohlcv-history": {
        "task": "core.tasks.sync_ohlcv_history",
        "schedule": 1800.0,  # segundos — solo persiste velas cerradas
    },
    # Histórico on-chain (cada 10 min). Sin esta tarea el almacén solo se llena
    # cuando alguien abre el panel: la historia dependería del tráfico y no del
    # tiempo, y las horas en que nadie mira —justo cuando el gas es más barato—
    # quedarían en blanco.
    "sync-chain-metrics": {
        "task": "core.tasks.sync_chain_metrics",
        "schedule": 600.0,
    },
    # Poda del histórico on-chain (semanal): un almacén que solo crece acaba
    # siendo un problema operativo.
    "prune-chain-metrics": {
        "task": "core.tasks.prune_chain_metrics",
        "schedule": 604800.0,
    },
    # Histórico de financiación de perpetuos (cada 6 h: se liquida cada 8 h).
    # Sin él, todo backtest de perpetuo sobreestima el rendimiento, y más
    # cuanto más aguante abierta la posición.
    "sync-funding-history": {
        "task": "core.tasks.sync_funding_history",
        "schedule": 21600.0,
    },
    # Altas y bajas del universo (diario): la condición para reconstruirlo
    # point-in-time y no medir solo sobre los que sobrevivieron.
    "sync-asset-lifecycle": {
        "task": "core.tasks.sync_asset_lifecycle",
        "schedule": 86400.0,
    },
    # Resolver lecturas de confluencia vencidas (aprendizaje de pesos, 30 min)
    "resolve-confluence-snapshots": {
        "task": "core.tasks.resolve_confluence_snapshots",
        "schedule": 1800.0,
    },
    # Evaluar la confluencia de los activos relevantes (aprendizaje + eventos)
    "evaluate-confluence": {
        "task": "core.tasks.evaluate_confluence",
        "schedule": 1800.0,
    },
    # OMS: reconciliar posición esperada ↔ balance real del exchange (cada hora)
    "reconcile-live-positions": {
        "task": "core.tasks.reconcile_live_positions",
        "schedule": 3600.0,
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
    # Establo nocturno: generar campeonas para activos sin estrategia validada
    # fresca (watchlists + top por capitalización), 2 por noche (diaria 04:00 UTC)
    "fill-strategy-stable": {
        "task": "core.tasks.fill_strategy_stable",
        "schedule": crontab(hour=4, minute=0),
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



# ------------------------------------------------------------------
# Web Push (PWA) — notificaciones con la app cerrada.
# Genera el par VAPID una vez y ponlo en el entorno. Vacío = push desactivado
# (el WebSocket y el centro in-app siguen funcionando).
# ------------------------------------------------------------------
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CLAIM_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "admin@cryptoworld.app")

# ------------------------------------------------------------------
# Cifrado de credenciales de usuario (claves API de exchanges)
#
# Se separa de SECRET_KEY a propósito: SECRET_KEY firma tokens y cookies y se
# rota con relativa frecuencia; rotarla NO debe invalidar las credenciales de
# exchange de todos los usuarios. Además, un secreto de firma filtrado no debe
# implicar automáticamente el descifrado de las claves API.
#
# Formato: lista separada por comas. La PRIMERA clave cifra; todas descifran.
# Eso permite rotar sin downtime: se añade la nueva delante, y las credenciales
# se recifran de forma transparente al siguiente guardado.
# Vacío → se deriva de SECRET_KEY (compatibilidad con lo ya guardado).
# ------------------------------------------------------------------
CREDENTIALS_ENCRYPTION_KEYS = _env_list("CREDENTIALS_ENCRYPTION_KEYS")

# ------------------------------------------------------------------
# Logging
#
# Sin configuración explícita, Django solo emite WARNING+ del propio framework
# y los logger.info de los casos de uso se pierden: no hay trazabilidad de qué
# hizo el sistema con el dinero del usuario. Aquí se define:
#   · consola con formato legible (o JSON en producción, para el agregador)
#   · `core.audit`, canal separado para eventos auditables (órdenes reales,
#     cambios de política de riesgo, accesos administrativos)
# ------------------------------------------------------------------
LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "DEBUG" if DEBUG else "INFO").upper()
LOG_FORMAT = os.environ.get("DJANGO_LOG_FORMAT", "plain" if DEBUG else "json").lower()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {
            "format": "{asctime} {levelname:<8} {name}: {message}",
            "style": "{",
        },
        "json": {
            "()": "config.logging.JsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if LOG_FORMAT == "json" else "plain",
        },
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {
        # Código propio: el nivel lo marca el entorno.
        "core": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # Canal de auditoría: siempre INFO, nunca se silencia. Es el registro
        # de cumplimiento (quién ordenó qué, cuándo y con qué resultado).
        "core.audit": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Peticiones 4xx/5xx: en producción interesan como señal operativa.
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        # El SQL de Django en DEBUG inunda la salida; se sube el umbral.
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "celery": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}
