"""
sync_market_data.py — Caso de uso: Sincronizar catálogo de mercado desde CoinGecko.

Obtiene el top N de criptomonedas por market cap desde CoinGecko y:
  1. Crea o actualiza el registro CryptoAsset (símbolo, nombre, precio, logo, etc.)
  2. Crea un MarketDataSnapshot (serie temporal inmutable)

Se invoca desde el panel Admin (POST /api/admin/market/sync/)
o desde un cron job en el futuro.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, UTC
from decimal import Decimal, InvalidOperation
from typing import Optional

from core.infrastructure.external_apis.coingecko_client import (
    CoinGeckoClient,
    CoinGeckoClientError,
)
from core.infrastructure.persistence.models import CryptoAsset, MarketDataSnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncResultDTO:
    assets_created: int
    assets_updated: int
    snapshots_created: int
    errors: list[str] = field(default_factory=list)


def _to_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


class SyncMarketDataUseCase:
    """
    Sincroniza el catálogo de activos y datos de mercado desde CoinGecko.

    Flujo:
      1. GET /coins/markets → top N por market cap
      2. Por cada moneda: upsert CryptoAsset + crear MarketDataSnapshot
      3. Devuelve estadísticas del sync (created/updated/errors)
    """

    def __init__(self, client: Optional[CoinGeckoClient] = None) -> None:
        self._client = client or CoinGeckoClient()

    def execute(self, per_page: int = 100) -> SyncResultDTO:
        errors: list[str] = []
        created = 0
        updated = 0
        snapshots = 0

        try:
            coins = self._client.get_markets(per_page=min(per_page, 250))
        except CoinGeckoClientError as exc:
            logger.error("Error obteniendo datos de CoinGecko: %s", exc)
            return SyncResultDTO(
                assets_created=0,
                assets_updated=0,
                snapshots_created=0,
                errors=[str(exc)],
            )

        now = datetime.now(UTC)

        for coin in coins:
            try:
                symbol = (coin.get("symbol") or "").upper()
                coingecko_id = coin.get("id") or ""
                name = coin.get("name") or symbol
                current_price = _to_decimal(coin.get("current_price")) or Decimal("0")
                market_cap = _to_decimal(coin.get("market_cap"))
                volume_24h = _to_decimal(coin.get("total_volume"))
                price_change_24h = _to_decimal(coin.get("price_change_percentage_24h"))
                logo_url = coin.get("image") or None

                if not symbol or not coingecko_id:
                    continue

                asset, is_new = CryptoAsset.objects.update_or_create(
                    coingecko_id=coingecko_id,
                    defaults={
                        "symbol": symbol,
                        "name": name,
                        "current_price": current_price,
                        "market_cap": market_cap,
                        "volume_24h": volume_24h,
                        "price_change_24h": price_change_24h,
                        "logo_url": logo_url,
                    },
                )

                if is_new:
                    created += 1
                else:
                    updated += 1

                # Snapshot inmutable de este momento
                if volume_24h is not None:
                    MarketDataSnapshot.objects.create(
                        asset=asset,
                        price=current_price,
                        volume=volume_24h,
                        market_cap=market_cap,
                        price_change_24h_pct=price_change_24h,
                        timestamp=now,
                    )
                    snapshots += 1

            except Exception as exc:  # noqa: BLE001
                symbol_str = coin.get("symbol", "?").upper()
                logger.warning("Error procesando %s: %s", symbol_str, exc)
                errors.append(f"{symbol_str}: {exc}")

        logger.info(
            "Sync completado — creados: %d, actualizados: %d, snapshots: %d, errores: %d",
            created, updated, snapshots, len(errors),
        )

        return SyncResultDTO(
            assets_created=created,
            assets_updated=updated,
            snapshots_created=snapshots,
            errors=errors,
        )
