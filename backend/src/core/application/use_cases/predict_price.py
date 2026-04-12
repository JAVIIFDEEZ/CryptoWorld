"""
predict_price.py — Caso de uso: Predicción de dirección de precio con ML.

Usa la cadena Binance → CoinGecko para obtener OHLCV.
"""

import logging

from core.application.dto.asset_dto import PredictionRequestDTO
from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
from core.domain.services.technical_analysis_service import predict_price_direction

logger = logging.getLogger(__name__)


class PredictPriceUseCase:

    def execute(self, dto: PredictionRequestDTO) -> dict:
        symbol = dto.asset_symbol.upper()

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=dto.interval, limit=dto.limit)

        if result is None or result.df.empty or len(result.df) < 100:
            return {
                "prediction": "INSUFFICIENT_DATA",
                "confidence": 0,
                "message": "Se necesitan al menos 100 velas.",
            }

        prediction = predict_price_direction(result.df, horizon=dto.horizon)
        prediction["asset_symbol"] = symbol
        prediction["interval"] = dto.interval
        prediction["data_source"] = result.source
        return prediction
