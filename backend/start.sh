#!/bin/bash
set -e

cd src
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

exec gunicorn config.wsgi:application --workers 3 --timeout 120 --bind 0.0.0.0:${PORT:-8000}
