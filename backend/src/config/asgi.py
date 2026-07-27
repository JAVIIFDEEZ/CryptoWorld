"""
asgi.py — Punto de entrada ASGI (HTTP + WebSocket).

Sustituye al WSGI para servir también WebSockets vía Channels. En producción se
arranca con un servidor ASGI, p. ej.:
    daphne -b 0.0.0.0 -p 8000 config.asgi:application
    uvicorn config.asgi:application --host 0.0.0.0 --port 8000

El handler HTTP se inicializa ANTES de importar los consumers (requisito de
Channels para que las apps de Django estén cargadas).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from core.interfaces.ws.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
