"""
get_asset_ohlcv.py — Caso de uso para velas OHLCV por activo.
"""

from datetime import datetime, UTC, timedelta
from decimal import Decimal

from core.application.dto.market_intelligence_dto import OhlcvCandleOutputDTO


class GetAssetOhlcvUseCase:
    """
    Devuelve velas OHLCV para un activo.

    Implementación inicial con datos sintéticos deterministas para validar
    contrato de API y visualizaciones del frontend.
    """

    def execute(self, symbol: str, interval: str, limit: int) -> list[OhlcvCandleOutputDTO]:
        symbol = symbol.upper()
        base_price = Decimal("62000") if symbol == "BTC" else Decimal("3200")
        now = datetime.now(UTC)
        interval_minutes = {
            "1m": 1,
            "5m": 5,
            "15m": 15,
            "1h": 60,
            "4h": 240,
            "1d": 1440,
        }.get(interval, 60)

        candles: list[OhlcvCandleOutputDTO] = []
        for i in range(limit):
            offset = limit - i
            close = base_price + Decimal(offset * 10)
            open_price = close - Decimal("35")
            high = close + Decimal("65")
            low = close - Decimal("75")
            volume = Decimal("1200") + Decimal(offset * 8)

            candles.append(
                OhlcvCandleOutputDTO(
                    open_time=(now - timedelta(minutes=offset * interval_minutes)).isoformat(),
                    open=str(open_price),
                    high=str(high),
                    low=str(low),
                    close=str(close),
                    volume=str(volume),
                )
            )

        return candles
