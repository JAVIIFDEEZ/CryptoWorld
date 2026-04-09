"""
run_backtest.py — Caso de uso: Backtesting de estrategias de trading.

Obtiene datos OHLCV históricos, ejecuta una estrategia predefinida
sobre ellos y devuelve métricas de rendimiento.
"""

import logging

import pandas as pd

from core.application.dto.asset_dto import BacktestRequestDTO
from core.infrastructure.external_apis.binance_client import (
    BinancePublicClient,
    BinanceClientError,
)
from core.domain.services.technical_analysis_service import run_backtest, STRATEGIES

logger = logging.getLogger(__name__)


class RunBacktestUseCase:

    def __init__(self, client: BinancePublicClient | None = None) -> None:
        self._client = client or BinancePublicClient()

    def execute(self, dto: BacktestRequestDTO) -> dict:
        symbol = dto.asset_symbol.upper()
        binance_symbol = f"{symbol}USDT"

        if dto.strategy not in STRATEGIES:
            return {
                "error": f"Estrategia '{dto.strategy}' no reconocida.",
                "available_strategies": list(STRATEGIES.keys()),
            }

        try:
            raw = self._client.get_klines(
                symbol=binance_symbol,
                interval=dto.interval,
                limit=dto.limit,
            )
            df = _klines_to_df(raw)

            if df.empty or len(df) < 60:
                return {"error": "Se necesitan al menos 60 velas para backtesting."}

            result = run_backtest(df, dto.strategy, dto.initial_capital)
            result["asset_symbol"] = symbol
            result["interval"] = dto.interval
            return result

        except BinanceClientError as exc:
            logger.error("Binance error en backtest para %s: %s", symbol, exc)
            return {"error": f"Error de conexión con Binance: {exc}"}

    @staticmethod
    def get_available_strategies() -> list[dict]:
        return [
            {"key": k, "name": v["name"], "description": v["description"]}
            for k, v in STRATEGIES.items()
        ]


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
