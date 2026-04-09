"""
predict_price.py — Caso de uso: Predicción de dirección de precio con ML.

Obtiene datos OHLCV, calcula features técnicos, entrena un modelo
Random Forest y predice la dirección del precio.
"""

import logging

import pandas as pd

from core.application.dto.asset_dto import PredictionRequestDTO
from core.infrastructure.external_apis.binance_client import (
    BinancePublicClient,
    BinanceClientError,
)
from core.domain.services.technical_analysis_service import predict_price_direction

logger = logging.getLogger(__name__)


class PredictPriceUseCase:

    def __init__(self, client: BinancePublicClient | None = None) -> None:
        self._client = client or BinancePublicClient()

    def execute(self, dto: PredictionRequestDTO) -> dict:
        symbol = dto.asset_symbol.upper()
        binance_symbol = f"{symbol}USDT"

        try:
            raw = self._client.get_klines(
                symbol=binance_symbol,
                interval=dto.interval,
                limit=dto.limit,
            )
            df = _klines_to_df(raw)

            if df.empty or len(df) < 100:
                return {
                    "prediction": "INSUFFICIENT_DATA",
                    "confidence": 0,
                    "message": "Se necesitan al menos 100 velas.",
                }

            result = predict_price_direction(df, horizon=dto.horizon)
            result["asset_symbol"] = symbol
            result["interval"] = dto.interval
            return result

        except BinanceClientError as exc:
            logger.error("Binance error en predict para %s: %s", symbol, exc)
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
