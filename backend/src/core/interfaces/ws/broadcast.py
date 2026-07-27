"""
broadcast.py — Emisión de eventos a los grupos WebSocket desde código síncrono.

Permite que tareas Celery / casos de uso (contexto síncrono) publiquen
actualizaciones a los clientes conectados a través de la capa de canales.
Degradación silenciosa: si no hay capa configurada o falla, no rompe el sync.
"""

import logging

logger = logging.getLogger(__name__)


def broadcast_price_update(items: list[dict]) -> bool:
    """Empuja una lista de precios {symbol, price, change} al grupo de precios.
    Devuelve True si se emitió."""
    if not items:
        return False
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from core.interfaces.ws.consumers import PRICE_GROUP

    layer = get_channel_layer()
    if layer is None:
        return False
    try:
        async_to_sync(layer.group_send)(
            PRICE_GROUP, {"type": "price_update", "data": items},
        )
        return True
    except Exception as exc:  # noqa: BLE001 — el broadcast nunca debe romper el sync
        logger.warning("broadcast_price_update fallo: %s", exc)
        return False


# Avisos que además se envían por Web Push (llegan con la app cerrada). Solo
# los críticos, para no ser ruidosos: kill-switch/riesgo, precio y confluencia.
_PUSH_KINDS = {"live", "price", "confluence", "whale"}
_PUSH_TITLES = {
    "live": "⛔ Ejecución real",
    "price": "🔔 Alerta de precio",
    "confluence": "🎯 Confluencia",
    "whale": "🐋 Movimiento on-chain",
}


def broadcast_notification(user_id: "int | None", data: dict) -> bool:
    """Empuja un aviso ligero al canal personal del usuario (la campana
    re-consulta el feed HTTP al recibirlo) y, si es crítico, lo manda también
    por Web Push. Devuelve True si se emitió por WebSocket."""
    if not user_id:
        return False

    # Web Push (best-effort, desactivado si no hay claves VAPID): las notis
    # críticas llegan aunque la pestaña esté cerrada.
    try:
        kind = (data or {}).get("kind")
        if kind in _PUSH_KINDS:
            from core.infrastructure.push.web_push import send_to_user
            send_to_user(user_id, {
                "title": _PUSH_TITLES.get(kind, "CryptoWorld"),
                "body": data.get("body") or "Toca para ver el detalle.",
                "url": data.get("url") or "/",
                "kind": kind,
            })
    except Exception as exc:  # noqa: BLE001 — el push nunca rompe el WebSocket
        logger.warning("push desde broadcast fallo: %s", exc)

    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from core.interfaces.ws.consumers import notif_group

    layer = get_channel_layer()
    if layer is None:
        return False
    try:
        async_to_sync(layer.group_send)(
            notif_group(user_id), {"type": "notify", "data": data},
        )
        return True
    except Exception as exc:  # noqa: BLE001 — el broadcast nunca debe romper al emisor
        logger.warning("broadcast_notification fallo: %s", exc)
        return False
