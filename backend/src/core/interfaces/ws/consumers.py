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
