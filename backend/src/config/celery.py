"""
config/celery.py — Configuración de Celery para tareas asíncronas.

Celery se usa para evaluar alertas de precio en background cada minuto.

Broker: Redis (configurado en docker-compose como servicio 'redis')
Backend: Redis (para almacenar resultados de tareas)

Inicio manual (fuera de Docker):
    celery -A config worker --beat --loglevel=info

En Docker, el servicio 'celery-worker' arranca con este comando.
"""

import os

from celery import Celery

# Indicar a Celery qué módulo de settings usar
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("cryptoworld")

# Leer configuración desde settings.py bajo el namespace CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-descubrir tareas en todos los módulos tasks.py de las apps instaladas
app.autodiscover_tasks()
