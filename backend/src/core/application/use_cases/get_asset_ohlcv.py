"""
get_asset_ohlcv.py — Caso de uso: Obtener velas OHLCV reales desde Binance.

Flujo:
  1. Convierte el símbolo al formato de Binance (ej. "BTC" → "BTCUSDT")
  2. Llama a GET /api/v3/klines en data-api.binance.vision (sin auth)
  3. Parsea la respuesta: [ts, open, high, low, close, volume, ...]
  4. Si Binance no responde → fallback a datos sintéticos deterministas

Ventajas frente a CoinGecko OHLC:
  - Incluye volumen real (CoinGecko /ohlc no lo tiene)
  - Hasta 600 llamadas/min (vs. 30 de CoinGecko Demo)
  - No necesita API key

Docs Binance klines:
  https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#klinecandlestick-data
"""

import logging
from datetime import datetime, UTC, timedelta
from decimal import Decimal
from typing import Optional

from core.application.dto.market_intelligence_dto import OhlcvCandleOutputDTO
from core.infrastructure.external_apis.binance_client import (
    BinancePublicClient,
    BinanceClientError,
)

logger = logging.getLogger(__name__)

# Sufijo quote por defecto.  Cubre el 95 %+ de los pares del top-50.
_QUOTE_CURRENCY = "USDT"

# Intervalos que reconoce el frontend → se pasan directamente a Binance.
# Binance acepta todos estos nativamente (1m, 5m, 15m, 1h, 4h, 1d, …).
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


class GetAssetOhlcvUseCase:
    """
    Devuelve velas OHLCV para un activo criptográfico.

    Usa Binance como fuente primaria (OHLCV completo, sin API key).
    Si Binance falla, emite datos sintéticos deterministas como fallback
    para no romper el frontend mientras la API no está disponible.
    """

    def __init__(self, client: Optional[BinancePublicClient] = None) -> None:
        self._client = client or BinancePublicClient()

    def execute(self, symbol: str, interval: str, limit: int) -> list[OhlcvCandleOutputDTO]:
        symbol = symbol.upper()
        binance_symbol = self._to_binance_symbol(symbol)
        binance_interval = self._normalize_interval(interval)

        try:
            raw = self._client.get_klines(
                symbol=binance_symbol,
                interval=binance_interval,
                limit=limit,
            )
            candles = self._parse_klines(raw)
            if candles:
                return candles
            logger.warning(
                "Binance devolvió 0 velas para %s. Usando fallback.", binance_symbol
            )
        except BinanceClientError as exc:
            logger.warning(
                "Binance klines falló para %s (%s): %s. Usando fallback.",
                binance_symbol,
                interval,
                exc,
            )

        return self._synthetic_fallback(symbol, interval, limit)

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _to_binance_symbol(symbol: str) -> str:
        """
        Convierte el símbolo canónico al par de Binance con USDT.

        Ejemplos:
          "BTC"  → "BTCUSDT"
          "ETH"  → "ETHUSDT"
          "USDT" → "USDTUSDT"  (Binance no tiene este par; fallará → fallback)
        """
        return f"{symbol}{_QUOTE_CURRENCY}"

    @staticmethod
    def _normalize_interval(interval: str) -> str:
        """
        Devuelve el intervalo normalizado para Binance.
        Los intervalos del frontend (1m, 4h, 1d…) ya son compatibles;
        solo se sanea el caso en que llegue un valor desconocido.
        """
        return interval if interval in _INTERVAL_MINUTES else "1h"

    @staticmethod
    def _parse_klines(raw: list[list]) -> list[OhlcvCandleOutputDTO]:
        """
        Parsea la respuesta completa de /api/v3/klines.

        Formato Binance (índices):
          0  open_time   — int   timestamp apertura en ms
          1  open        — str   precio apertura
          2  high        — str   máximo
          3  low         — str   mínimo
          4  close       — str   precio cierre
          5  volume      — str   volumen base (ej. BTC)
          6  close_time  — int   timestamp cierre en ms
          7  quote_vol   — str   volumen quote (ej. USDT)
          …  (resto ignorado)
        """
        candles: list[OhlcvCandleOutputDTO] = []
        for row in raw:
            if len(row) < 6:
                continue
            ts_ms = row[0]
            candles.append(OhlcvCandleOutputDTO(
                open_time=datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat(),
                open=str(row[1]),
                high=str(row[2]),
                low=str(row[3]),
                close=str(row[4]),
                volume=str(row[5]),
            ))
        return candles

    @staticmethod
    def _synthetic_fallback(
        symbol: str, interval: str, limit: int
    ) -> list[OhlcvCandleOutputDTO]:
        """
        Datos sintéticos deterministas como último recurso.
        Mantiene el contrato del frontend cuando Binance no responde.
        """
        base_price = Decimal("62000") if symbol == "BTC" else Decimal("3200")
        now = datetime.now(UTC)
        interval_minutes = _INTERVAL_MINUTES.get(interval, 60)

        candles: list[OhlcvCandleOutputDTO] = []
        for i in range(limit):
            offset = limit - i
            close = base_price + Decimal(offset * 10)
            open_price = close - Decimal("35")
            high = close + Decimal("65")
            low = close - Decimal("75")
            volume = Decimal("1200") + Decimal(offset * 8)
            candles.append(OhlcvCandleOutputDTO(
                open_time=(now - timedelta(minutes=offset * interval_minutes)).isoformat(),
                open=str(open_price),
                high=str(high),
                low=str(low),
                close=str(close),
                volume=str(volume),
            ))
