"""
get_onchain_metrics.py — Caso de uso para métricas on-chain.
"""

from datetime import datetime, UTC, timedelta
from decimal import Decimal

from core.application.dto.market_intelligence_dto import OnChainMetricPointOutputDTO


class GetOnChainMetricsUseCase:
    """
    Devuelve serie temporal de una métrica on-chain.

    Implementación inicial contract-first. En producción se conectará a
    CoinMetrics (métricas agregadas) y opcionalmente Whale Alert (eventos).
    """

    def execute(self, symbol: str, metric: str, days: int) -> list[OnChainMetricPointOutputDTO]:
        symbol = symbol.upper()
        metric = metric.lower()
        now = datetime.now(UTC)

        base = Decimal("900000") if metric == "active_addresses" else Decimal("550")
        source = "coinmetrics-community"

        points: list[OnChainMetricPointOutputDTO] = []
        for i in range(days):
            points.append(
                OnChainMetricPointOutputDTO(
                    metric=metric,
                    symbol=symbol,
                    timestamp=(now - timedelta(days=(days - i))).isoformat(),
                    value=str(base + Decimal(i * 1300) if metric == "active_addresses" else base + Decimal(i * 2)),
                    source=source,
                )
            )

        return points
