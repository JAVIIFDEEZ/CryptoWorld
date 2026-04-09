"""
detect_patterns.py — Caso de uso: Detección de patrones de velas japonesas.

Obtiene datos OHLCV y ejecuta el detector de patrones chartistas.
"""

import logging

import pandas as pd

from core.application.dto.asset_dto import PatternsRequestDTO
from core.infrastructure.external_apis.binance_client import (
    BinancePublicClient,
    BinanceClientError,
)
from core.domain.services.technical_analysis_service import detect_candle_patterns

logger = logging.getLogger(__name__)


class DetectPatternsUseCase:

    def __init__(self, client: BinancePublicClient | None = None) -> None:
        self._client = client or BinancePublicClient()

    def execute(self, dto: PatternsRequestDTO) -> dict:
        symbol = dto.asset_symbol.upper()
        binance_symbol = f"{symbol}USDT"

        try:
            raw = self._client.get_klines(
                symbol=binance_symbol,
                interval=dto.interval,
                limit=dto.limit,
            )
            df = _klines_to_df(raw)

            if df.empty or len(df) < 5:
                return {"patterns": [], "message": "Datos insuficientes."}

            patterns = detect_candle_patterns(df)
            return {
                "asset_symbol": symbol,
                "interval": dto.interval,
                "total_candles": len(df),
                "patterns": patterns,
            }

        except BinanceClientError as exc:
            logger.error("Binance error en patterns para %s: %s", symbol, exc)
            return {"error": f"Error de conexión con Binance: {exc}"}


def _klines_to_df(raw: list) -> pd.DataFrame:
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    return df[["open", "high", "low", "close", "volume"]].reset_index(drop=True)
