"""
get_signals_dashboard.py — Caso de uso: Panel de señales multi-indicador.

Ejecuta todos los indicadores principales sobre un activo y devuelve
un resumen tipo TradingView con semáforos y veredicto global.
"""

import logging

import pandas as pd

from core.application.dto.asset_dto import SignalsRequestDTO
from core.infrastructure.external_apis.binance_client import (
    BinancePublicClient,
    BinanceClientError,
)
from core.domain.services.technical_analysis_service import calculate_signals_dashboard

logger = logging.getLogger(__name__)


class GetSignalsDashboardUseCase:

    def __init__(self, client: BinancePublicClient | None = None) -> None:
        self._client = client or BinancePublicClient()

    def execute(self, dto: SignalsRequestDTO) -> dict:
        symbol = dto.asset_symbol.upper()
        binance_symbol = f"{symbol}USDT"

        try:
            raw = self._client.get_klines(
                symbol=binance_symbol,
                interval=dto.interval,
                limit=dto.limit,
            )
            df = _klines_to_df(raw)

            if df.empty or len(df) < 50:
                return {"error": "Datos insuficientes para generar señales."}

            result = calculate_signals_dashboard(df)
            result["asset_symbol"] = symbol
            result["interval"] = dto.interval
            return result

        except BinanceClientError as exc:
            logger.error("Binance error en signals para %s: %s", symbol, exc)
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
