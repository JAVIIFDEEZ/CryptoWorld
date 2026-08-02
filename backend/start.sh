#!/bin/bash
set -e

cd src

# ── Rol del servicio ────────────────────────────────────────────────
# railway.json fija "bash start.sh" como start command para TODOS los
# servicios del repo (config-as-code bloquea el campo del panel).
# El rol de cada servicio se decide con la variable SERVICE_ROLE:
#   (vacia) / web -> gunicorn (migraciones + estaticos incluidos)
#   worker        -> celery worker (consume la cola de tareas)
#   beat          -> celery beat (scheduler de tareas periodicas)

case "${SERVICE_ROLE:-web}" in
  worker)
    exec celery -A config worker --loglevel=info --pool=solo
    ;;
  beat)
    exec celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
    ;;
esac

# ── Rol web (por defecto) ───────────────────────────────────────────
# Las migraciones y collectstatic solo deben ejecutarse una vez, en el
# servicio web; worker y beat arrancan directo arriba sin pasar por aqui.
python manage.py migrate --noinput
python manage.py collectstatic --noinput

# One-time admin promotion: set PROMOTE_ADMIN_USERNAME=<username> in Railway vars
if [ -n "${PROMOTE_ADMIN_USERNAME}" ]; then
    python manage.py shell -c "
import os
username = os.environ.get('PROMOTE_ADMIN_USERNAME', '')
from core.infrastructure.persistence.models import User
try:
    u = User.objects.get(username=username)
    u.is_staff = True
    u.is_superuser = True
    u.is_email_verified = True
    u.save()
    print('Promoted', username, 'to admin OK')
except User.DoesNotExist:
    print('User not found:', username)
" || true
fi

exec gunicorn config.asgi:application --worker-class uvicorn.workers.UvicornWorker --workers 3 --timeout 120 --bind 0.0.0.0:${PORT:-8000}
