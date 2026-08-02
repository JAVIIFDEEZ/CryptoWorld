"""
get_portfolio.py — Caso de uso: Obtener resumen del portfolio del usuario.

Calcula posiciones abiertas y métricas PnL a partir del historial de trades.
"""

import logging
from collections import defaultdict
from decimal import Decimal

from core.application.dto.portfolio_dto import PortfolioPositionDTO, PortfolioSummaryDTO
from core.infrastructure.persistence.models import CryptoAsset, TradeHistory

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
                "net_quantity": Decimal("0"),
                "buy_quantity": Decimal("0"),
                "sell_quantity": Decimal("0"),
                "total_invested": Decimal("0"),   # coste acumulado de compras
                "total_received": Decimal("0"),   # ingresos acumulados de ventas
            }
        )

        for trade in trades:
            sym = trade.asset.symbol
            by_asset[sym]["asset"] = trade.asset
            if trade.trade_type == "BUY":
                by_asset[sym]["net_quantity"] += trade.quantity
                by_asset[sym]["buy_quantity"] += trade.quantity
                by_asset[sym]["total_invested"] += trade.total_usd
            elif trade.trade_type == "SELL":
                by_asset[sym]["net_quantity"] -= trade.quantity
                by_asset[sym]["sell_quantity"] += trade.quantity
                by_asset[sym]["total_received"] += trade.total_usd

        positions = []
        total_invested = Decimal("0")
        total_current_value = Decimal("0")
        long_count = 0
        short_count = 0
        total_long_invested = Decimal("0")
        total_short_exposure = Decimal("0")

        for sym, data in by_asset.items():
            net_qty = data["net_quantity"]
            if net_qty == Decimal("0"):
                continue  # Posición completamente cerrada

            asset: CryptoAsset = data["asset"]
            current_price = asset.current_price or Decimal("0")

            if net_qty > Decimal("0"):
                # ── Posición LONG ──────────────────────────────────────────
                qty = net_qty
                buy_qty = data["buy_quantity"]
                avg_buy_price = (
                    data["total_invested"] / buy_qty if buy_qty > 0 else Decimal("0")
                )
                invested = avg_buy_price * qty
                current_value = qty * current_price
                pnl_usd = current_value - invested
                pnl_pct = (pnl_usd / invested * 100) if invested > 0 else Decimal("0")

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
                        position_type="LONG",
                    )
                )
                long_count += 1
                total_long_invested += invested
                total_invested += invested
                total_current_value += current_value

            else:
                # ── Posición SHORT (vendido sin compra suficiente) ─────────
                short_qty = abs(net_qty)
                sell_qty = data["sell_quantity"]
                avg_sell_price = (
                    data["total_received"] / sell_qty if sell_qty > 0 else Decimal("0")
                )
                # Ingreso proporcional a la parte descubierta
                received = avg_sell_price * short_qty
                # Coste de recompra al precio actual
                current_value = short_qty * current_price
                # PnL corto: ganamos si el precio baja
                pnl_usd = received - current_value
                pnl_pct = (pnl_usd / received * 100) if received > 0 else Decimal("0")

                positions.append(
                    PortfolioPositionDTO(
                        asset_symbol=sym,
                        asset_name=asset.name,
                        logo_url=asset.logo_url,
                        quantity=str(short_qty.normalize()),
                        avg_buy_price=f"{avg_sell_price:.8f}",  # precio medio de venta
                        total_invested=f"{received:.2f}",        # ingreso de la venta corta
                        current_price=f"{current_price:.8f}",
                        current_value=f"{current_value:.2f}",
                        pnl_usd=f"{pnl_usd:.2f}",
                        pnl_pct=f"{pnl_pct:.2f}",
                        is_profit=pnl_usd >= 0,
                        position_type="SHORT",
                    )
                )
                short_count += 1
                total_short_exposure += current_value
                total_invested += received
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
            long_count=long_count,
            short_count=short_count,
            total_long_invested_usd=f"{total_long_invested:.2f}",
            total_short_exposure_usd=f"{total_short_exposure:.2f}",
        )
