"""
tests/integration/test_websocket_prices.py — Stream de precios por WebSocket.

Verifica el helper de broadcast y un round-trip real del consumer con la capa
InMemory: conectar → recibir el broadcast emitido al grupo. Se usa asyncio.run
para no depender de plugins async. No se parchea get_channel_layer (channels lo
enlaza en import y filtra entre tests): se usa la capa InMemory de verdad.
"""

import asyncio

import pytest
from channels import layers


def _use_inmemory(settings):
    """Configura la capa de canales InMemory (en proceso, sin Redis) y limpia la
    caché para que channels la relea."""
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    layers.channel_layers.backends = {}


class TestBroadcastHelper:

    @pytest.mark.unit
    def test_broadcast_empty_is_noop(self):
        from core.interfaces.ws.broadcast import broadcast_price_update
        assert broadcast_price_update([]) is False

    @pytest.mark.unit
    def test_broadcast_sends_to_layer(self, settings):
        _use_inmemory(settings)
        from core.interfaces.ws.broadcast import broadcast_price_update
        try:
            ok = broadcast_price_update([{"symbol": "BTC", "price": 1.0, "change": 2.0}])
            assert ok is True
        finally:
            layers.channel_layers.backends = {}


class TestPriceConsumer:

    @pytest.mark.unit
    def test_consumer_receives_broadcast(self, settings):
        _use_inmemory(settings)

        async def _run():
            from channels.layers import get_channel_layer
            from channels.testing import WebsocketCommunicator
            from core.interfaces.ws.consumers import PRICE_GROUP, PriceConsumer

            comm = WebsocketCommunicator(PriceConsumer.as_asgi(), "/ws/prices/")
            connected, _ = await comm.connect()
            assert connected
            hello = await comm.receive_json_from()
            assert hello["type"] == "connected"

            await get_channel_layer().group_send(
                PRICE_GROUP,
                {"type": "price_update", "data": [{"symbol": "ETH", "price": 1600.0, "change": 1.2}]},
            )
            msg = await comm.receive_json_from()
            assert msg["type"] == "price_update"
            assert msg["data"][0]["symbol"] == "ETH"

            # El ping mantiene viva la conexión (responde pong).
            await comm.send_json_to({"type": "ping"})
            pong = await comm.receive_json_from()
            assert pong["type"] == "pong"

            await comm.disconnect()

        try:
            asyncio.run(_run())
        finally:
            layers.channel_layers.backends = {}
