"""
test_quant_alerts.py — Motor de alertas cuantitativas.

Cubre la lógica pura de disparo por flanco (dominio), el evaluador con
cooldown y provider inyectado, la validación del CRUD y la API REST.
"""

import pytest
from datetime import timedelta
from django.utils import timezone

from core.domain.services.quant_alert_rules import evaluate, METRIC_REGISTRY, is_portfolio_metric
from core.infrastructure.persistence.models import (
    CryptoAsset, QuantAlert, QuantAlertFiring,
)


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def asset(db):
    return CryptoAsset.objects.create(
        symbol="BTC", name="Bitcoin", current_price="65000", price_change_24h="2.5",
    )


class _FakeProvider:
    """Provider inyectable: devuelve un valor fijo (o una secuencia)."""
    def __init__(self, value):
        self._values = list(value) if isinstance(value, (list, tuple)) else None
        self._value = value

    def value(self, alert):
        if self._values is not None:
            return self._values.pop(0) if self._values else None
        return self._value


def _run(provider):
    from core.application.use_cases.evaluate_quant_alerts import EvaluateQuantAlertsUseCase
    fired = []
    return EvaluateQuantAlertsUseCase(
        provider=provider, pusher=lambda a, f: fired.append(f),
    ).execute()


# ── Dominio: disparo por flanco ─────────────────────────────────────

class TestEdgeTrigger:
    def test_gt_fires_on_entering_zone(self):
        ev = evaluate(metric="rsi", operator="gt", threshold=70, value=72, prev_side="below")
        assert ev.fired and ev.new_side == "above"

    def test_gt_does_not_refire_while_inside(self):
        ev = evaluate(metric="rsi", operator="gt", threshold=70, value=75, prev_side="above")
        assert not ev.fired

    def test_lt_fires_on_entering_below(self):
        ev = evaluate(metric="rsi", operator="lt", threshold=30, value=28, prev_side="above")
        assert ev.fired and ev.new_side == "below"

    def test_cross_up_requires_prior_below(self):
        assert evaluate(metric="macd_hist", operator="cross_up", threshold=0, value=1, prev_side="below").fired
        assert not evaluate(metric="macd_hist", operator="cross_up", threshold=0, value=1, prev_side="above").fired

    def test_cross_down_requires_prior_above(self):
        assert evaluate(metric="macd_hist", operator="cross_down", threshold=0, value=-1, prev_side="above").fired

    def test_message_mentions_label_and_threshold(self):
        ev = evaluate(metric="rsi", operator="gt", threshold=70, value=72, prev_side="below")
        assert "RSI" in ev.message and "70" in ev.message


# ── Evaluador ───────────────────────────────────────────────────────

@pytest.mark.django_db
class TestEvaluator:
    def test_fires_and_logs_firing(self, test_user, asset):
        QuantAlert.objects.create(
            user=test_user, asset=asset, metric="rsi", operator="gt",
            threshold=70, timeframe="1h",
        )
        result = _run(_FakeProvider(80))
        assert result["fired"] == 1
        assert QuantAlertFiring.objects.count() == 1
        a = QuantAlert.objects.get()
        assert a.last_side == "above" and a.last_fired_at is not None

    def test_cooldown_suppresses_refire(self, test_user, asset):
        # Ya disparada hace poco y todavía "por encima"; debe re-armar sin re-disparar
        # aunque cruce de nuevo — probamos que el cooldown bloquea un flanco fresco.
        QuantAlert.objects.create(
            user=test_user, asset=asset, metric="rsi", operator="gt", threshold=70,
            cooldown_minutes=60, last_side="below",
            last_fired_at=timezone.now() - timedelta(minutes=5),
        )
        result = _run(_FakeProvider(80))
        assert result["fired"] == 0            # dentro del cooldown
        assert QuantAlertFiring.objects.count() == 0

    def test_skips_when_no_value(self, test_user, asset):
        QuantAlert.objects.create(
            user=test_user, asset=asset, metric="rsi", operator="gt", threshold=70,
        )
        result = _run(_FakeProvider(None))
        assert result["evaluated"] == 0 and result["fired"] == 0

    def test_portfolio_metric_without_asset(self, test_user):
        QuantAlert.objects.create(
            user=test_user, asset=None, metric="portfolio_var", operator="gt", threshold=5,
        )
        result = _run(_FakeProvider(7.5))
        assert result["fired"] == 1

    def test_inactive_alert_not_evaluated(self, test_user, asset):
        QuantAlert.objects.create(
            user=test_user, asset=asset, metric="rsi", operator="gt", threshold=70,
            is_active=False,
        )
        assert _run(_FakeProvider(90))["evaluated"] == 0


