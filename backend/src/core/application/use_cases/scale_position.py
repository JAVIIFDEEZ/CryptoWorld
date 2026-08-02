"""
scale_position.py — Caso de uso: Ampliar una posición existente (AVCO).
"""

from decimal import Decimal
from datetime import datetime, timezone

from core.application.dto.portfolio_dto import AddToPositionInputDTO, PositionDTO
from core.infrastructure.persistence.models import Position, TradeHistory, User
from core.application.use_cases.open_position import _build_position_dto


class ScalePositionUseCase:
    """
    Amplía una posición abierta añadiendo más cantidad al precio indicado.

    Recalcula el precio medio de entrada (AVCO):
        new_avg = (old_qty * old_avg + add_qty * add_price) / (old_qty + add_qty)
    """

    def execute(
        self, user: User, position_id: int, dto: AddToPositionInputDTO
    ) -> PositionDTO:
        try:
            position = Position.objects.select_related("asset").get(
                pk=position_id, user=user
            )
        except Position.DoesNotExist:
            raise ValueError("Posición no encontrada.")

        if position.status == "CLOSED":
            raise ValueError("No se puede ampliar una posición ya cerrada.")

        # El DTO ya transporta Decimal (el serializer valida con
        # DecimalField); no hay conversion desde float que redondee.
        add_qty = dto.quantity
        add_price = dto.entry_price

        if add_qty <= 0:
            raise ValueError("La cantidad a añadir debe ser mayor que cero.")
        if add_price <= 0:
            raise ValueError("El precio debe ser mayor que cero.")

        try:
            executed_at = datetime.fromisoformat(dto.executed_at)
        except ValueError:
            raise ValueError("Formato de fecha inválido. Usa ISO 8601.")

        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=timezone.utc)

        # Recálculo AVCO
        old_qty = position.open_quantity
        old_avg = position.avg_entry_price
        new_qty = old_qty + add_qty
        new_avg = (old_qty * old_avg + add_qty * add_price) / new_qty

        position.avg_entry_price = new_avg.quantize(Decimal("0.00000001"))
        position.open_quantity = new_qty
        position.initial_quantity += add_qty
        position.save()

        # trade_type: ampliar LONG → BUY, ampliar SHORT → SELL
        trade_type = "BUY" if position.direction == "LONG" else "SELL"

        TradeHistory.objects.create(
            user=user,
            asset=position.asset,
            position=position,
            trade_type=trade_type,
            trade_intent="ADD",
            quantity=add_qty,
            price_usd=add_price,
            total_usd=(add_qty * add_price).quantize(Decimal("0.00000001")),
            notes=dto.notes,
            executed_at=executed_at,
        )

        current_price = Decimal(str(position.asset.current_price or add_price))
        return _build_position_dto(position, current_price)
