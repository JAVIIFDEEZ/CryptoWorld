# Cargar Celery al importar el paquete config para que el decorador @shared_task funcione.
from .celery import app as celery_app

__all__ = ("celery_app",)
