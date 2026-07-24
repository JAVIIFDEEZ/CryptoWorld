"""
evaluate_quant_alerts.py — Motor de evaluación de alertas cuantitativas.

Recorre todas las alertas activas, calcula el valor actual de su métrica,
aplica la lógica de disparo por flanco (dominio) y el cooldown temporal, y
—cuando procede— registra el disparo, re-arma el estado y lo notifica por los
canales del sistema (feed in-app/WS vía QuantAlertFiring + push web).

El ``provider`` y el ``pusher`` son inyectables para que los tests puedan
alimentar valores deterministas y capturar las notificaciones sin tocar redes.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from django.utils import timezone

from core.application.use_cases.quant_alert_providers import MetricProvider
from core.domain.services.quant_alert_rules import evaluate

logger = logging.getLogger(__name__)


class EvaluateQuantAlertsUseCase:
    """Evalúa todas las alertas cuantitativas activas en una pasada."""

    def __init__(self, provider=None, pusher: Optional[Callable] = None) -> None:
        self._provider = provider or MetricProvider()
        self._pusher = pusher   # None → push web real; callable → inyectado (tests)

    def execute(self) -> dict:
        from core.infrastructure.persistence.models import QuantAlert, QuantAlertFiring

        now = timezone.now()
        alerts = (
            QuantAlert.objects.filter(is_active=True)
            .select_related("asset", "user")
        )

        evaluated = fired = skipped = 0
        firings: list = []

        for alert in alerts:
            value = self._provider.value(alert)
            if value is None:
                skipped += 1
                continue
            evaluated += 1

            result = evaluate(
                metric=alert.metric, operator=alert.operator,
                threshold=alert.threshold, value=value,
                prev_side=alert.last_side,
            )

            in_cooldown = False
            if result.fired and alert.last_fired_at is not None:
                elapsed_min = (now - alert.last_fired_at).total_seconds() / 60.0
                in_cooldown = elapsed_min < alert.cooldown_minutes

            if result.fired and not in_cooldown:
                firing = QuantAlertFiring.objects.create(
                    alert=alert, value=round(value, 6), threshold=alert.threshold,
                    operator=alert.operator, message=result.message,
                )
                alert.last_fired_at = now
                fired += 1
                firings.append(firing)
                self._notify(alert, firing)

            # Persistir siempre el estado del flanco para re-armar sin spam.
            alert.last_side = result.new_side
            alert.last_value = round(value, 6)
            alert.save(update_fields=["last_side", "last_value", "last_fired_at", "updated_at"])

        logger.info(
            "evaluate_quant_alerts: %d evaluadas, %d disparadas, %d sin dato",
            evaluated, fired, skipped,
        )
        return {"evaluated": evaluated, "fired": fired, "skipped": skipped,
                "firing_ids": [f.id for f in firings]}

    # ── Notificación (push web best-effort; feed vía QuantAlertFiring) ──
    def _notify(self, alert, firing) -> None:
        if self._pusher is not None:
            try:
                self._pusher(alert, firing)
            except Exception as exc:  # noqa: BLE001
                logger.warning("pusher inyectado falló: %s", exc)
            return
        try:
            from core.infrastructure.push.web_push import send_to_user, is_configured
            if not is_configured():
                return
            target = alert.asset.symbol if alert.asset else "Cartera"
            send_to_user(alert.user_id, {
                "title": f"Alerta cuantitativa · {target}",
                "body": firing.message,
                "tag": f"quant-{alert.id}",
                "url": "/alerts",
            })
        except Exception as exc:  # noqa: BLE001 — el push no debe frenar el motor
            logger.warning("push alerta cuantitativa %s: %s", alert.id, exc)
