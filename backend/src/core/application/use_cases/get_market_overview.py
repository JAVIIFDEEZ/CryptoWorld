"""
get_market_overview.py — Caso de uso para resumen global de mercado.
"""

from datetime import datetime, UTC

from core.application.dto.market_intelligence_dto import MarketOverviewOutputDTO


class GetMarketOverviewUseCase:
    """
    Devuelve un resumen agregado del mercado.

    Nota: implementación inicial contract-first con valores de ejemplo.
    En la siguiente iteración se conectará a proveedores externos (CoinGecko).
    """

    def execute(self) -> MarketOverviewOutputDTO:
        return MarketOverviewOutputDTO(
            total_market_cap_usd="2450000000000",
            total_volume_24h_usd="156800000000",
            btc_dominance_pct="48.30",
            fear_greed_index=72,
            updated_at=datetime.now(UTC).isoformat(),
        )
