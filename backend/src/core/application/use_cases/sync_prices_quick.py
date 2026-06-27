"""
sync_prices_quick.py — Caso de uso: Sincronización rápida de precios vía Binance.

Obtiene las estadísticas 24 h de TODOS los pares activos en Binance con una
única llamada HTTP (GET /api/v3/ticker/24hr sin símbolo, weight=40) y actualiza
only current_price, volume_24h y price_change_24h en CryptoAsset.

Diferencias con SyncMarketDataUseCase (CoinGecko):
  - NO crea MarketDataSnapshot  → sin crecimiento extra de BD por minuto
  - NO actualiza market_cap, logo_url ni coingecko_id
  - NO consume cuota mensual de CoinGecko (30 req/min ni 10 000 calls/mes)
  - Se puede ejecutar cada 60 s sin ningún límite práctico

Activos sin par USDT en Binance (ej. USDT, USDC, stablecoins) son ignorados
silenciosamente; sus precios se actualizarán en el próximo sync CoinGecko.

Arquitectura dual de sincronización:
  · sync_prices_quick  (este UC)  →  cada  60 s  →  Binance  →  precios al minuto
  · SyncMarketDataUseCase         →  cada 300 s  →  CoinGecko →  market_cap + snapshots
"""

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction

from core.infrastructure.external_apis.binance_client import (
    BinanceClientError,
    BinancePublicClient,
)
from core.infrastructure.persistence.models import CryptoAsset

logger = logging.getLogger(__name__)


# ── DTO de resultado ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class QuickSyncResultDTO:
    """Estadísticas de la ejecución del sync rápido."""
    updated: int
    skipped: int
    errors: int


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _safe_decimal(value) -> Optional[Decimal]:
    """Convierte un valor a Decimal de forma segura; devuelve None si falla."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


# ── Caso de uso ─────────────────────────────────────────────────────────────────

class SyncPricesQuickUseCase:
    """
    Sincronización rápida de precios desde Binance ticker 24 h.

    Flujo de ejecución:
      1. GET /api/v3/ticker/24hr sin símbolo → devuelve ~2 000 pares (weight=40)
      2. Construir índice {symbol_binance: ticker_dict}
      3. Para cada CryptoAsset en BD: buscar "{SYMBOL}USDT" en el índice
      4. Mutar current_price, volume_24h, price_change_24h en memoria
      5. bulk_update de los activos modificados (1 query SQL con batch_size=100)

    La operación completa es segura para ejecutarse cada 60 s:
      - 1 HTTP call a Binance (weight 40 de 1200 disponibles por minuto)
      - 1 query SELECT a BD (assets)
      - 1 query UPDATE masivo (bulk_update)
    """

    def __init__(self, client: Optional[BinancePublicClient] = None) -> None:
        self._client = client or BinancePublicClient()

    def execute(self) -> QuickSyncResultDTO:
        # 1. Obtener todos los tickers de Binance en una sola llamada HTTP
        try:
            tickers: list = self._client.get_ticker_24hr()
        except BinanceClientError as exc:
            logger.error("SyncPricesQuickUseCase: error Binance: %s", exc)
            return QuickSyncResultDTO(updated=0, skipped=0, errors=1)

        if not isinstance(tickers, list) or not tickers:
            logger.warning("SyncPricesQuickUseCase: respuesta vacía o inesperada de Binance")
            return QuickSyncResultDTO(updated=0, skipped=0, errors=0)

        # 2. Indexar por símbolo en mayúsculas (ej. "BTCUSDT")
        ticker_map: dict[str, dict] = {
            t["symbol"]: t
            for t in tickers
            if isinstance(t, dict) and "symbol" in t
        }

        # 3. Cargar todos los assets de la BD (solo los campos necesarios)
        assets = list(
            CryptoAsset.objects.only(
                "id", "symbol", "current_price", "volume_24h", "price_change_24h"
            )
        )

        to_update: list[CryptoAsset] = []
        skipped = 0

        for asset in assets:
            binance_key = f"{asset.symbol.upper()}USDT"
            ticker = ticker_map.get(binance_key)

            if ticker is None:
                # Asset sin par USDT en Binance (stablecoin, token muy pequeño, etc.)
                skipped += 1
                continue

            price = _safe_decimal(ticker.get("lastPrice"))
            if price is None:
                skipped += 1
                continue

            # Mutar solo los campos disponibles
            asset.current_price = price

            volume = _safe_decimal(ticker.get("quoteVolume"))  # volumen en USDT
            if volume is not None:
                asset.volume_24h = volume

            pct_change = _safe_decimal(ticker.get("priceChangePercent"))
            if pct_change is not None:
                asset.price_change_24h = pct_change

            to_update.append(asset)

        # 4. Persistir en una sola transacción atómica
        errors = 0
        if to_update:
            try:
                with transaction.atomic():
                    CryptoAsset.objects.bulk_update(
                        to_update,
                        ["current_price", "volume_24h", "price_change_24h"],
                        batch_size=100,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "SyncPricesQuickUseCase: bulk_update fallido: %s", exc, exc_info=True
                )
                errors = len(to_update)
                return QuickSyncResultDTO(updated=0, skipped=skipped, errors=errors)

            # Empujar los precios actualizados a los clientes WebSocket (tiempo real).
            self._broadcast(to_update)

        logger.info(
            "SyncPricesQuickUseCase: updated=%d, skipped=%d, errors=%d",
            len(to_update), skipped, errors,
        )
        return QuickSyncResultDTO(updated=len(to_update), skipped=skipped, errors=errors)

    @staticmethod
    def _broadcast(assets: list[CryptoAsset]) -> None:
        """Emite los precios actualizados al stream WebSocket (tiempo real)."""
        from core.interfaces.ws.broadcast import broadcast_price_update

        items = [
            {
                "symbol": a.symbol,
                "price": float(a.current_price) if a.current_price is not None else None,
                "change": float(a.price_change_24h) if a.price_change_24h is not None else None,
            }
            for a in assets
        ]
        broadcast_price_update(items)
