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

    def execute(self, dto: PredictionRequestDTO, owner=None) -> dict:
        from django.core.cache import cache
        from core.application.use_cases.track_predictions import log_prediction

        symbol = dto.asset_symbol.upper()

        # El entrenamiento del ensemble + walk-forward + calibración es caro y los
        # datos cambian despacio: cachear el resultado evita recomputarlo en cada
        # recarga (≈ "persistir el modelo" sin serializar el estimador).
        cache_key = f"ml_predict:{symbol}:{dto.interval}:{dto.horizon}"
        cached = cache.get(cache_key)
        if cached is not None:
            log_prediction(cached, symbol, dto.interval, dto.horizon,
                           last_close=cached.get("_last_close", 0.0), owner=owner)
            return {k: v for k, v in cached.items() if k != "_last_close"}

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

        last_close = float(result.df["close"].iloc[-1])
        cache.set(cache_key, {**prediction, "_last_close": last_close}, 900)  # 15 min

        # Registrar la predicción para verificarla cuando transcurra el horizonte.
        log_prediction(prediction, symbol, dto.interval, dto.horizon, last_close=last_close, owner=owner)
        return prediction
