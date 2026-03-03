"""
wsgi.py — Punto de entrada WSGI para servidores de producción.

Este módulo es el adaptador entre el servidor HTTP (Gunicorn, uWSGI, etc.)
y la aplicación Django. Pertenece a la capa de infraestructura porque
es una preocupación del despliegue, no del dominio.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
