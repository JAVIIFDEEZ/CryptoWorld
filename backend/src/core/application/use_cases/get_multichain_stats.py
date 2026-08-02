"""
get_multichain_stats.py — Caso de uso: estadísticas on-chain multi-chain.

Fuente: Blockchair API (gratuita, sin auth).
Chains soportadas: BTC, ETH, LTC, DOGE, BCH, XRP, ADA, DOT, XLM, XMR.

Devuelve un snapshot de estadísticas actuales (no series históricas).
Para series históricas de BTC usar GetOnChainMetricsUseCase (Blockchain.com).
"""

import logging
from typing import Optional

from core.infrastructure.external_apis.blockchair_client import (
    COMMON_FIELDS,
    ETH_EXTRA_FIELDS,
    SUPPORTED_SYMBOLS,
    BlockchairClient,
    BlockchairClientError,
)

logger = logging.getLogger(__name__)

# Formato de grandes números para las etiquetas de unidad
_FIELD_FORMATTERS: dict[str, str] = {
    "hashrate_24h": "TH/s",  # se convierte desde H/s
}


def _build_stat_item(key: str, label: str, unit: str, raw_value) -> dict:
    """Construye un ítem de estadística normalizado."""
    value = raw_value
    display_unit = unit

    # Conversión especial: hash rate de H/s a TH/s
    if key == "hashrate_24h" and isinstance(value, (int, float)) and value > 0:
        value = round(value / 1e12, 4)
        display_unit = "TH/s"

    # Conversión wei → ETH para burned_24h
    if key == "burned_24h" and isinstance(value, (int, float)) and value > 0:
        value = round(value / 1e18, 4)
        display_unit = "ETH"

    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": display_unit,
    }


class GetMultiChainStatsUseCase:
    """
    Devuelve estadísticas actuales (snapshot) de una blockchain.

    Soporta: BTC, ETH, LTC, DOGE, BCH, XRP, ADA, DOT, XLM, XMR.
    Para BTC también están disponibles series históricas via Blockchain.com.
    """

    def __init__(self, client: Optional[BlockchairClient] = None) -> None:
        self._client = client or BlockchairClient()

    def execute(self, symbol: str) -> dict:
        symbol = symbol.upper()

        if symbol not in SUPPORTED_SYMBOLS:
            return {
                "error": (
                    f"Chain '{symbol}' no soportada en estadísticas multi-chain. "
                    f"Disponibles: {SUPPORTED_SYMBOLS}"
                ),
                "supported": SUPPORTED_SYMBOLS,
                "stats": [],
            }

        try:
            raw = self._client.get_stats(symbol)
        except BlockchairClientError as exc:
            logger.warning("Blockchair no disponible para %s: %s", symbol, exc)
            return {
                "error": str(exc),
                "supported": SUPPORTED_SYMBOLS,
                "stats": [],
            }

        stats = []

        # Campos comunes a todas las chains
        for key, label, unit in COMMON_FIELDS:
            value = raw.get(key)
            if value is not None:
                stats.append(_build_stat_item(key, label, unit, value))

        # Campos extra para ETH
        if symbol == "ETH":
            for key, label, unit in ETH_EXTRA_FIELDS:
                value = raw.get(key)
                if value is not None:
                    stats.append(_build_stat_item(key, label, unit, value))

        # Extraer best_block_time como dato informativo
        best_block_time = raw.get("best_block_time")
        best_block_height = raw.get("best_block_height")

        return {
            "symbol": symbol,
            "source": "blockchair.com",
            "best_block_time": best_block_time,
            "best_block_height": best_block_height,
            "supported": SUPPORTED_SYMBOLS,
            "stats": stats,
        }

    def get_supported_symbols(self) -> list[str]:
        return SUPPORTED_SYMBOLS
