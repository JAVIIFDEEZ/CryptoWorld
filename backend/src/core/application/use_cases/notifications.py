"""
notifications.py — Centro de notificaciones in-app (feed unificado).

En lugar de duplicar datos en una tabla nueva, AGREGA SOBRE LECTURA los eventos
que ya existen en el sistema y los presenta como un único feed cronológico:
  · Señales de estrategias monitorizadas (StrategySignalEvent)
  · Alertas de movimiento de direcciones vigiladas (AddressAlert)
  · Predicciones ML resueltas (PredictionRecord acierto/fallo)
  · Alertas de precio disparadas (PriceAlert)
  · Kill-switch de la ejecución real (PaperTradingAccount.live_disabled_at)
  · Cambios de régimen del motor de confluencia 360° (ConfluenceSignalEvent)

El estado "no leído" se resuelve con un único timestamp por usuario
(`notifications_seen_at`): cuenta como no leído todo evento posterior. Abrir el
centro y marcar como leído actualiza ese sello.
"""

import logging

logger = logging.getLogger(__name__)

_UNREAD_CAP = 99   # el contador se muestra como "99+" por encima de esto


def _signal_label(signal: str) -> str:
    return "COMPRA" if signal == "BUY" else "VENTA"


_PRESSURE_TITLES = {
    "ACUMULACION": "Presión on-chain: ACUMULACIÓN",
    "PRESION_VENDEDORA": "Presión on-chain: PRESIÓN VENDEDORA",
    "EQUILIBRIO": "Presión on-chain: equilibrio",
}


