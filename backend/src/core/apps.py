"""
apps.py — Configuración de la app Django 'core'.

Django necesita este archivo para reconocer 'core' como una aplicación
instalable. No contiene lógica de negocio.
"""

from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "CryptoWorld Core"