# ── CRUD / validación ───────────────────────────────────────────────

@pytest.mark.django_db
class TestManage:
    def test_create_requires_asset_for_asset_metric(self, test_user):
        from core.application.use_cases.manage_quant_alerts import CreateQuantAlertUseCase
        with pytest.raises(ValueError):
            CreateQuantAlertUseCase().execute(test_user, {
                "metric": "rsi", "operator": "gt", "threshold": 70,
            })

    def test_create_rejects_unknown_metric(self, test_user, asset):
        from core.application.use_cases.manage_quant_alerts import CreateQuantAlertUseCase
        with pytest.raises(ValueError):
            CreateQuantAlertUseCase().execute(test_user, {
                "metric": "nope", "operator": "gt", "threshold": 1, "asset_symbol": "BTC",
            })

    def test_portfolio_metric_needs_no_asset(self, test_user):
        from core.application.use_cases.manage_quant_alerts import CreateQuantAlertUseCase
        out = CreateQuantAlertUseCase().execute(test_user, {
            "metric": "portfolio_cvar", "operator": "gt", "threshold": 10,
        })
        assert out["scope"] == "portfolio" and out["asset_symbol"] is None

    def test_registry_has_portfolio_and_asset_scopes(self):
        assert is_portfolio_metric("portfolio_var")
        assert not is_portfolio_metric("rsi")
        assert len(METRIC_REGISTRY) >= 12


# ── API ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestApi:
    def test_create_list_and_catalog(self, authenticated_client, asset):
        r = authenticated_client.post("/api/quant-alerts/", {
            "metric": "rsi", "operator": "gt", "threshold": 70,
            "asset_symbol": "BTC", "timeframe": "4h",
        }, format="json")
        assert r.status_code == 201, r.data
        r2 = authenticated_client.get("/api/quant-alerts/?catalog=1")
        assert r2.status_code == 200
        assert len(r2.data["alerts"]) == 1
        assert any(m["key"] == "rsi" for m in r2.data["metrics"])

    def test_toggle_and_delete(self, authenticated_client, asset):
        r = authenticated_client.post("/api/quant-alerts/", {
            "metric": "adx", "operator": "gt", "threshold": 25, "asset_symbol": "BTC",
        }, format="json")
        aid = r.data["id"]
        rp = authenticated_client.patch(f"/api/quant-alerts/{aid}/",
                                        {"is_active": False}, format="json")
        assert rp.status_code == 200 and rp.data["is_active"] is False
        rd = authenticated_client.delete(f"/api/quant-alerts/{aid}/")
        assert rd.status_code == 204
        assert QuantAlert.objects.count() == 0

    def test_firings_endpoint(self, authenticated_client, test_user, asset):
        alert = QuantAlert.objects.create(
            user=test_user, asset=asset, metric="rsi", operator="gt", threshold=70,
        )
        QuantAlertFiring.objects.create(
            alert=alert, value=80, threshold=70, operator="gt", message="RSI ≥ 70",
        )
        r = authenticated_client.get("/api/quant-alerts/firings/")
        assert r.status_code == 200 and len(r.data["firings"]) == 1
        assert r.data["firings"][0]["message"] == "RSI ≥ 70"
