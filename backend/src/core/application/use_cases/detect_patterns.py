"""
detect_patterns.py — Caso de uso: Detección de patrones de velas japonesas.

Usa la cadena Binance → CoinGecko para obtener OHLCV.
"""

import logging

from core.application.dto.asset_dto import PatternsRequestDTO
from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
from core.domain.services.technical_analysis_service import detect_candle_patterns

logger = logging.getLogger(__name__)


class DetectPatternsUseCase:

    def execute(self, dto: PatternsRequestDTO) -> dict:
        symbol = dto.asset_symbol.upper()

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=dto.interval, limit=dto.limit)

        if result is None or result.df.empty or len(result.df) < 5:
            return {"patterns": [], "message": "Datos insuficientes."}

        patterns = detect_candle_patterns(result.df)
        return {
            "asset_symbol": symbol,
            "interval": dto.interval,
            "total_candles": len(result.df),
            "patterns": patterns,
            "data_source": result.source,
        }
