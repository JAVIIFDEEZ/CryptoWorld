"""
blockchain_dot_com_client.py — Adaptador para la API pública de Blockchain.com.

Blockchain.com ofrece datos on-chain de Bitcoin sin autenticación.
Endpoint base: https://api.blockchain.info/charts/

Métricas disponibles (todas para BTC):
  - active-addresses     → Direcciones activas por día
  - hash-rate            → Hash rate de la red (TH/s)
  - n-transactions       → Número de transacciones por día
  - difficulty           → Dificultad de minado
  - mempool-size         → Tamaño del mempool (bytes)
  - avg-block-size       → Tamaño medio de bloque (MB)
  - miners-revenue       → Ingresos mineros (USD/día)
  - transaction-fees     → Comisiones totales (BTC/día)

Docs: https://www.blockchain.com/explorer/api/charts_api

Rate limit: No documentado, pero ~100 req/min razonable.
Sin API key necesaria.

Principio aplicado: Adapter Pattern (Arquitectura Hexagonal).
"""

import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

BLOCKCHAIN_BASE_URL = "https://api.blockchain.info/charts"
REQUEST_TIMEOUT = 12  # segundos

# Mapeo de nombres internos a nombres de la API
METRIC_MAP = {
    "active_addresses": "n-unique-addresses",
    "hashrate": "hash-rate",
    "tx_count": "n-transactions",
    "difficulty": "difficulty",
    "mempool_size": "mempool-size",
    "miners_revenue": "miners-revenue",
    "transaction_fees": "transaction-fees",
    "avg_block_size": "avg-block-size",
}

# Etiquetas legibles para el frontend
METRIC_LABELS = {
    "active_addresses": "Direcciones Activas",
    "hashrate": "Hash Rate (TH/s)",
    "tx_count": "Transacciones/día",
    "difficulty": "Dificultad",
    "mempool_size": "Tamaño Mempool (bytes)",
    "miners_revenue": "Ingresos Mineros (USD)",
    "transaction_fees": "Comisiones (BTC)",
    "avg_block_size": "Tamaño Medio Bloque (MB)",
}


class BlockchainDotComClientError(Exception):
    """Error al comunicarse con la API de Blockchain.com."""


class BlockchainDotComClient:
    """
    Cliente HTTP para la API pública de Blockchain.com.

    Solo cubre Bitcoin (BTC). No requiere autenticación.

    Uso:
        client = BlockchainDotComClient()
        data = client.get_chart("active_addresses", timespan="30days")
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def get_chart(
        self,
        metric: str,
        timespan: str = "30days",
        rolling_average: str | None = None,
    ) -> dict[str, Any]:
        """
        GET /charts/<metric-name> — Serie temporal de una métrica BTC.

        Args:
            metric: Nombre interno del métrico (ver METRIC_MAP).
            timespan: Ventana temporal ("7days", "30days", "90days", "1year", "all").
            rolling_average: Media móvil opcional ("24hours", "1week", ...). Si es
                None no se envía el parámetro, evitando que la API devuelva 0 puntos
                en ventanas cortas (≤ 7 days).

        Returns:
            Dict con name, description, period, values (lista de {x: ts, y: valor}).
        """
        api_metric = METRIC_MAP.get(metric)
        if api_metric is None:
            raise BlockchainDotComClientError(
                f"Métrica '{metric}' no soportada. "
                f"Disponibles: {list(METRIC_MAP.keys())}"
            )

        params: dict[str, str] = {
            "timespan": timespan,
            "format": "json",
        }
        if rolling_average:
            params["rollingAverage"] = rolling_average

        try:
            resp = self._session.get(
                f"{BLOCKCHAIN_BASE_URL}/{api_metric}",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.Timeout:
            raise BlockchainDotComClientError(
                "Timeout al conectar con Blockchain.com."
            )
        except requests.exceptions.RequestException as exc:
            raise BlockchainDotComClientError(f"Error de red: {exc}") from exc

    def get_stats(self) -> dict[str, Any]:
        """
        GET /stats — Estadísticas actuales de la red Bitcoin.

        Incluye: market_price_usd, hash_rate, total_fees_btc,
                 n_btc_mined, n_tx, n_blocks_mined, etc.
        """
        try:
            resp = self._session.get(
                "https://api.blockchain.info/stats",
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            raise BlockchainDotComClientError(f"Error de red: {exc}") from exc
