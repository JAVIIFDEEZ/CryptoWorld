"""
get_asset_ohlcv.py — Caso de uso: Obtener velas OHLCV reales.

Cadena de fuentes (Strategy Pattern):
  1. Binance (OHLCV + volumen, sin auth, 600 req/min)
  2. CoinGecko OHLC (OHLC sin volumen, 30 req/min)
  3. Si ambos fallan → error explícito (NO datos sintéticos)

El campo `source` en cada vela indica el proveedor de datos real.

Docs Binance klines:
  https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#klinecandlestick-data
Docs CoinGecko OHLC:
  https://docs.coingecko.com/reference/coins-id-ohlc
"""

import logging
from datetime import datetime, UTC
from typing import Optional

from core.application.dto.market_intelligence_dto import OhlcvCandleOutputDTO
from core.infrastructure.external_apis.binance_client import (
    BinancePublicClient,
    BinanceClientError,
)
from core.infrastructure.external_apis.coingecko_client import (
    CoinGeckoClient,
    CoinGeckoClientError,
)
from core.infrastructure.persistence.repositories_impl import DjangoCryptoAssetRepository

logger = logging.getLogger(__name__)

# Sufijo quote por defecto.
_QUOTE_CURRENCY = "USDT"

# Intervalos → minutos (para mapeo a CoinGecko days).
_INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "12h": 720,
    "1d": 1440,
    "1w": 10080,
}

# Mapeo interval + limit → days para CoinGecko OHLC.
# CoinGecko acepta: 1, 7, 14, 30, 90, 180, 365, "max"
_COINGECKO_VALID_DAYS = [1, 7, 14, 30, 90, 180, 365]


class OhlcvNotAvailableError(Exception):
    """Ninguna fuente de datos pudo servir OHLCV para el activo."""


class GetAssetOhlcvUseCase:
    """
    Devuelve velas OHLCV para un activo criptográfico.

    Estrategia: Binance → CoinGecko OHLC → error.
    Elimina completamente los datos sintéticos/falsos.
    """

    def __init__(
        self,
        binance_client: Optional[BinancePublicClient] = None,
        coingecko_client: Optional[CoinGeckoClient] = None,
        asset_repo: Optional[DjangoCryptoAssetRepository] = None,
    ) -> None:
        self._binance = binance_client or BinancePublicClient()
        self._coingecko = coingecko_client or CoinGeckoClient()
        self._asset_repo = asset_repo or DjangoCryptoAssetRepository()

    def execute(
        self, symbol: str, interval: str, limit: int
    ) -> tuple[list[OhlcvCandleOutputDTO], str]:
        """
        Devuelve (candles, source) donde source es "binance" o "coingecko".
        Lanza OhlcvNotAvailableError si ninguna fuente tiene datos.
        """
        symbol = symbol.upper()
        binance_interval = self._normalize_interval(interval)

        # ── 1. Intentar Binance ─────────────────────────────────
        candles = self._try_binance(symbol, binance_interval, limit)
        if candles:
            return candles, "binance"

        # ── 2. Fallback CoinGecko OHLC ─────────────────────────
        candles = self._try_coingecko(symbol, interval, limit)
        if candles:
            return candles, "coingecko"

        # ── 3. Ninguna fuente disponible ────────────────────────
        raise OhlcvNotAvailableError(
            f"No hay datos OHLCV disponibles para {symbol}. "
            f"El activo no se encuentra en Binance y no tiene coingecko_id configurado."
        )

    # ── Binance ────────────────────────────────────────────────────

    def _try_binance(
        self, symbol: str, interval: str, limit: int
    ) -> list[OhlcvCandleOutputDTO]:
        binance_symbol = f"{symbol}{_QUOTE_CURRENCY}"
        try:
            raw = self._binance.get_klines(
                symbol=binance_symbol, interval=interval, limit=limit,
            )
            candles = self._parse_binance_klines(raw)
            if candles:
                return candles
            logger.warning("Binance devolvió 0 velas para %s.", binance_symbol)
        except BinanceClientError as exc:
            logger.info(
                "Binance no tiene el par %s (%s). Probando CoinGecko...",
                binance_symbol, exc,
            )
        return []

    # ── CoinGecko ──────────────────────────────────────────────────

    def _try_coingecko(
        self, symbol: str, interval: str, limit: int
    ) -> list[OhlcvCandleOutputDTO]:
        # Buscar coingecko_id en BD
        asset = self._asset_repo.get_by_symbol(symbol)
        if not asset or not asset.coingecko_id:
            logger.warning(
                "No se encontró coingecko_id para %s. No se puede usar CoinGecko.", symbol
            )
            return []

        days = self._interval_limit_to_days(interval, limit)

        try:
            raw = self._coingecko.get_ohlc(
                coin_id=asset.coingecko_id,
                vs_currency="usd",
                days=days,
            )
            candles = self._parse_coingecko_ohlc(raw)
            if candles:
                logger.info(
                    "CoinGecko OHLC sirvió %d velas para %s (days=%s).",
                    len(candles), symbol, days,
                )
                return candles
        except CoinGeckoClientError as exc:
            logger.error("CoinGecko OHLC falló para %s: %s", symbol, exc)
        return []

    # ── Parsers ────────────────────────────────────────────────────

    @staticmethod
    def _parse_binance_klines(raw: list[list]) -> list[OhlcvCandleOutputDTO]:
        candles: list[OhlcvCandleOutputDTO] = []
        for row in raw:
            if len(row) < 6:
                continue
            candles.append(OhlcvCandleOutputDTO(
                open_time=datetime.fromtimestamp(row[0] / 1000, tz=UTC).isoformat(),
                open=str(row[1]),
                high=str(row[2]),
                low=str(row[3]),
                close=str(row[4]),
                volume=str(row[5]),
                source="binance",
            ))
        return candles

    @staticmethod
    def _parse_coingecko_ohlc(raw: list[list]) -> list[OhlcvCandleOutputDTO]:
        """
        CoinGecko OHLC: [[ts_ms, open, high, low, close], ...]
        No incluye volumen → se pone "0".
        """
        candles: list[OhlcvCandleOutputDTO] = []
        for row in raw:
            if len(row) < 5:
                continue
            candles.append(OhlcvCandleOutputDTO(
                open_time=datetime.fromtimestamp(row[0] / 1000, tz=UTC).isoformat(),
                open=str(row[1]),
                high=str(row[2]),
                low=str(row[3]),
                close=str(row[4]),
                volume="0",
                source="coingecko",
            ))
        return candles

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _normalize_interval(interval: str) -> str:
        return interval if interval in _INTERVAL_MINUTES else "1h"

    @staticmethod
    def _interval_limit_to_days(interval: str, limit: int) -> int | str:
        """
        Convierte interval + limit a 'days' para CoinGecko.
        Ej: interval=1h, limit=120 → 120h = 5 días → redondeamos a 7
        """
        minutes_per_candle = _INTERVAL_MINUTES.get(interval, 60)
        total_minutes = minutes_per_candle * limit
        total_days = total_minutes / 1440  # 1440 min = 1 día

        # Escoger el valor válido de CoinGecko más cercano (>= total_days)
        for d in _COINGECKO_VALID_DAYS:
            if d >= total_days:
                return d
        return 365
