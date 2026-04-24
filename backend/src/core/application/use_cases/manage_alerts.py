"""
manage_alerts.py — Casos de uso: CRUD de alertas de precio.
"""

import logging
from decimal import Decimal
from datetime import datetime, UTC
from typing import Optional

from core.application.dto.alerts_dto import CreateAlertInputDTO, AlertOutputDTO
from core.infrastructure.persistence.models import PriceAlert, CryptoAsset

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────

def _to_dto(alert: PriceAlert) -> AlertOutputDTO:
    return AlertOutputDTO(
        id=alert.pk,
        asset_symbol=alert.asset.symbol,
        asset_name=alert.asset.name,
        condition=alert.condition,
        threshold_price=str(alert.threshold_price),
        current_price=str(alert.asset.current_price or "0"),
        is_active=alert.is_active,
        is_triggered=alert.is_triggered,
        triggered_at=alert.triggered_at.isoformat() if alert.triggered_at else None,
        notes=alert.notes,
        created_at=alert.created_at.isoformat(),
    )


# ── Create ─────────────────────────────────────────────────────────

class CreateAlertUseCase:
    """Crea una nueva alerta de precio para el usuario autenticado."""

    def execute(self, user, dto: CreateAlertInputDTO) -> AlertOutputDTO:
        symbol = dto.asset_symbol.upper()

        try:
            asset = CryptoAsset.objects.get(symbol=symbol)
        except CryptoAsset.DoesNotExist:
            raise ValueError(f"Activo '{symbol}' no encontrado.")

        if dto.condition not in ("ABOVE", "BELOW"):
            raise ValueError("condition debe ser 'ABOVE' o 'BELOW'.")

        threshold = Decimal(str(dto.threshold_price))
        if threshold <= 0:
            raise ValueError("El precio umbral debe ser mayor que cero.")

        alert = PriceAlert.objects.create(
            user=user,
            asset=asset,
            condition=dto.condition,
            threshold_price=threshold,
            notes=dto.notes,
        )
        return _to_dto(alert)


# ── List ───────────────────────────────────────────────────────────

class ListAlertsUseCase:
    """Devuelve todas las alertas del usuario con precios actualizados."""

    def execute(self, user, active_only: bool = False) -> list[AlertOutputDTO]:
        qs = PriceAlert.objects.filter(user=user).select_related("asset")
        if active_only:
            qs = qs.filter(is_active=True)
        return [_to_dto(a) for a in qs]


# ── Delete ─────────────────────────────────────────────────────────

class DeleteAlertUseCase:
    """Elimina una alerta del usuario."""

    def execute(self, user, alert_id: int) -> None:
        try:
            alert = PriceAlert.objects.get(pk=alert_id, user=user)
        except PriceAlert.DoesNotExist:
            raise ValueError(f"Alerta {alert_id} no encontrada.")
        alert.delete()


# ── Toggle active ──────────────────────────────────────────────────

class ToggleAlertUseCase:
    """Activa o desactiva una alerta."""

    def execute(self, user, alert_id: int) -> AlertOutputDTO:
        try:
            alert = PriceAlert.objects.get(pk=alert_id, user=user)
        except PriceAlert.DoesNotExist:
            raise ValueError(f"Alerta {alert_id} no encontrada.")

        alert.is_active = not alert.is_active
        # Si se reactiva, resetear triggered
        if alert.is_active:
            alert.is_triggered = False
            alert.triggered_at = None
        alert.save(update_fields=["is_active", "is_triggered", "triggered_at", "updated_at"])
        return _to_dto(alert)


# ── Check (usado por Celery task) ──────────────────────────────────

class CheckAlertsUseCase:
    """
    Evalúa todas las alertas activas y marca las que se han disparado.

    Llamado periódicamente por el worker Celery.
    Devuelve lista de alertas disparadas en esta ejecución.
    """

    def execute(self) -> list[AlertOutputDTO]:
        alerts = (
            PriceAlert.objects.filter(is_active=True, is_triggered=False)
            .select_related("asset")
        )

        triggered = []
        now = datetime.now(UTC)

        for alert in alerts:
            current_price = alert.asset.current_price
            if current_price is None:
                continue

            fired = False
            if alert.condition == "ABOVE" and current_price >= alert.threshold_price:
                fired = True
            elif alert.condition == "BELOW" and current_price <= alert.threshold_price:
                fired = True

            if fired:
                alert.is_triggered = True
                alert.triggered_at = now
                alert.is_active = False
                alert.save(
                    update_fields=["is_triggered", "triggered_at", "is_active", "updated_at"]
                )
                triggered.append(_to_dto(alert))
                logger.info(
                    "Alerta disparada: %s %s %s @ %s (precio actual: %s)",
                    alert.asset.symbol,
                    alert.condition,
                    alert.threshold_price,
                    now,
                    current_price,
                )

        return triggered
