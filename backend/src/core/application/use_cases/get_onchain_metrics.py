"""
get_onchain_metrics.py — Caso de uso para métricas on-chain de Bitcoin.

Fuente: Blockchain.com Charts API (gratuita, sin auth).
Solo cubre Bitcoin (BTC). Para ETH y otras chains habría que integrar
APIs adicionales (Etherscan, Blockchair, etc.).
Docs: https://www.blockchain.com/explorer/api/charts_api
"""

import logging
from datetime import datetime, UTC
from typing import Optional

from core.application.dto.market_intelligence_dto import OnChainMetricPointOutputDTO
from core.infrastructure.external_apis.blockchain_dot_com_client import (
    BlockchainDotComClient,
    BlockchainDotComClientError,
    METRIC_MAP,
    METRIC_LABELS,
)

logger = logging.getLogger(__name__)

# Timespan mapping: days → API timespan
_TIMESPAN_MAP = {
    7: "7days",
    14: "14days",
    30: "30days",
    60: "60days",
    90: "90days",
    180: "180days",
    365: "1year",
}


def _days_to_timespan(days: int) -> str:
    """Convierte el número de días al formato de timespan de la API."""
    # Buscar el valor más cercano hacia arriba
    for threshold, ts in sorted(_TIMESPAN_MAP.items()):
        if days <= threshold:
            return ts
    return "1year"


class GetOnChainMetricsUseCase:
    """
    Devuelve serie temporal de una métrica on-chain de Bitcoin.

    Métricas disponibles:
      - active_addresses  → Direcciones activas por día
      - hashrate          → Hash rate de la red (TH/s)
      - tx_count          → Transacciones por día
      - difficulty        → Dificultad de minado
      - mempool_size      → Tamaño del mempool
      - miners_revenue    → Ingresos mineros (USD)
      - transaction_fees  → Comisiones totales (BTC)
      - avg_block_size    → Tamaño medio de bloque

    Si el símbolo no es BTC, devuelve error informativo.
    """

    def __init__(self, client: Optional[BlockchainDotComClient] = None) -> None:
        self._client = client or BlockchainDotComClient()

    def execute(self, symbol: str, metric: str, days: int) -> dict:
        symbol = symbol.upper()

        # Por ahora solo BTC está soportado por Blockchain.com
        if symbol != "BTC":
            return {
                "error": f"Métricas on-chain solo disponibles para BTC actualmente. Solicitado: {symbol}.",
                "supported": ["BTC"],
                "points": [],
            }

        metric = metric.lower()
        if metric not in METRIC_MAP:
            return {
                "error": f"Métrica '{metric}' no soportada.",
                "available_metrics": list(METRIC_MAP.keys()),
                "points": [],
            }

        timespan = _days_to_timespan(days)

        try:
            raw = self._client.get_chart(metric=metric, timespan=timespan)
        except BlockchainDotComClientError as exc:
            logger.warning("Blockchain.com no disponible: %s", exc)
            return {
                "error": "API on-chain temporalmente no disponible.",
                "points": [],
            }

        values = raw.get("values", [])
        points: list[OnChainMetricPointOutputDTO] = []

        for point in values:
            ts = point.get("x", 0)
            val = point.get("y")
            if val is None:
                continue
            try:
                timestamp = datetime.fromtimestamp(ts, UTC).isoformat()
            except (TypeError, OSError):
                timestamp = datetime.now(UTC).isoformat()

            points.append(
                OnChainMetricPointOutputDTO(
                    metric=metric,
                    symbol=symbol,
                    timestamp=timestamp,
                    value=str(val),
                    source="blockchain.com",
                )
            )

        return {
            "symbol": symbol,
            "metric": metric,
            "metric_label": METRIC_LABELS.get(metric, metric),
            "description": raw.get("description", ""),
            "timespan": timespan,
            "total_points": len(points),
            "points": points,
            "source": "blockchain.com",
        }
