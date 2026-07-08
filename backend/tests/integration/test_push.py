"""
tests/integration/test_push.py — Web Push (PWA).

Verifica el guardado/borrado de suscripciones, la clave pública, la selección
de tipos críticos para push y que broadcast_notification intenta el envío
(con el envío mockeado, ya que pywebpush no está en este entorno).
"""

import pytest


class TestSubscriptionApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.post("/api/push/subscribe/").status_code == 401
        assert api_client.get("/api/push/public-key/").status_code == 401

    @pytest.mark.integration
    def test_subscribe_and_unsubscribe(self, authenticated_client, test_user):
        from core.infrastructure.persistence.models import PushSubscription

        payload = {"endpoint": "https://push.example/abc",
                   "keys": {"p256dh": "KEY", "auth": "AUTH"}}
        resp = authenticated_client.post("/api/push/subscribe/", payload, format="json")
        assert resp.status_code == 201
        sub = PushSubscription.objects.get()
        assert sub.owner_id == test_user.id and sub.p256dh == "KEY"

        # Re-suscribir el mismo endpoint no duplica (update_or_create)
        authenticated_client.post("/api/push/subscribe/", payload, format="json")
        assert PushSubscription.objects.count() == 1

        # Borrado por endpoint
        d = authenticated_client.delete("/api/push/subscribe/",
                                        {"endpoint": "https://push.example/abc"}, format="json")
        assert d.status_code == 200 and PushSubscription.objects.count() == 0

    @pytest.mark.integration
    def test_incomplete_subscription_rejected(self, authenticated_client):
        resp = authenticated_client.post("/api/push/subscribe/",
                                         {"endpoint": "https://x"}, format="json")
        assert resp.status_code == 400

    @pytest.mark.integration
    def test_public_key_reports_disabled_without_vapid(self, authenticated_client, settings):
        settings.VAPID_PUBLIC_KEY = ""
        resp = authenticated_client.get("/api/push/public-key/")
        assert resp.status_code == 200 and resp.data["enabled"] is False


class TestPushSend:

    @pytest.mark.integration
    def test_send_noop_when_not_configured(self, db, test_user):
        from core.infrastructure.push.web_push import send_to_user
        # Sin claves VAPID / sin pywebpush: no envía y no rompe.
        assert send_to_user(test_user.id, {"title": "x"}) == 0

    @pytest.mark.integration
    def test_broadcast_attempts_push_for_critical_kinds(self, db, test_user, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "core.infrastructure.push.web_push.send_to_user",
            lambda user_id, payload: calls.append((user_id, payload["kind"])) or 1,
        )
        from core.interfaces.ws import broadcast

        broadcast.broadcast_notification(test_user.id, {"kind": "live"})   # crítico → push
        broadcast.broadcast_notification(test_user.id, {"kind": "signal"})  # no crítico → sin push
        kinds = [k for _, k in calls]
        assert "live" in kinds and "signal" not in kinds
