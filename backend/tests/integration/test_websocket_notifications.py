"""
tests/integration/test_websocket_notifications.py — Canal personal de
notificaciones por WebSocket.

Verifica la autenticación por JWT (?token=), el aislamiento por usuario (cada
cliente solo recibe los broadcasts de SU grupo), el helper de emisión y que el
kill-switch de la ejecución real emite el aviso. Mismo patrón que el test de
precios: capa InMemory real + asyncio.run, sin parchear get_channel_layer.
"""

import asyncio

import pytest
from channels import layers


def _use_inmemory(settings):
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    layers.channel_layers.backends = {}


def _token_for(user) -> str:
    from rest_framework_simplejwt.tokens import AccessToken
    return str(AccessToken.for_user(user))


class TestBroadcastHelper:

    @pytest.mark.unit
    def test_no_user_is_noop(self):
        from core.interfaces.ws.broadcast import broadcast_notification
        assert broadcast_notification(None, {"kind": "live"}) is False

    @pytest.mark.unit
    def test_broadcast_sends_to_layer(self, settings):
        _use_inmemory(settings)
        from core.interfaces.ws.broadcast import broadcast_notification
        try:
            assert broadcast_notification(42, {"kind": "live"}) is True
        finally:
            layers.channel_layers.backends = {}


class TestNotificationConsumer:

    @pytest.mark.integration
    def test_rejects_without_valid_token(self, settings, db):
        _use_inmemory(settings)

        async def _run():
            from channels.testing import WebsocketCommunicator
            from core.interfaces.ws.consumers import NotificationConsumer

            for qs in ("", "?token=basura"):
                comm = WebsocketCommunicator(NotificationConsumer.as_asgi(), f"/ws/notifications/{qs}")
                connected, _ = await comm.connect()
                assert not connected
                await comm.disconnect()

        try:
            asyncio.run(_run())
        finally:
            layers.channel_layers.backends = {}

    @pytest.mark.integration
    def test_receives_only_own_broadcasts(self, settings, test_user):
        _use_inmemory(settings)
        token = _token_for(test_user)

        async def _run():
            from channels.layers import get_channel_layer
            from channels.testing import WebsocketCommunicator
            from core.interfaces.ws.consumers import NotificationConsumer, notif_group

            comm = WebsocketCommunicator(
                NotificationConsumer.as_asgi(), f"/ws/notifications/?token={token}",
            )
            connected, _ = await comm.connect()
            assert connected
            hello = await comm.receive_json_from()
            assert hello["type"] == "connected"

            layer = get_channel_layer()
            # Aviso de OTRO usuario: no debe llegar.
            await layer.group_send(notif_group(test_user.id + 999),
                                   {"type": "notify", "data": {"kind": "live"}})
            assert await comm.receive_nothing(timeout=0.2)

            # Aviso propio: llega con su kind.
            await layer.group_send(notif_group(test_user.id),
                                   {"type": "notify", "data": {"kind": "live"}})
            msg = await comm.receive_json_from()
            assert msg == {"type": "notification", "data": {"kind": "live"}}

            # Ping de keep-alive.
            await comm.send_json_to({"type": "ping"})
            assert (await comm.receive_json_from())["type"] == "pong"

            await comm.disconnect()

        try:
            asyncio.run(_run())
        finally:
            layers.channel_layers.backends = {}


class TestKillSwitchEmitsNotification:

    @pytest.mark.integration
    def test_broker_error_broadcasts_live_kind(self, db, test_user, monkeypatch):
        """El kill-switch (BrokerError al espejar) emite el aviso al dueño."""
        from core.application.use_cases.paper_trading import _apply_signal, _mirror_live
        from core.infrastructure.external_apis.ccxt_broker import BrokerError
        from core.infrastructure.persistence.models import (
            CryptoAsset, ExchangeConnection, PaperTradingAccount, StrategyDefinition,
        )
        from core.infrastructure.security.crypto import encrypt_secret

        asset = CryptoAsset.objects.create(symbol="BTC", name="Bitcoin")
        strat = StrategyDefinition.objects.create(
            asset=asset, name="s", spec={"x": 1}, spec_hash="h", interval="1d",
        )
        conn = ExchangeConnection.objects.create(
            owner=test_user, exchange="binance",
            api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"),
        )
        acc = PaperTradingAccount.objects.create(
            strategy=strat, owner=test_user, asset_symbol="BTC", interval="1d",
            initial_capital=10000.0, cash=10000.0,
            live_connection=conn, live_enabled=True, live_cap_usd=100.0,
        )

        sent = []
        monkeypatch.setattr(
            "core.interfaces.ws.broadcast.broadcast_notification",
            lambda user_id, data: sent.append((user_id, data)) or True,
        )

        class _Boom:
            def create_order(self, *a, **kw):
                raise BrokerError("Fondos insuficientes.")

        trade = _apply_signal(acc, "BUY", price=100.0)
        _mirror_live(acc, trade, 100.0, broker_factory=lambda c: _Boom())
        assert acc.live_enabled is False
        assert sent == [(test_user.id, {"kind": "live"})]
