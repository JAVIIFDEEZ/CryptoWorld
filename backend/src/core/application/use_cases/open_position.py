"""
open_position.py — Caso de uso: Abrir una nueva posición (LONG o SHORT).
"""

from decimal import Decimal
from datetime import datetime, timezone

from core.application.dto.portfolio_dto import OpenPositionInputDTO, PositionDTO
from core.infrastructure.persistence.models import (
    CryptoAsset,
    Position,
    TradeHistory,
    User,
)


def _build_position_dto(position: Position, current_price: Decimal) -> PositionDTO:
    avg = position.avg_entry_price
    qty = position.open_quantity

    if position.direction == "LONG":
        unrealized = (current_price - avg) * qty
    else:  # SHORT
        unrealized = (avg - current_price) * qty

    if avg != 0 and qty != 0:
        cost_basis = avg * qty
        unrealized_pct = (unrealized / cost_basis * 100) if cost_basis else Decimal("0")
    else:
        unrealized_pct = Decimal("0")

    total_pnl = position.realized_pnl + unrealized
    is_profit = total_pnl >= 0

    return PositionDTO(
        id=position.pk,
        asset_symbol=position.asset.symbol,
        asset_name=position.asset.name,
        logo_url=position.asset.logo_url,
        direction=position.direction,
        status=position.status,
        label=position.label,
        avg_entry_price=str(avg),
        open_quantity=str(qty),
        initial_quantity=str(position.initial_quantity),
        current_price=str(current_price),
        unrealized_pnl_usd=str(unrealized.quantize(Decimal("0.01"))),
        unrealized_pnl_pct=str(unrealized_pct.quantize(Decimal("0.01"))),
        realized_pnl_usd=str(position.realized_pnl),
        total_pnl_usd=str(total_pnl.quantize(Decimal("0.01"))),
        is_profit=is_profit,
        opened_at=position.opened_at.isoformat(),
        closed_at=position.closed_at.isoformat() if position.closed_at else None,
        trades_count=position.trades.count(),
    )


class OpenPositionUseCase:
    """
    Abre una nueva posición LONG o SHORT sobre un activo del usuario.

    Cada llamada crea una posición independiente (modo hedge):
    es posible tener varias posiciones LONG y SHORT simultáneas sobre el mismo activo.
    """

    def execute(self, user: User, dto: OpenPositionInputDTO) -> PositionDTO:
        try:
            asset = CryptoAsset.objects.get(symbol=dto.asset_symbol.upper())
        except CryptoAsset.DoesNotExist:
            raise ValueError(f"El activo '{dto.asset_symbol}' no está disponible en la plataforma.")

        if dto.quantity <= 0:
            raise ValueError("La cantidad debe ser mayor que cero.")
        if dto.entry_price <= 0:
            raise ValueError("El precio de entrada debe ser mayor que cero.")
        if dto.direction not in ("LONG", "SHORT"):
            raise ValueError("La dirección debe ser 'LONG' o 'SHORT'.")

        qty = Decimal(str(dto.quantity))
        price = Decimal(str(dto.entry_price))

        try:
            opened_at = datetime.fromisoformat(dto.opened_at)
        except ValueError:
            raise ValueError("Formato de fecha inválido. Usa ISO 8601.")

        # Normalizar a UTC aware si no tiene timezone
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)

        position = Position.objects.create(
            user=user,
            asset=asset,
            direction=dto.direction,
            status="OPEN",
            label=dto.label,
            avg_entry_price=price,
            open_quantity=qty,
            initial_quantity=qty,
            realized_pnl=Decimal("0"),
            opened_at=opened_at,
        )

        # trade_type: LONG abre con BUY, SHORT abre con SELL
        trade_type = "BUY" if dto.direction == "LONG" else "SELL"

        TradeHistory.objects.create(
            user=user,
            asset=asset,
            position=position,
            trade_type=trade_type,
            trade_intent="OPEN",
            quantity=qty,
            price_usd=price,
            total_usd=(qty * price).quantize(Decimal("0.00000001")),
            notes=dto.notes,
            executed_at=opened_at,
        )

        current_price = Decimal(str(asset.current_price or price))
        return _build_position_dto(position, current_price)