class NotificationsFeedUseCase:
    """Feed unificado de notificaciones del usuario + contador de no leídas."""

    def execute(self, owner, limit: int = 30) -> dict:
        from core.infrastructure.persistence.models import (
            AddressAlert, ConfluenceSignalEvent, OnChainSignalEvent,
            PaperTradingAccount, PredictionRecord, PriceAlert, QuantAlertFiring,
            StrategySignalEvent,
        )

        seen = getattr(owner, "notifications_seen_at", None)
        items: list[dict] = []

        # ── Cambios de régimen de la confluencia 360° (globales) ──
        _CONF_TITLES = {
            "CONFLUENCIA_ALCISTA": "alineación ALCISTA",
            "CONFLUENCIA_BAJISTA": "alineación BAJISTA",
            "MIXTO": "fuentes divididas",
            "NEUTRAL": "neutral",
        }
        for ev in ConfluenceSignalEvent.objects.order_by("-created_at")[:limit]:
            items.append({
                "id": f"confluence-{ev.id}",
                "kind": "confluence",
                "title": f"Confluencia {ev.asset_symbol}: {_CONF_TITLES.get(ev.verdict, ev.verdict)}",
                "body": f"score {ev.score:+.2f} · acuerdo {ev.agreement_pct:.0f}%"
                        + (f" · antes {_CONF_TITLES.get(ev.previous_verdict, ev.previous_verdict)}"
                           if ev.previous_verdict else ""),
                "link": "/analysis",
                "ts": ev.created_at,
            })

        # ── Kill-switch de ejecución real (paper→real desactivado) ──
        # Es la notificación más crítica del sistema: hay dinero (o testnet)
        # detrás y la promoción dejó de espejar órdenes por un error.
        for acc in (PaperTradingAccount.objects.select_related("strategy")
                    .filter(owner=owner, live_disabled_at__isnull=False)
                    .order_by("-live_disabled_at")[:limit]):
            items.append({
                "id": f"live-{acc.id}-{int(acc.live_disabled_at.timestamp())}",
                "kind": "live",
                "title": f"Ejecución real desactivada · {acc.asset_symbol}",
                "body": acc.live_error or "Kill-switch activado.",
                "link": "/strategies",
                "ts": acc.live_disabled_at,
            })

        # ── Señales de presión on-chain (globales: cambios de régimen) ──
        for ev in OnChainSignalEvent.objects.order_by("-created_at")[:limit]:
            items.append({
                "id": f"pressure-{ev.id}",
                "kind": "pressure",
                "title": _PRESSURE_TITLES.get(ev.verdict, f"Presión on-chain: {ev.verdict}"),
                "body": f"{ev.chain} · puntuación {ev.pressure:+.2f} (ventana {ev.window_hours}h)",
                "link": "/blockchain",
                "ts": ev.created_at,
            })

        # ── Señales de estrategia ──
        for e in (StrategySignalEvent.objects.select_related("strategy", "strategy__asset")
                  .filter(owner=owner).order_by("-created_at")[:limit]):
            sym = e.strategy.asset.symbol if (e.strategy and e.strategy.asset) else "—"
            items.append({
                "id": f"signal-{e.id}",
                "kind": "signal",
                "title": f"Señal de {_signal_label(e.signal)} · {sym}",
                "body": (e.strategy.name[:80] if e.strategy else ""),
                "link": "/strategies",
                "ts": e.created_at,
            })

        # ── Alertas de ballenas (direcciones vigiladas) ──
        for a in (AddressAlert.objects.select_related("watched")
                  .filter(owner=owner).order_by("-created_at")[:limit]):
            who = a.watched.label or (a.watched.address[:10] + "…") if a.watched else "—"
            verb = "entrada" if a.direction == "increase" else "salida"
            items.append({
                "id": f"whale-{a.id}",
                "kind": "whale",
                "title": f"Movimiento ({verb}) {a.delta_pct:+.1f}%",
                "body": f"{who} · {a.watched.chain if a.watched else ''}",
                "link": "/blockchain",
                "ts": a.created_at,
            })

        # ── Predicciones ML resueltas ──
        for r in (PredictionRecord.objects
                  .filter(owner=owner, status__in=["correct", "incorrect"], resolved_at__isnull=False)
                  .order_by("-resolved_at")[:limit]):
            ok = r.status == "correct"
            ret = f"{r.actual_return_pct:+.2f}%" if r.actual_return_pct is not None else ""
            items.append({
                "id": f"pred-{r.id}",
                "kind": "prediction",
                "title": f"Predicción {r.predicted} — {'acierto' if ok else 'fallo'}",
                "body": f"{r.asset_symbol} · {ret}".strip(" ·"),
                "link": "/analysis",
                "ts": r.resolved_at,
            })

        # ── Alertas de precio disparadas ──
        for p in (PriceAlert.objects.select_related("asset")
                  .filter(user=owner, is_triggered=True, triggered_at__isnull=False)
                  .order_by("-triggered_at")[:limit]):
            sym = p.asset.symbol if p.asset else "—"
            cond = "por encima de" if p.condition == "ABOVE" else "por debajo de"
            items.append({
                "id": f"price-{p.id}",
                "kind": "price",
                "title": f"Alerta de precio · {sym}",
                "body": f"Precio {cond} {p.threshold_price}",
                "link": "/alerts",
                "ts": p.triggered_at,
            })

        # ── Alertas cuantitativas disparadas (motor multi-métrica) ──
        for f in (QuantAlertFiring.objects.select_related("alert", "alert__asset")
                  .filter(alert__user=owner).order_by("-fired_at")[:limit]):
            target = f.alert.asset.symbol if f.alert.asset else "Cartera"
            items.append({
                "id": f"quant-{f.id}",
                "kind": "quant",
                "title": f"Alerta cuantitativa · {target}",
                "body": f.message,
                "link": "/alerts",
                "ts": f.fired_at,
            })

        # Ordenar cronológicamente (más reciente primero) y recortar.
        items.sort(key=lambda it: it["ts"], reverse=True)
        top = items[:limit]

        for it in top:
            it["unread"] = bool(seen is None or it["ts"] > seen)
            it["created_at"] = it["ts"].isoformat()
            del it["ts"]

        return {"unread": self._count_unread(owner, seen), "count": len(top), "items": top}

    @staticmethod
    def _count_unread(owner, since) -> int:
        from core.infrastructure.persistence.models import (
            AddressAlert, ConfluenceSignalEvent, OnChainSignalEvent,
            PaperTradingAccount, PredictionRecord, PriceAlert, QuantAlertFiring,
            StrategySignalEvent,
        )
        confluence = ConfluenceSignalEvent.objects.all()
        pressure = OnChainSignalEvent.objects.all()
        sig = StrategySignalEvent.objects.filter(owner=owner)
        whale = AddressAlert.objects.filter(owner=owner)
        pred = PredictionRecord.objects.filter(
            owner=owner, status__in=["correct", "incorrect"], resolved_at__isnull=False)
        price = PriceAlert.objects.filter(user=owner, is_triggered=True, triggered_at__isnull=False)
        live = PaperTradingAccount.objects.filter(owner=owner, live_disabled_at__isnull=False)
        quant = QuantAlertFiring.objects.filter(alert__user=owner)
        if since is not None:
            total = (sig.filter(created_at__gt=since).count()
                     + whale.filter(created_at__gt=since).count()
                     + pred.filter(resolved_at__gt=since).count()
                     + price.filter(triggered_at__gt=since).count()
                     + pressure.filter(created_at__gt=since).count()
                     + confluence.filter(created_at__gt=since).count()
                     + live.filter(live_disabled_at__gt=since).count()
                     + quant.filter(fired_at__gt=since).count())
        else:
            total = (sig.count() + whale.count() + pred.count() + price.count()
                     + pressure.count() + confluence.count() + live.count()
                     + quant.count())
        return min(total, _UNREAD_CAP)


class MarkNotificationsSeenUseCase:
    """Marca todas las notificaciones como leídas (sella la fecha de visto)."""

    def execute(self, owner) -> dict:
        from django.utils import timezone

        owner.notifications_seen_at = timezone.now()
        owner.save(update_fields=["notifications_seen_at"])
        return {"unread": 0, "seen_at": owner.notifications_seen_at.isoformat()}
