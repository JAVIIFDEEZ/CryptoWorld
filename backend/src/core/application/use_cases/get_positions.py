"""
get_positions.py — Caso de uso: Obtener posiciones del usuario.
"""

from decimal import Decimal

from core.application.dto.portfolio_dto import PositionDTO, PositionSummaryDTO
from core.infrastructure.persistence.models import Position, User
from core.application.use_cases.open_position import _build_position_dto


class GetPositionsUseCase:
    """
    Devuelve las posiciones del usuario agrupadas en OPEN y CLOSED.

    Para las posiciones OPEN calcula el PnL no realizado usando el
    precio actual del activo (campo `current_price` en CryptoAsset,
    actualizado periódicamente por el worker de Celery).
    """

    def execute(self, user: User, status: str | None = None) -> PositionSummaryDTO:
        """
        :param status: "OPEN" | "CLOSED" | None (todas)
        :return: PositionSummaryDTO
        """
        qs = (
            Position.objects.select_related("asset")
            .prefetch_related("trades")
            .filter(user=user)
        )

        if status in ("OPEN", "CLOSED"):
            qs = qs.filter(status=status)

        open_positions: list[PositionDTO] = []
        closed_positions: list[PositionDTO] = []

        total_unrealized = Decimal("0")
        total_realized = Decimal("0")
        open_long = 0
        open_short = 0

        for pos in qs:
            current_price = Decimal(str(pos.asset.current_price or pos.avg_entry_price))
            dto = _build_position_dto(pos, current_price)

            if pos.status == "OPEN":
                open_positions.append(dto)
                total_unrealized += Decimal(dto.unrealized_pnl_usd)
                if pos.direction == "LONG":
                    open_long += 1
                else:
                    open_short += 1
            else:
                closed_positions.append(dto)

            total_realized += pos.realized_pnl

        return PositionSummaryDTO(
            open_positions=open_positions,
            closed_positions=closed_positions,
            total_unrealized_pnl_usd=str(total_unrealized.quantize(Decimal("0.01"))),
            total_realized_pnl_usd=str(total_realized.quantize(Decimal("0.01"))),
            open_long_count=open_long,
            open_short_count=open_short,
        )
