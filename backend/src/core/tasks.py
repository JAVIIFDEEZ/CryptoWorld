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
