"""
tests/integration/test_alerts_and_trades.py — Alertas y operaciones.

Alertas y trades son las dos funciones donde el usuario introduce datos
propios que el sistema conserva y evalúa después. Los tests cubren el
ciclo completo de cada una, el aislamiento entre usuarios y el disparo de
alertas por el worker, incluida la retención de datos.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.infrastructure.persistence.models import (
    AuditLog,
    CryptoAsset,
    MarketDataSnapshot,
    PriceAlert,
    TradeHistory,
)


@pytest.fixture
def btc(db):
    return CryptoAsset.objects.create(
        symbol="BTC", name="Bitcoin", current_price=Decimal("50000.00000000")
    )


# ── Alertas de precio ──────────────────────────────────────────────


@pytest.mark.integration
class TestPriceAlerts:

    def test_create_and_list(self, authenticated_client, btc):
        created = authenticated_client.post(
            "/api/alerts/",
            {"asset_symbol": "BTC", "condition": "ABOVE", "threshold_price": "60000"},
            format="json",
        )
        assert created.status_code == 201
        assert created.data["condition"] == "ABOVE"

        listed = authenticated_client.get("/api/alerts/")
        assert listed.status_code == 200
        assert len(listed.data) == 1

    def test_symbol_is_normalized_to_uppercase(self, authenticated_client, btc):
        created = authenticated_client.post(
            "/api/alerts/",
            {"asset_symbol": "btc", "condition": "BELOW", "threshold_price": "40000"},
            format="json",
        )
        assert created.status_code == 201
        assert created.data["asset_symbol"] == "BTC"

    def test_rejects_unknown_asset(self, authenticated_client, btc):
        response = authenticated_client.post(
            "/api/alerts/",
            {"asset_symbol": "NOEXISTE", "condition": "ABOVE", "threshold_price": "1"},
            format="json",
        )
        assert response.status_code == 400

    def test_rejects_non_positive_threshold(self, authenticated_client, btc):
        response = authenticated_client.post(
            "/api/alerts/",
            {"asset_symbol": "BTC", "condition": "ABOVE", "threshold_price": "0"},
            format="json",
        )
        assert response.status_code == 400

    def test_threshold_keeps_decimal_precision(self, authenticated_client, btc):
        threshold = "0.00000123"
        created = authenticated_client.post(
            "/api/alerts/",
            {"asset_symbol": "BTC", "condition": "ABOVE", "threshold_price": threshold},
            format="json",
        )
        stored = PriceAlert.objects.get(pk=created.data["id"])
        assert stored.threshold_price == Decimal(threshold)

    def test_toggle_switches_the_active_flag(self, authenticated_client, btc):
        alert_id = authenticated_client.post(
            "/api/alerts/",
            {"asset_symbol": "BTC", "condition": "ABOVE", "threshold_price": "60000"},
            format="json",
        ).data["id"]

        off = authenticated_client.patch(f"/api/alerts/{alert_id}/toggle/")
        assert off.data["is_active"] is False

        on = authenticated_client.patch(f"/api/alerts/{alert_id}/toggle/")
        assert on.data["is_active"] is True

    def test_reactivating_clears_the_triggered_state(self, authenticated_client, btc):
        """
        Una alerta reactivada vuelve a poder dispararse; si conservara
        `is_triggered`, el worker la ignoraría para siempre.
        """
        alert_id = authenticated_client.post(
            "/api/alerts/",
            {"asset_symbol": "BTC", "condition": "ABOVE", "threshold_price": "60000"},
            format="json",
        ).data["id"]

        PriceAlert.objects.filter(pk=alert_id).update(
            is_triggered=True, triggered_at=timezone.now()
        )

        authenticated_client.patch(f"/api/alerts/{alert_id}/toggle/")  # desactiva
        reactivated = authenticated_client.patch(f"/api/alerts/{alert_id}/toggle/")

        assert reactivated.data["is_active"] is True
        assert reactivated.data["is_triggered"] is False

    def test_active_only_filter(self, authenticated_client, btc):
        alert_id = authenticated_client.post(
            "/api/alerts/",
            {"asset_symbol": "BTC", "condition": "ABOVE", "threshold_price": "60000"},
            format="json",
        ).data["id"]
        authenticated_client.patch(f"/api/alerts/{alert_id}/toggle/")

        assert len(authenticated_client.get("/api/alerts/", {"active_only": "true"}).data) == 0
        assert len(authenticated_client.get("/api/alerts/").data) == 1

    def test_delete(self, authenticated_client, btc):
        alert_id = authenticated_client.post(
            "/api/alerts/",
            {"asset_symbol": "BTC", "condition": "ABOVE", "threshold_price": "60000"},
            format="json",
        ).data["id"]

        assert authenticated_client.delete(f"/api/alerts/{alert_id}/").status_code == 204
        assert not PriceAlert.objects.filter(pk=alert_id).exists()

    def test_cannot_touch_another_users_alert(self, authenticated_client, admin_client, btc):
        alert_id = authenticated_client.post(
            "/api/alerts/",
            {"asset_symbol": "BTC", "condition": "ABOVE", "threshold_price": "60000"},
            format="json",
        ).data["id"]

        assert admin_client.delete(f"/api/alerts/{alert_id}/").status_code == 404
        assert PriceAlert.objects.filter(pk=alert_id).exists()


@pytest.mark.integration
class TestAlertEvaluation:
    """Lo que hace el worker de Celery cada dos minutos."""

    def test_above_alert_triggers_when_the_price_exceeds_the_threshold(
        self, authenticated_client, test_user, btc
    ):
        from core.application.use_cases.manage_alerts import CheckAlertsUseCase

        alert = PriceAlert.objects.create(
            user=test_user, asset=btc, condition="ABOVE", threshold_price=Decimal("40000")
        )
        # current_price del activo = 50.000 > 40.000
        triggered = CheckAlertsUseCase().execute()

        alert.refresh_from_db()
        assert alert.is_triggered is True
        assert alert.triggered_at is not None
        assert len(triggered) == 1

    def test_below_alert_does_not_trigger_above_the_threshold(self, test_user, btc):
        from core.application.use_cases.manage_alerts import CheckAlertsUseCase

        alert = PriceAlert.objects.create(
            user=test_user, asset=btc, condition="BELOW", threshold_price=Decimal("40000")
        )
        CheckAlertsUseCase().execute()

        alert.refresh_from_db()
        assert alert.is_triggered is False

    def test_inactive_alerts_are_ignored(self, test_user, btc):
        from core.application.use_cases.manage_alerts import CheckAlertsUseCase

        alert = PriceAlert.objects.create(
            user=test_user,
            asset=btc,
            condition="ABOVE",
            threshold_price=Decimal("40000"),
            is_active=False,
        )
        CheckAlertsUseCase().execute()

        alert.refresh_from_db()
        assert alert.is_triggered is False

    def test_an_alert_does_not_trigger_twice(self, test_user, btc):
        """Sin esta regla, el usuario recibiría un email cada dos minutos."""
        from core.application.use_cases.manage_alerts import CheckAlertsUseCase

        PriceAlert.objects.create(
            user=test_user, asset=btc, condition="ABOVE", threshold_price=Decimal("40000")
        )
        assert len(CheckAlertsUseCase().execute()) == 1
        assert len(CheckAlertsUseCase().execute()) == 0


# ── Historial de operaciones ───────────────────────────────────────


@pytest.mark.integration
class TestTradeHistory:

    def _add(self, client, **overrides):
        payload = {
            "asset_symbol": "BTC",
            "trade_type": "BUY",
            "quantity": "1.5",
            "price_usd": "20000",
            "executed_at": "2026-01-15T10:00:00Z",
        }
        payload.update(overrides)
        return client.post("/api/portfolio/trades/", payload, format="json")

    def test_add_and_list(self, authenticated_client, btc):
        assert self._add(authenticated_client).status_code == 201

        listed = authenticated_client.get("/api/portfolio/trades/")
        assert listed.status_code == 200
        assert len(listed.data) == 1

    def test_total_is_quantity_times_price(self, authenticated_client, btc):
        response = self._add(authenticated_client, quantity="1.5", price_usd="20000")
        assert Decimal(response.data["total_usd"]) == Decimal("30000")

    def test_filter_by_type(self, authenticated_client, btc):
        self._add(authenticated_client, trade_type="BUY")
        self._add(authenticated_client, trade_type="SELL")

        buys = authenticated_client.get("/api/portfolio/trades/", {"trade_type": "BUY"})
        assert len(buys.data) == 1
        assert buys.data[0]["trade_type"] == "BUY"

    def test_limit_is_respected(self, authenticated_client, btc):
        for _ in range(3):
            self._add(authenticated_client)

        limited = authenticated_client.get("/api/portfolio/trades/", {"limit": 2})
        assert len(limited.data) == 2

    def test_rejects_a_future_date(self, authenticated_client, btc):
        response = self._add(authenticated_client, executed_at="2099-01-01T10:00:00Z")
        assert response.status_code == 400

    def test_delete(self, authenticated_client, btc):
        trade_id = self._add(authenticated_client).data["id"]
        assert authenticated_client.delete(f"/api/portfolio/trades/{trade_id}/").status_code == 204
        assert not TradeHistory.objects.filter(pk=trade_id).exists()

    def test_cannot_delete_another_users_trade(self, authenticated_client, admin_client, btc):
        trade_id = self._add(authenticated_client).data["id"]
        assert admin_client.delete(f"/api/portfolio/trades/{trade_id}/").status_code == 404
        assert TradeHistory.objects.filter(pk=trade_id).exists()


# ── Watchlist ──────────────────────────────────────────────────────


@pytest.mark.integration
class TestWatchlist:

    def test_add_list_and_remove(self, authenticated_client, btc):
        assert (
            authenticated_client.post(
                "/api/watchlist/", {"symbol": "BTC"}, format="json"
            ).status_code
            == 201
        )

        listed = authenticated_client.get("/api/watchlist/")
        assert [item["symbol"] for item in listed.data] == ["BTC"]

        assert authenticated_client.delete("/api/watchlist/BTC/").status_code == 204
        assert authenticated_client.get("/api/watchlist/").data == []

    def test_adding_twice_is_idempotent(self, authenticated_client, btc):
        authenticated_client.post("/api/watchlist/", {"symbol": "BTC"}, format="json")
        second = authenticated_client.post("/api/watchlist/", {"symbol": "BTC"}, format="json")

        assert second.status_code == 200
        assert len(authenticated_client.get("/api/watchlist/").data) == 1

    def test_unknown_asset_is_rejected(self, authenticated_client, btc):
        response = authenticated_client.post(
            "/api/watchlist/", {"symbol": "NOEXISTE"}, format="json"
        )
        assert response.status_code == 404

    def test_removing_something_not_on_the_list(self, authenticated_client, btc):
        assert authenticated_client.delete("/api/watchlist/BTC/").status_code == 404


# ── Retención de datos ─────────────────────────────────────────────


@pytest.mark.integration
class TestDataRetention:
    """
    Las tablas de crecimiento ilimitado se podan.

    `MarketDataSnapshot` crece ~144 filas al día por activo; sin purga la
    tabla no tiene techo.
    """

    def test_old_snapshots_are_purged(self, btc, settings):
        from core.tasks import purge_old_market_snapshots

        settings.MARKET_SNAPSHOT_RETENTION_DAYS = 30
        now = timezone.now()

        old = MarketDataSnapshot.objects.create(
            asset=btc,
            price=Decimal("1"),
            volume=Decimal("1"),
            timestamp=now - timedelta(days=60),
        )
        recent = MarketDataSnapshot.objects.create(
            asset=btc,
            price=Decimal("1"),
            volume=Decimal("1"),
            timestamp=now - timedelta(days=5),
        )

        result = purge_old_market_snapshots()

        assert result["deleted"] == 1
        assert not MarketDataSnapshot.objects.filter(pk=old.pk).exists()
        assert MarketDataSnapshot.objects.filter(pk=recent.pk).exists()

    def test_old_audit_entries_are_purged(self, db, settings):
        from core.tasks import purge_audit_log

        settings.AUDIT_LOG_RETENTION_DAYS = 90

        old = AuditLog.objects.create(action=AuditLog.Action.LOGIN_SUCCESS)
        recent = AuditLog.objects.create(action=AuditLog.Action.LOGIN_SUCCESS)
        # `created_at` es auto_now_add: se reescribe con UPDATE para
        # simular una entrada antigua.
        AuditLog.objects.filter(pk=old.pk).update(
            created_at=timezone.now() - timedelta(days=200)
        )

        result = purge_audit_log()

        assert result["deleted"] == 1
        assert not AuditLog.objects.filter(pk=old.pk).exists()
        assert AuditLog.objects.filter(pk=recent.pk).exists()
