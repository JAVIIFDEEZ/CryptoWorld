"""
tests/integration/test_notifications.py — Centro de notificaciones in-app.

Verifica que el feed agrega los distintos eventos del usuario (señales,
ballenas, predicciones resueltas, alertas de precio, kill-switch de ejecución
real), el contador de no leídas según el sello de visto, el aislamiento por
usuario y los endpoints.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.application.use_cases.notifications import (
    MarkNotificationsSeenUseCase, NotificationsFeedUseCase,
)


@pytest.fixture
def events(db, test_user):
    """Crea un evento de cada tipo para el usuario de prueba."""
    from core.infrastructure.persistence.models import (
        AddressAlert, CryptoAsset, PaperTradingAccount, PredictionRecord,
        PriceAlert, StrategyDefinition, StrategySignalEvent, WatchedAddress,
    )
    asset = CryptoAsset.objects.create(symbol="BTC", name="Bitcoin")
    strat = StrategyDefinition.objects.create(
        asset=asset, name="RSI reversal", spec={"x": 1}, spec_hash="h", interval="1d",
    )
    StrategySignalEvent.objects.create(strategy=strat, owner=test_user, signal="BUY", price=100.0)

    watch = WatchedAddress.objects.create(
        owner=test_user, chain="ethereum", address="0x" + "a" * 40, native_symbol="ETH",
    )
    AddressAlert.objects.create(
        watched=watch, owner=test_user, direction="increase",
        balance_before=10.0, balance_after=13.0, delta=3.0, delta_pct=30.0,
    )

    PredictionRecord.objects.create(
        owner=test_user, asset_symbol="BTC", interval="1d", horizon=5,
        predicted="ALCISTA", prob_up=0.6, confidence=0.6, price_at_prediction=100.0,
        status="correct", resolve_at=timezone.now(), resolved_at=timezone.now(),
        actual_return_pct=4.2,
    )

    PriceAlert.objects.create(
        user=test_user, asset=asset, condition="ABOVE", threshold_price="50000",
        is_triggered=True, triggered_at=timezone.now(),
    )

    PaperTradingAccount.objects.create(
        strategy=strat, owner=test_user, asset_symbol="BTC", interval="1d",
        live_error="Ejecución real desactivada: fondos insuficientes.",
        live_disabled_at=timezone.now(),
    )
    return test_user


class TestFeed:

    @pytest.mark.integration
    def test_aggregates_all_event_kinds(self, events):
        out = NotificationsFeedUseCase().execute(owner=events)
        kinds = {it["kind"] for it in out["items"]}
        assert kinds == {"signal", "whale", "prediction", "price", "live"}
        assert out["count"] == 5

    @pytest.mark.integration
    def test_unread_all_when_never_seen(self, events):
        out = NotificationsFeedUseCase().execute(owner=events)
        assert out["unread"] == 5
        assert all(it["unread"] for it in out["items"])

    @pytest.mark.integration
    def test_kill_switch_item_carries_reason_and_link(self, events):
        out = NotificationsFeedUseCase().execute(owner=events)
        item = next(it for it in out["items"] if it["kind"] == "live")
        assert "BTC" in item["title"]
        assert "fondos insuficientes" in item["body"].lower()
        assert item["link"] == "/strategies"

    @pytest.mark.integration
    def test_kill_switch_item_disappears_on_reenable(self, events):
        from core.infrastructure.persistence.models import PaperTradingAccount
        PaperTradingAccount.objects.filter(owner=events).update(
            live_error="", live_disabled_at=None,
        )
        out = NotificationsFeedUseCase().execute(owner=events)
        assert not any(it["kind"] == "live" for it in out["items"])
        assert out["unread"] == 4

    @pytest.mark.integration
    def test_unread_zero_when_seen_in_future(self, events):
        events.notifications_seen_at = timezone.now() + timedelta(hours=1)
        events.save(update_fields=["notifications_seen_at"])
        out = NotificationsFeedUseCase().execute(owner=events)
        assert out["unread"] == 0
        assert not any(it["unread"] for it in out["items"])

    @pytest.mark.integration
    def test_feed_sorted_desc_by_time(self, events):
        out = NotificationsFeedUseCase().execute(owner=events)
        times = [it["created_at"] for it in out["items"]]
        assert times == sorted(times, reverse=True)

    @pytest.mark.integration
    def test_isolated_per_user(self, events, db):
        from core.infrastructure.persistence.models import User
        other = User.objects.create_user(email="o@e.com", username="other", password="x")
        out = NotificationsFeedUseCase().execute(owner=other)
        assert out["count"] == 0 and out["unread"] == 0


class TestMarkSeen:

    @pytest.mark.integration
    def test_mark_seen_sets_timestamp_and_clears_unread(self, events):
        before = NotificationsFeedUseCase().execute(owner=events)
        assert before["unread"] == 5
        MarkNotificationsSeenUseCase().execute(owner=events)
        events.refresh_from_db()
        assert events.notifications_seen_at is not None
        after = NotificationsFeedUseCase().execute(owner=events)
        assert after["unread"] == 0


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/notifications/").status_code == 401
        assert api_client.post("/api/notifications/seen/").status_code == 401

    @pytest.mark.integration
    def test_feed_and_seen_endpoints(self, authenticated_client):
        resp = authenticated_client.get("/api/notifications/")
        assert resp.status_code == 200
        assert set(resp.data) >= {"unread", "count", "items"}

        seen = authenticated_client.post("/api/notifications/seen/")
        assert seen.status_code == 200 and seen.data["unread"] == 0
