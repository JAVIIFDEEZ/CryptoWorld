"""
consumers.py — Consumers WebSocket (capa interfaces).

PriceConsumer empuja actualizaciones de precios en tiempo real a los clientes
suscritos, sustituyendo el polling del ticker/mercado. Es público (no requiere
autenticación): los precios no son datos sensibles. Cada cliente se une a un
único grupo y recibe los broadcasts que emite el sync de precios.
"""

import logging

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)

PRICE_GROUP = "prices"


class PriceConsumer(AsyncJsonWebsocketConsumer):
    """Stream de precios en vivo. Canal de solo-lectura (servidor → cliente)."""

    async def connect(self):
        await self.channel_layer.group_add(PRICE_GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected"})

    async def disconnect(self, code):
        await self.channel_layer.group_discard(PRICE_GROUP, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Canal de solo-lectura: respondemos a un ping para mantener viva la conexión.
        if isinstance(content, dict) and content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    # Handler del broadcast: el `type` del evento ("price_update") se traduce a
    # este método por convención de Channels.
    async def price_update(self, event):
        await self.send_json({"type": "price_update", "data": event["data"]})


# ── Notificaciones personales ────────────────────────────────────────

def notif_group(user_id: int) -> str:
    """Nombre del grupo personal de notificaciones de un usuario."""
    return f"notif_user_{user_id}"


def _user_id_from_token(token: str) -> "int | None":
    """Valida un access token JWT (firma + expiración; sin tocar la BD) y
    devuelve el id del usuario, o None si el token no es válido."""
    if not token:
        return None
    try:
        from rest_framework_simplejwt.tokens import AccessToken
        return int(AccessToken(token)["user_id"])
    except Exception:  # noqa: BLE001 — token inválido/expirado → sin acceso
        return None


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """Stream personal de notificaciones (servidor → cliente).

    A diferencia del de precios, este canal es POR USUARIO y exige JWT
    (?token=<access>): cada cliente solo se une a su propio grupo. Los avisos
    son ligeros ({"kind": ...}): al recibirlos, la campana re-consulta el feed
    HTTP, que es la única fuente de verdad del contenido.
    """

    async def connect(self):
        from urllib.parse import parse_qs

        qs = parse_qs((self.scope.get("query_string") or b"").decode())
        user_id = _user_id_from_token((qs.get("token") or [""])[0])
        if user_id is None:
            await self.close(code=4401)  # no autorizado
            return
        self._group = notif_group(user_id)
        await self.channel_layer.group_add(self._group, self.channel_name)
        await self.accept()
        await self.send_json({"type": "connected"})

    async def disconnect(self, code):
        group = getattr(self, "_group", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive_json(self, content, **kwargs):
        # Canal de solo-lectura: respondemos a un ping para mantener viva la conexión.
        if isinstance(content, dict) and content.get("type") == "ping":
            await self.send_json({"type": "pong"})

    async def notify(self, event):
        await self.send_json({"type": "notification", "data": event.get("data") or {}})
