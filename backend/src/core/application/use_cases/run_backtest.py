"""
run_backtest.py — Caso de uso: Backtesting de estrategias de trading.

Usa la cadena Binance → CoinGecko para obtener OHLCV.
"""

import logging

from core.application.dto.asset_dto import BacktestRequestDTO
from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
from core.domain.services.technical_analysis_service import STRATEGIES, run_backtest

logger = logging.getLogger(__name__)


class RunBacktestUseCase:

    def execute(self, dto: BacktestRequestDTO) -> dict:
        symbol = dto.asset_symbol.upper()

        if dto.strategy not in STRATEGIES:
            return {
                "error": f"Estrategia '{dto.strategy}' no reconocida.",
                "available_strategies": list(STRATEGIES.keys()),
            }

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=dto.interval, limit=dto.limit)

        if result is None or result.df.empty or len(result.df) < 60:
            return {"error": "Se necesitan al menos 60 velas para backtesting."}

        backtest_result = run_backtest(result.df, dto.strategy, dto.initial_capital)
        backtest_result["asset_symbol"] = symbol
        backtest_result["interval"] = dto.interval
        backtest_result["data_source"] = result.source
        return backtest_result

    @staticmethod
    def get_available_strategies() -> list[dict]:
        return [
            {"key": k, "name": v["name"], "description": v["description"]}
            for k, v in STRATEGIES.items()
        ]
