"""
get_chain_health.py — Caso de uso: salud de red y rastreador de gas.

Fuente: Blockscout API REST v2 (`/api/v2/stats`), por red.

Consolida el estado actual de una cadena: precios de gas (lento/medio/rápido en
Gwei), utilización de la red, tiempo medio de bloque, precio del nativo y totales
(transacciones, bloques, direcciones). Clasifica el coste de gas como
barato/normal/caro con umbrales específicos por red (en L2 el gas es órdenes de
magnitud menor que en Ethereum mainnet), para un aviso accionable de "buen
momento para operar".
"""

import logging
from typing import Optional

from core.infrastructure.external_apis.blockscout_client import (
    CHAINS,
    BlockscoutClient,
    BlockscoutClientError,
    SUPPORTED_CHAINS,
)

logger = logging.getLogger(__name__)


def _to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class GetChainHealthUseCase:
    """Salud de red + rastreador de gas de una cadena soportada."""

    def __init__(self, client: Optional[BlockscoutClient] = None) -> None:
        self._client = client or BlockscoutClient()

    def execute(self, chain: str) -> dict:
        chain = (chain or "").strip().lower()
        if chain not in SUPPORTED_CHAINS:
            return {"error": f"Red '{chain}' no soportada. Disponibles: {SUPPORTED_CHAINS}"}

        try:
            stats = self._client.get_chain_stats(chain)
        except BlockscoutClientError as exc:
            logger.warning("chain_health %s: %s", chain, exc)
            return {"error": str(exc)}

        meta = CHAINS[chain]
        gas = stats.get("gas_prices") or {}
        gas_slow = _to_float(gas.get("slow"))
        gas_avg = _to_float(gas.get("average"))
        gas_fast = _to_float(gas.get("fast"))

        gas_level, gas_text = self._classify_gas(gas_avg, meta)
        block_time_ms = _to_float(stats.get("average_block_time"))

        return {
            "chain": chain,
            "chain_name": meta["name"],
            "native_symbol": meta["native"],
            "explorer_url": meta["base_url"],
            "gas_slow": gas_slow,
            "gas_average": gas_avg,
            "gas_fast": gas_fast,
            "gas_level": gas_level,          # cheap | normal | high | unknown
            "gas_text": gas_text,
            "gas_unit": "Gwei",
            "gas_updated_at": stats.get("gas_price_updated_at"),
            "network_utilization_pct": _to_float(stats.get("network_utilization_percentage")),
            "block_time_sec": round(block_time_ms / 1000.0, 2) if block_time_ms else None,
            "coin_price_usd": _to_float(stats.get("coin_price")),
            "coin_price_change_pct": _to_float(stats.get("coin_price_change_percentage")),
            "total_transactions": stats.get("total_transactions"),
            "total_blocks": stats.get("total_blocks"),
            "total_addresses": stats.get("total_addresses"),
            "transactions_today": stats.get("transactions_today"),
            "source": "blockscout",
        }

    @staticmethod
    def _classify_gas(gas_avg, meta) -> tuple[str, str]:
        """Clasifica el gas medio como barato/normal/caro según la red."""
        if gas_avg is None:
            return "unknown", "Precio de gas no disponible."
        cheap = meta.get("gas_cheap", 10.0)
        high = meta.get("gas_high", 30.0)
        if gas_avg <= cheap:
            return "cheap", f"Gas barato ({gas_avg:g} Gwei): buen momento para operar."
        if gas_avg >= high:
            return "high", f"Gas caro ({gas_avg:g} Gwei): conviene esperar si no es urgente."
        return "normal", f"Gas en niveles normales ({gas_avg:g} Gwei)."
