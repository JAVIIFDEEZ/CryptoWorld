"""
close_position.py — Caso de uso: Cerrar parcial o totalmente una posición.
"""

from decimal import Decimal
from datetime import datetime, timezone

from core.application.dto.portfolio_dto import ClosePositionInputDTO, PositionDTO
from core.infrastructure.persistence.models import Position, TradeHistory, User
from core.application.use_cases.open_position import _build_position_dto


class ClosePositionUseCase:
    """
    Cierra (parcial o totalmente) una posición abierta del usuario.

    Calcula el PnL realizado, registra el trade de cierre y actualiza
    la posición. Si open_quantity llega a 0, marca la posición como CLOSED.
    """

    def execute(
        self, user: User, position_id: int, dto: ClosePositionInputDTO
    ) -> PositionDTO:
        try:
            position = Position.objects.select_related("asset").get(
                pk=position_id, user=user
            )
        except Position.DoesNotExist:
            raise ValueError("Posición no encontrada.")

        if position.status == "CLOSED":
            raise ValueError("La posición ya está cerrada.")

        close_qty = Decimal(str(dto.close_quantity))
        close_price = Decimal(str(dto.close_price))

        if close_qty <= 0:
            raise ValueError("La cantidad a cerrar debe ser mayor que cero.")
        if close_price <= 0:
            raise ValueError("El precio de cierre debe ser mayor que cero.")
        if close_qty > position.open_quantity:
            raise ValueError(
                f"Cantidad a cerrar ({close_qty}) supera la cantidad abierta "
                f"({position.open_quantity})."
            )

        try:
            executed_at = datetime.fromisoformat(dto.executed_at)
        except ValueError:
            raise ValueError("Formato de fecha inválido. Usa ISO 8601.")

        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=timezone.utc)

        # PnL realizado de esta operación de cierre
        avg = position.avg_entry_price
        if position.direction == "LONG":
            realized_now = (close_price - avg) * close_qty
        else:  # SHORT
            realized_now = (avg - close_price) * close_qty

        # Actualizar posición
        new_open_qty = position.open_quantity - close_qty
        position.realized_pnl += realized_now.quantize(Decimal("0.00000001"))
        position.open_quantity = new_open_qty

        if new_open_qty <= 0:
            position.status = "CLOSED"
            position.closed_at = executed_at

        position.save()

        # trade_type: cerrar LONG → SELL, cerrar SHORT → BUY
        trade_type = "SELL" if position.direction == "LONG" else "BUY"

        TradeHistory.objects.create(
            user=user,
            asset=position.asset,
            position=position,
            trade_type=trade_type,
            trade_intent="CLOSE",
            quantity=close_qty,
            price_usd=close_price,
            total_usd=(close_qty * close_price).quantize(Decimal("0.00000001")),
            notes=dto.notes,
            executed_at=executed_at,
        )

        current_price = Decimal(str(position.asset.current_price or close_price))
        return _build_position_dto(position, current_price)
