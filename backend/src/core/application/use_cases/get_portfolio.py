"""
get_portfolio.py — Caso de uso: Obtener resumen del portfolio del usuario.

Calcula posiciones abiertas y métricas PnL a partir del historial de trades.
"""

import logging
from decimal import Decimal, InvalidOperation
from collections import defaultdict

from core.application.dto.portfolio_dto import PortfolioPositionDTO, PortfolioSummaryDTO
from core.infrastructure.persistence.models import TradeHistory, CryptoAsset

logger = logging.getLogger(__name__)


class GetPortfolioUseCase:
    """
    Calcula el portfolio actual a partir del historial de trades.

    Algoritmo:
      1. Agrupa todos los trades del usuario por activo.
      2. Para cada activo, calcula cantidad neta (BUY - SELL) y coste total.
      3. Obtiene precio actual del activo en BD.
      4. Calcula PnL (ganancia/pérdida) comparando coste vs valor actual.
    """

    def execute(self, user) -> PortfolioSummaryDTO:
        trades = (
            TradeHistory.objects.filter(user=user)
            .select_related("asset")
            .order_by("executed_at")
        )

        # Agrupar trades por activo
        by_asset: dict[str, dict] = defaultdict(
            lambda: {
                "asset": None,
                "quantity": Decimal("0"),
                "total_invested": Decimal("0"),
                "buy_quantity": Decimal("0"),
            }
        )

        for trade in trades:
            sym = trade.asset.symbol
            by_asset[sym]["asset"] = trade.asset
            if trade.trade_type == "BUY":
                by_asset[sym]["quantity"] += trade.quantity
                by_asset[sym]["total_invested"] += trade.total_usd
                by_asset[sym]["buy_quantity"] += trade.quantity
            elif trade.trade_type == "SELL":
                # Al vender, reducimos la posición proporcionalmente al coste
                if by_asset[sym]["buy_quantity"] > 0:
                    cost_per_unit = (
                        by_asset[sym]["total_invested"] / by_asset[sym]["buy_quantity"]
                    )
                    by_asset[sym]["total_invested"] -= trade.quantity * cost_per_unit
                by_asset[sym]["quantity"] -= trade.quantity

        positions = []
        total_invested = Decimal("0")
        total_current_value = Decimal("0")

        for sym, data in by_asset.items():
            qty = data["quantity"]
            if qty <= Decimal("0"):
                continue  # Posición cerrada

            asset: CryptoAsset = data["asset"]
            invested = max(data["total_invested"], Decimal("0"))
            current_price = asset.current_price or Decimal("0")
            current_value = qty * current_price
            pnl_usd = current_value - invested
            pnl_pct = (
                (pnl_usd / invested * 100) if invested > 0 else Decimal("0")
            )
            avg_buy_price = (
                invested / data["buy_quantity"] if data["buy_quantity"] > 0 else Decimal("0")
            )

            positions.append(
                PortfolioPositionDTO(
                    asset_symbol=sym,
                    asset_name=asset.name,
                    logo_url=asset.logo_url,
                    quantity=str(qty.normalize()),
                    avg_buy_price=f"{avg_buy_price:.8f}",
                    total_invested=f"{invested:.2f}",
                    current_price=f"{current_price:.8f}",
                    current_value=f"{current_value:.2f}",
                    pnl_usd=f"{pnl_usd:.2f}",
                    pnl_pct=f"{pnl_pct:.2f}",
                    is_profit=pnl_usd >= 0,
                )
            )

            total_invested += invested
            total_current_value += current_value

        total_pnl = total_current_value - total_invested
        total_pnl_pct = (
            (total_pnl / total_invested * 100) if total_invested > 0 else Decimal("0")
        )

        return PortfolioSummaryDTO(
            total_invested_usd=f"{total_invested:.2f}",
            total_current_value_usd=f"{total_current_value:.2f}",
            total_pnl_usd=f"{total_pnl:.2f}",
            total_pnl_pct=f"{total_pnl_pct:.2f}",
            positions=positions,
            is_profit=total_pnl >= 0,
        )
