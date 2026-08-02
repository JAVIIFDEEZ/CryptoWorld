"""
core/tasks.py — Tareas asíncronas Celery para CryptoWorld.

Las tareas se ejecutan en background por el servicio 'celery-worker' de Docker.
El scheduler (celery-beat) las dispara según CELERY_BEAT_SCHEDULE en settings.py.

Tareas:
- check_price_alerts:  Evalúa todas las alertas activas cada 2 min.
- sync_prices_quick:   Actualiza precios vía Binance ticker/24hr cada 60 s.
                       Sin cuota CoinGecko, sin crear MarketDataSnapshot.
- sync_market_prices:  Sync completo vía CoinGecko cada 5 min.
                       Actualiza market_cap, logos y crea MarketDataSnapshot.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def dispatch_task(task, *args, **kwargs):
    """
    Encolar una tarea en Celery con degradación a ejecución síncrona.

    En despliegues sin worker Celery o sin broker Redis accesible
    (p. ej. Railway con solo el servicio web), `.delay()` lanza
    OperationalError y la tarea se perdería — el usuario nunca
    recibiría su email de verificación. Este helper detecta el fallo
    de conexión al broker y ejecuta la tarea en el propio proceso web
    como plan B, de forma que el envío de emails nunca depende de que
    la infraestructura asíncrona esté disponible.
    """
    try:
        return task.delay(*args, **kwargs)
    except Exception as exc:
        logger.warning(
            "Broker Celery no disponible (%s). Ejecutando %s de forma síncrona.",
            exc,
            task.name,
        )
        # .apply() ejecuta en el proceso actual; los errores quedan en el
        # EagerResult (no se propagan) y la propia tarea ya los loguea.
        return task.apply(args=args, kwargs=kwargs)


@shared_task(
    name="core.tasks.check_price_alerts",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def check_price_alerts(self):
    """
    Evalúa todas las alertas de precio activas y no disparadas.
    Marca como triggered las que cumplan la condición (ABOVE/BELOW).
    """
    try:
        from core.application.use_cases.manage_alerts import CheckAlertsUseCase

        triggered = CheckAlertsUseCase().execute()
        logger.info(
            "check_price_alerts: %d alertas disparadas",
            len(triggered),
        )
        return {"triggered": len(triggered)}
    except Exception as exc:
        logger.error("check_price_alerts error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.sync_prices_quick",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
)
def sync_prices_quick(self):
    """
    Actualiza current_price, volume_24h y price_change_24h usando Binance
    ticker/24hr (1 llamada HTTP, weight=40, sin cuota CoinGecko).
    No crea MarketDataSnapshot. Se ejecuta cada 60 s.
    """
    try:
        from core.application.use_cases.sync_prices_quick import SyncPricesQuickUseCase

        result = SyncPricesQuickUseCase().execute()
        logger.info(
            "sync_prices_quick: updated=%d, skipped=%d, errors=%d",
            result.updated,
            result.skipped,
            result.errors,
        )
        return {
            "updated": result.updated,
            "skipped": result.skipped,
            "errors": result.errors,
        }
    except Exception as exc:
        logger.error("sync_prices_quick error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.sync_market_prices",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def sync_market_prices(self):
    """
    Sync completo vía CoinGecko: actualiza market_cap, logos, coingecko_id
    y crea MarketDataSnapshot para sparklines. Se ejecuta cada 5 min.
    """
    try:
        from core.application.use_cases.sync_market_data import SyncMarketDataUseCase

        result = SyncMarketDataUseCase().execute()
        logger.info(
            "sync_market_prices: creados=%d, actualizados=%d, snapshots=%d, errores=%d",
            result.assets_created,
            result.assets_updated,
            result.snapshots_created,
            len(result.errors),
        )
        return {
            "created": result.assets_created,
            "updated": result.assets_updated,
            "snapshots": result.snapshots_created,
            "errors": len(result.errors),
        }
    except Exception as exc:
        logger.error("sync_market_prices error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


# ─────────────────────────────────────────────────────────────────
# Email tasks — Envío asíncrono para no bloquear la respuesta HTTP
# ─────────────────────────────────────────────────────────────────

@shared_task(
    name="core.tasks.send_verification_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_verification_email(self, user_id: int) -> dict:
    """
    Envía el email de verificación de cuenta al usuario indicado.

    Se llama desde RegisterView y ResendVerificationEmailView con .delay()
    para no bloquear la respuesta HTTP al usuario.
    Reintenta hasta 3 veces con backoff de 60 s ante fallos de red o SendGrid.
    """
    try:
        from core.application.use_cases.send_verification_email import (
            SendVerificationEmailUseCase,
        )

        SendVerificationEmailUseCase().execute(user_id)
        logger.info("send_verification_email: enviado a user_id=%d", user_id)
        return {"status": "sent", "user_id": user_id}
    except ValueError as exc:
        # Usuario no encontrado u otro error de negocio — no reintentar
        logger.warning("send_verification_email: ValueError user_id=%d — %s", user_id, exc)
        return {"status": "skipped", "reason": str(exc)}
    except Exception as exc:
        logger.error("send_verification_email error user_id=%d: %s", user_id, exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.send_market_digest",
    bind=True,
    max_retries=1,
    default_retry_delay=300,
)
def send_market_digest(self) -> dict:
    """
    Envía el resumen semanal del mercado a los usuarios suscritos
    (notify_market_digest=True). Programado por celery beat los lunes.
    """
    try:
        from core.application.use_cases.send_market_digest import (
            SendMarketDigestUseCase,
        )

        sent = SendMarketDigestUseCase().execute()
        logger.info("send_market_digest: %d emails enviados", sent)
        return {"sent": sent}
    except Exception as exc:
        logger.error("send_market_digest error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.send_email_change_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_email_change_email(self, user_id: int) -> dict:
    """
    Envía el enlace de confirmación de cambio de email a la dirección
    pendiente (pending_email) del usuario. Despachado con dispatch_task
    desde ChangeEmailRequestView.
    """
    try:
        from core.application.use_cases.change_email import RequestEmailChangeUseCase

        RequestEmailChangeUseCase.send_confirmation_email(user_id)
        logger.info("send_email_change_email: enviado para user_id=%d", user_id)
        return {"status": "sent", "user_id": user_id}
    except ValueError as exc:
        logger.warning("send_email_change_email: ValueError user_id=%d — %s", user_id, exc)
        return {"status": "skipped", "reason": str(exc)}
    except Exception as exc:
        logger.error("send_email_change_email error user_id=%d: %s", user_id, exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(name="core.tasks.purge_old_market_snapshots", bind=True, max_retries=1)
def purge_old_market_snapshots(self) -> dict:
    """
    Podar `MarketDataSnapshot` más allá del periodo de retención.

    La tabla crece ~144 filas al día por activo (una cada 10 minutos).
    Con un catálogo de 100 activos son ~5,3 millones de filas al año: sin
    purga, la tabla es de crecimiento ilimitado y termina degradando cada
    consulta de sparklines y el propio coste de almacenamiento.

    El borrado se hace por lotes para no mantener un bloqueo largo ni una
    transacción enorme sobre la tabla en producción.
    """
    from django.conf import settings
    from django.utils import timezone
    from datetime import timedelta

    from core.infrastructure.persistence.models import MarketDataSnapshot

    retention_days = getattr(settings, "MARKET_SNAPSHOT_RETENTION_DAYS", 90)
    cutoff = timezone.now() - timedelta(days=retention_days)
    batch_size = 5_000
    total = 0

    while True:
        ids = list(
            MarketDataSnapshot.objects.filter(timestamp__lt=cutoff)
            .values_list("pk", flat=True)[:batch_size]
        )
        if not ids:
            break
        deleted, _ = MarketDataSnapshot.objects.filter(pk__in=ids).delete()
        total += deleted
        if len(ids) < batch_size:
            break

    logger.info(
        "purge_old_market_snapshots: %d filas eliminadas (retencion %d dias)",
        total,
        retention_days,
    )
    return {"deleted": total, "retention_days": retention_days}


@shared_task(name="core.tasks.purge_audit_log", bind=True, max_retries=1)
def purge_audit_log(self) -> dict:
    """
    Podar el registro de auditoría más allá del periodo de conservación.

    La traza de seguridad tiene que conservarse, pero no indefinidamente:
    guardarla más de lo necesario es a la vez coste y exposición de datos
    personales (IP y user-agent). El periodo se configura por entorno.
    """
    from django.conf import settings
    from django.utils import timezone
    from datetime import timedelta

    from core.infrastructure.persistence.models import AuditLog

    retention_days = getattr(settings, "AUDIT_LOG_RETENTION_DAYS", 365)
    cutoff = timezone.now() - timedelta(days=retention_days)

    deleted, _ = AuditLog.objects.filter(created_at__lt=cutoff).delete()
    logger.info(
        "purge_audit_log: %d entradas eliminadas (retencion %d dias)",
        deleted,
        retention_days,
    )
    return {"deleted": deleted, "retention_days": retention_days}


@shared_task(
    name="core.tasks.send_password_reset_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_password_reset_email(self, email: str) -> dict:
    """
    Envía el email de recuperación de contraseña a la dirección indicada.

    Se llama desde PasswordResetRequestView con .delay() para no bloquear
    la respuesta HTTP. Si el email no existe en el sistema, la tarea
    termina silenciosamente (sin error) para evitar timing attacks.
    """
    try:
        from core.application.use_cases.request_password_reset import (
            RequestPasswordResetUseCase,
        )
        from core.application.dto.auth_dto import PasswordResetRequestDTO

        RequestPasswordResetUseCase().execute(PasswordResetRequestDTO(email=email))
        logger.info("send_password_reset_email: procesado para email=%s", email)
        return {"status": "processed", "email": email}
    except Exception as exc:
        logger.error("send_password_reset_email error email=%s: %s", email, exc, exc_info=True)
        raise self.retry(exc=exc)
