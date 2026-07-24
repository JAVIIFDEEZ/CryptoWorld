"""
manage_quant_alerts.py — Casos de uso CRUD del motor de alertas cuantitativas.

Validan contra el registro de métricas del dominio (métrica conocida, ámbito
activo/cartera coherente, operador y marco válidos) y exponen las alertas y sus
disparos recientes al feed de la app.
"""

from __future__ import annotations

import logging

from core.domain.services.quant_alert_rules import (
    METRIC_REGISTRY, OPERATORS, is_portfolio_metric, metric_meta,
)
from core.infrastructure.persistence.models import (
    CryptoAsset, QuantAlert, QuantAlertFiring,
)

logger = logging.getLogger(__name__)

_TIMEFRAMES = ("1h", "4h", "1d")


def _to_dict(alert: QuantAlert) -> dict:
    meta = metric_meta(alert.metric)
    return {
        "id": alert.pk,
        "asset_symbol": alert.asset.symbol if alert.asset else None,
        "asset_name": alert.asset.name if alert.asset else None,
        "metric": alert.metric,
        "metric_label": meta.label if meta else alert.metric,
        "metric_unit": meta.unit if meta else "",
        "scope": meta.scope if meta else "asset",
        "timeframe": alert.timeframe,
        "operator": alert.operator,
        "threshold": alert.threshold,
        "cooldown_minutes": alert.cooldown_minutes,
        "is_active": alert.is_active,
        "last_value": alert.last_value,
        "last_fired_at": alert.last_fired_at.isoformat() if alert.last_fired_at else None,
        "note": alert.note,
        "created_at": alert.created_at.isoformat(),
    }


def _firing_dict(f: QuantAlertFiring) -> dict:
    meta = metric_meta(f.alert.metric)
    return {
        "id": f.id,
        "alert_id": f.alert_id,
        "metric": f.alert.metric,
        "metric_label": meta.label if meta else f.alert.metric,
        "asset_symbol": f.alert.asset.symbol if f.alert.asset else None,
        "value": f.value,
        "threshold": f.threshold,
        "operator": f.operator,
        "message": f.message,
        "seen": f.seen,
        "fired_at": f.fired_at.isoformat(),
    }


def metric_catalog() -> list[dict]:
    """Catálogo de métricas para el constructor de reglas de la UI."""
    return [
        {"key": m.key, "label": m.label, "unit": m.unit, "category": m.category,
         "scope": m.scope, "hint": m.hint}
        for m in METRIC_REGISTRY.values()
    ]


def _validate(data: dict) -> dict:
    metric = (data.get("metric") or "").strip()
    meta = metric_meta(metric)
    if meta is None:
        raise ValueError(f"Métrica desconocida: '{metric}'.")

    operator = (data.get("operator") or "").strip()
    if operator not in OPERATORS:
        raise ValueError(f"Operador inválido: '{operator}'.")

    try:
        threshold = float(data.get("threshold"))
    except (TypeError, ValueError):
        raise ValueError("El umbral debe ser numérico.")

    cooldown = int(data.get("cooldown_minutes", 60) or 60)
    if cooldown < 0:
        raise ValueError("El cooldown no puede ser negativo.")

    timeframe = (data.get("timeframe") or "1h").strip()
    if timeframe not in _TIMEFRAMES:
        raise ValueError(f"Marco temporal inválido: '{timeframe}'.")

    asset = None
    if not is_portfolio_metric(metric):
        symbol = (data.get("asset_symbol") or "").upper().strip()
        if not symbol:
            raise ValueError("Esta métrica requiere un activo.")
        try:
            asset = CryptoAsset.objects.get(symbol=symbol)
        except CryptoAsset.DoesNotExist:
            raise ValueError(f"Activo '{symbol}' no encontrado.")

    return {
        "metric": metric, "operator": operator, "threshold": threshold,
        "cooldown_minutes": cooldown, "timeframe": timeframe, "asset": asset,
        "note": (data.get("note") or "").strip()[:300],
    }


class ListQuantAlertsUseCase:
    def execute(self, user) -> list[dict]:
        qs = QuantAlert.objects.filter(user=user).select_related("asset")
        return [_to_dict(a) for a in qs]


class CreateQuantAlertUseCase:
    def execute(self, user, data: dict) -> dict:
        fields = _validate(data)
        alert = QuantAlert.objects.create(user=user, **fields)
        return _to_dict(alert)


class UpdateQuantAlertUseCase:
    def execute(self, user, alert_id: int, data: dict) -> dict:
        try:
            alert = QuantAlert.objects.get(pk=alert_id, user=user)
        except QuantAlert.DoesNotExist:
            raise ValueError("Alerta no encontrada.")
        # Toggle rápido de activación sin revalidar toda la regla.
        if set(data.keys()) <= {"is_active"}:
            alert.is_active = bool(data["is_active"])
            alert.save(update_fields=["is_active", "updated_at"])
            return _to_dict(alert)
        fields = _validate(data)
        for k, v in fields.items():
            setattr(alert, k, v)
        if "is_active" in data:
            alert.is_active = bool(data["is_active"])
        # Reset del estado de flanco al reconfigurar la regla.
        alert.last_side = ""
        alert.last_value = None
        alert.save()
        return _to_dict(alert)


class DeleteQuantAlertUseCase:
    def execute(self, user, alert_id: int) -> None:
        deleted, _ = QuantAlert.objects.filter(pk=alert_id, user=user).delete()
        if not deleted:
            raise ValueError("Alerta no encontrada.")


class ListQuantFiringsUseCase:
    def execute(self, user, limit: int = 30, mark_seen: bool = False) -> list[dict]:
        qs = (
            QuantAlertFiring.objects.filter(alert__user=user)
            .select_related("alert", "alert__asset")[:max(1, min(limit, 100))]
        )
        rows = [_firing_dict(f) for f in qs]
        if mark_seen:
            QuantAlertFiring.objects.filter(
                alert__user=user, seen=False,
            ).update(seen=True)
        return rows
