"""
routing.py — Rutas WebSocket (análogo a urls.py para HTTP).
"""

from django.urls import re_path

from core.interfaces.ws.consumers import NotificationConsumer, PriceConsumer

websocket_urlpatterns = [
    re_path(r"^ws/prices/$", PriceConsumer.as_asgi()),
    re_path(r"^ws/notifications/$", NotificationConsumer.as_asgi()),
]
