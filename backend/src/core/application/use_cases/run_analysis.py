"""
run_analysis.py — Caso de uso: Ejecutar análisis técnico con cálculos reales.

Obtiene datos OHLCV de Binance, calcula el indicador solicitado usando
pandas-ta, y devuelve los resultados numéricos reales con interpretación.
"""

import logging

import pandas as pd

from core.application.dto.asset_dto import AnalysisRequestInputDTO, AnalysisOutputDTO
from core.infrastructure.external_apis.binance_client import (
    BinancePublicClient,
    BinanceClientError,
)
from core.domain.services.technical_analysis_service import calculate_indicator

logger = logging.getLogger(__name__)


class RunAnalysisUseCase:
    """
    Caso de uso: calcular un indicador técnico individual sobre un activo.

    Flujo:
      1. Obtiene velas OHLCV de Binance.
      2. Las convierte a DataFrame de pandas.
      3. Ejecuta el cálculo del indicador solicitado.
      4. Devuelve el resultado con valores reales y señal.
    """

    def __init__(self, client: BinancePublicClient | None = None) -> None:
        self._client = client or BinancePublicClient()

    def execute(self, input_dto: AnalysisRequestInputDTO) -> AnalysisOutputDTO:
        symbol = input_dto.asset_symbol.upper()
        binance_symbol = f"{symbol}USDT"
        interval = getattr(input_dto, "interval", "1h") or "1h"
        limit = getattr(input_dto, "limit", 300) or 300

        try:
            raw = self._client.get_klines(
                symbol=binance_symbol,
                interval=interval,
                limit=limit,
            )
            df = self._klines_to_dataframe(raw)

            if df.empty or len(df) < 20:
                return AnalysisOutputDTO(
                    id=0,
                    asset_symbol=symbol,
                    analysis_type=input_dto.analysis_type,
                    status="failed",
                    result={"error": "Datos insuficientes para el análisis."},
                )

            result = calculate_indicator(df, input_dto.analysis_type)

            return AnalysisOutputDTO(
                id=0,
                asset_symbol=symbol,
                analysis_type=input_dto.analysis_type,
                status="completed",
                result=result,
            )

        except BinanceClientError as exc:
            logger.error("Error obteniendo datos de Binance para %s: %s", symbol, exc)
            return AnalysisOutputDTO(
                id=0,
                asset_symbol=symbol,
                analysis_type=input_dto.analysis_type,
                status="failed",
                result={"error": f"Error de conexión con Binance: {exc}"},
            )

    @staticmethod
    def _klines_to_dataframe(raw: list) -> pd.DataFrame:
        """Convierte klines de Binance a DataFrame OHLCV."""
        df = pd.DataFrame(raw, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "num_trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ])
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close", "volume"])
        return df[["open", "high", "low", "close", "volume"]].reset_index(drop=True)
