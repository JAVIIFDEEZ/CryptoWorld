"""
get_derivatives.py — Caso de uso: microestructura de derivados de un activo.

Mapea el símbolo del activo a su perpetuo USDⓈ-M (BTC → BTCUSDT), consulta
premiumIndex + openInterest y devuelve el snapshot del dominio. Best-effort:
si el activo no tiene perpetuo o la API falla, devuelve ``available=False``.
"""

from __future__ import annotations

import logging

from core.domain.services.derivatives_metrics import compute_derivatives_snapshot

logger = logging.getLogger(__name__)


class GetDerivativesUseCase:
    """Microestructura de perpetuos (funding / basis / OI) de un activo."""

    def execute(self, asset_symbol: str) -> dict:
        symbol = (asset_symbol or "").upper().strip()
        if not symbol:
            return {"available": False, "note": "Falta el símbolo del activo."}

        pair = symbol if symbol.endswith("USDT") else f"{symbol}USDT"

        from core.infrastructure.external_apis.binance_client import (
            BinancePublicClient, BinanceClientError,
        )
        client = BinancePublicClient()
        try:
            premium = client.premium_index(pair)
            open_interest = client.open_interest(pair)
        except BinanceClientError as exc:
            logger.warning("derivados %s no disponibles: %s", pair, exc)
            return {"available": False, "symbol": symbol, "perp_symbol": pair,
                    "note": "Este activo no tiene perpetuo USDⓈ-M o la fuente no responde."}

        snapshot = compute_derivatives_snapshot(premium, open_interest)
        snapshot["symbol"] = symbol
        snapshot["perp_symbol"] = pair
        return snapshot
