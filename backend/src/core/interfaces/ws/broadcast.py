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
