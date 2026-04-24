"""
get_trade_history.py — Caso de uso: Listar historial de operaciones del usuario.
"""

import logging

from core.application.dto.portfolio_dto import TradeOutputDTO
from core.infrastructure.persistence.models import TradeHistory

logger = logging.getLogger(__name__)


class GetTradeHistoryUseCase:
    """
    Devuelve el historial de operaciones del usuario, con filtros opcionales.
    """

    def execute(
        self,
        user,
        symbol: str = "",
        trade_type: str = "",
        limit: int = 50,
    ) -> list[TradeOutputDTO]:
        qs = (
            TradeHistory.objects.filter(user=user)
            .select_related("asset")
            .order_by("-executed_at")
        )

        if symbol:
            qs = qs.filter(asset__symbol=symbol.upper())
        if trade_type in ("BUY", "SELL"):
            qs = qs.filter(trade_type=trade_type)

        return [_to_dto(t) for t in qs[:limit]]


def _to_dto(trade: TradeHistory) -> TradeOutputDTO:
    return TradeOutputDTO(
        id=trade.pk,
        asset_symbol=trade.asset.symbol,
        asset_name=trade.asset.name,
        trade_type=trade.trade_type,
        quantity=str(trade.quantity),
        price_usd=str(trade.price_usd),
        total_usd=str(trade.total_usd),
        notes=trade.notes,
        executed_at=trade.executed_at.isoformat(),
        created_at=trade.created_at.isoformat(),
    )
