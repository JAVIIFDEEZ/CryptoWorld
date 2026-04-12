"""
get_signals_dashboard.py — Caso de uso: Panel de señales multi-indicador.

Usa la cadena Binance → CoinGecko para obtener OHLCV.
"""

import logging

from core.application.dto.asset_dto import SignalsRequestDTO
from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
from core.domain.services.technical_analysis_service import calculate_signals_dashboard

logger = logging.getLogger(__name__)


class GetSignalsDashboardUseCase:

    def execute(self, dto: SignalsRequestDTO) -> dict:
        symbol = dto.asset_symbol.upper()

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=dto.interval, limit=dto.limit)

        if result is None or result.df.empty or len(result.df) < 50:
            return {"error": "Datos insuficientes para generar señales."}

        dashboard = calculate_signals_dashboard(result.df)
        dashboard["asset_symbol"] = symbol
        dashboard["interval"] = dto.interval
        dashboard["data_source"] = result.source
        return dashboard
