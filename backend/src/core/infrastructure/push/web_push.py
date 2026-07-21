"""
web_push.py — Envío de notificaciones Web Push (PWA), con degradación.

Envía un payload cifrado a los navegadores suscritos de un usuario para que las
notificaciones críticas lleguen AUNQUE la app esté cerrada. Robusto ante
entornos sin la infraestructura:
  · Si `pywebpush` no está instalado o faltan las claves VAPID, no hace nada
    (el WebSocket y el centro de notificaciones in-app siguen funcionando).
  · Una suscripción caducada (410/404 del push service) se elimina sola.

Producción: instalar `pywebpush`, generar el par VAPID una vez y configurar
VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY / VAPID_CLAIM_EMAIL en el entorno. El
frontend obtiene la clave pública de GET /api/push/public-key/.
"""

import json
import logging

logger = logging.getLogger(__name__)


def vapid_public_key() -> str | None:
    from django.conf import settings
    return getattr(settings, "VAPID_PUBLIC_KEY", "") or None


def is_configured() -> bool:
    """True si el envío real es posible (lib presente + claves configuradas)."""
    from django.conf import settings
    if not (getattr(settings, "VAPID_PUBLIC_KEY", "") and getattr(settings, "VAPID_PRIVATE_KEY", "")):
        return False
    try:
        import pywebpush  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 — lib no instalada en este entorno
        return False


def send_to_user(user_id: int, payload: dict) -> int:
    """Envía `payload` (JSON) a todas las suscripciones del usuario. Devuelve
    cuántas se enviaron. No-op silencioso si el envío no está configurado."""
    if not user_id or not is_configured():
        return 0
    from django.conf import settings
    from pywebpush import WebPushException, webpush
    from core.infrastructure.persistence.models import PushSubscription

    subs = list(PushSubscription.objects.filter(owner_id=user_id))
    if not subs:
        return 0
    vapid_claims = {"sub": f"mailto:{getattr(settings, 'VAPID_CLAIM_EMAIL', 'admin@cryptoworld.app')}"}
    body = json.dumps(payload)
    sent = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                },
                data=body,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims=dict(vapid_claims),
            )
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404, 410):     # suscripción muerta: limpiar
                sub.delete()
                logger.info("push: suscripción caducada eliminada (user %s)", user_id)
            else:
                logger.warning("push a user %s falló: %s", user_id, exc)
        except Exception as exc:  # noqa: BLE001 — el push nunca rompe al emisor
            logger.warning("push a user %s error: %s", user_id, exc)
    return sent
