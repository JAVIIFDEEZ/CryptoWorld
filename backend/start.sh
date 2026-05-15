#!/bin/bash
set -e

cd src
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --workers 3 --timeout 120 --bind 0.0.0.0:${PORT:-8000}
