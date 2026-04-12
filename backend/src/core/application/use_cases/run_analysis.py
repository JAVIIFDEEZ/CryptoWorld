"""run_analysis.py — Caso de uso: Ejecutar análisis técnico con cálculos reales.

Obtiene datos OHLCV (Binance → CoinGecko) y calcula el indicador solicitado.
"""

import logging

from core.application.dto.asset_dto import AnalysisRequestInputDTO, AnalysisOutputDTO
from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
from core.domain.services.technical_analysis_service import calculate_indicator

logger = logging.getLogger(__name__)


class RunAnalysisUseCase:
    """
    Caso de uso: calcular un indicador técnico individual.
    Usa la cadena Binance → CoinGecko para obtener OHLCV.
    """

    def execute(self, input_dto: AnalysisRequestInputDTO) -> AnalysisOutputDTO:
        symbol = input_dto.asset_symbol.upper()
        interval = getattr(input_dto, "interval", "1h") or "1h"
        limit = getattr(input_dto, "limit", 300) or 300

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=limit)

        if result is None or result.df.empty or len(result.df) < 20:
            return AnalysisOutputDTO(
                id=0,
                asset_symbol=symbol,
                analysis_type=input_dto.analysis_type,
                status="failed",
                result={"error": "Datos insuficientes o activo no disponible."},
            )

        indicator_result = calculate_indicator(result.df, input_dto.analysis_type)
        indicator_result["data_source"] = result.source

        return AnalysisOutputDTO(
            id=0,
            asset_symbol=symbol,
            analysis_type=input_dto.analysis_type,
            status="completed",
            result=indicator_result,
        )
