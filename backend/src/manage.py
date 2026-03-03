#!/usr/bin/env python
"""
manage.py — Utilidad de línea de comandos de Django.

Punto de entrada para comandos de gestión:
  python manage.py runserver
  python manage.py makemigrations
  python manage.py migrate
  python manage.py createsuperuser
  etc.
"""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se puede importar Django. ¿Está instalado y en el PYTHONPATH?\n"
            "¿Olvidaste activar el entorno virtual?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
