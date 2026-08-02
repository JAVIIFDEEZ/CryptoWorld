# Dockerfile — Backend Django
#
# Imagen de producción:
#   - Multi-stage: las herramientas de compilación no llegan a la imagen final.
#   - Proceso sin privilegios (usuario `app`): un fallo en la aplicación no
#     concede root dentro del contenedor.
#   - Gunicorn como servidor WSGI. El `runserver` de Django es un servidor de
#     desarrollo —monohilo, sin límites y con depurador— y no debe ser el
#     comando por defecto de una imagen que también se publica. Para
#     desarrollo local, docker-compose.yml sobrescribe el comando.
#   - HEALTHCHECK contra la sonda de vitalidad, que no toca dependencias.
#
# Uso:
#   docker build -t cryptoworld-backend .
#   docker run -p 8000:8000 --env-file .env cryptoworld-backend

# ── Stage 1: dependencias ──────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Cabeceras de compilación solo en esta etapa (psycopg2, numpy…).
RUN apt-get update \
 && apt-get install --no-install-recommends -y build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix=/install --timeout=300 --retries=5 -r requirements.txt

# ── Stage 2: runtime ───────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# `curl` es la única herramienta extra: la usa el HEALTHCHECK.
RUN apt-get update \
 && apt-get install --no-install-recommends -y curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --shell /usr/sbin/nologin --uid 10001 app

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=app:app . .

# Directorio de estáticos escribible por el usuario sin privilegios.
RUN mkdir -p /app/src/staticfiles && chown -R app:app /app/src/staticfiles

USER app

EXPOSE 8000

# La sonda de vitalidad no consulta base de datos ni Redis: comprueba el
# proceso web, que es lo único que un reinicio del contenedor arregla.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health/live/ || exit 1

CMD ["gunicorn", "config.wsgi:application", \
     "--chdir", "/app/src", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
