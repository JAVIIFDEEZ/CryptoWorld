"""
core/tasks.py — Tareas asíncronas Celery para CryptoWorld.

Las tareas se ejecutan en background por el servicio 'celery-worker' de Docker.
El scheduler (celery-beat) las dispara según CELERY_BEAT_SCHEDULE en settings.py.

Tareas:
- check_price_alerts: Evalúa todas las alertas activas cada 2 min.
- sync_market_prices: Sincroniza precios desde CoinGecko cada 10 min.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


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

        result = CheckAlertsUseCase().execute()
        logger.info(
            "check_price_alerts: %d alertas disparadas de %d revisadas",
            result["triggered"],
            result["checked"],
        )
        return result
    except Exception as exc:
        logger.error("check_price_alerts error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    name="core.tasks.sync_market_prices",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def sync_market_prices(self):
    """
    Sincroniza precios y datos de mercado de los activos en la BD
    consultando la API de CoinGecko.
    """
    try:
        from core.application.use_cases.sync_market_data import SyncMarketDataUseCase

        result = SyncMarketDataUseCase().execute()
        logger.info("sync_market_prices: %d activos sincronizados", result.get("synced", 0))
        return result
    except Exception as exc:
        logger.error("sync_market_prices error: %s", exc, exc_info=True)
        raise self.retry(exc=exc)
