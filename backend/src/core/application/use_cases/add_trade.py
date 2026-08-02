"""
add_trade.py — Caso de uso: Registrar una operación en el portfolio.
"""

import logging
from datetime import datetime

from core.application.dto.portfolio_dto import AddTradeInputDTO, TradeOutputDTO
from core.infrastructure.persistence.models import CryptoAsset, TradeHistory

logger = logging.getLogger(__name__)


class AddTradeUseCase:
    """
    Registra una operación de compra o venta en el historial del usuario.

    Validaciones:
      - El activo debe existir en BD.
      - La cantidad debe ser positiva.
      - Para SELL: el usuario debe tener cantidad suficiente.
    """

    def execute(self, user, dto: AddTradeInputDTO) -> TradeOutputDTO:
        symbol = dto.asset_symbol.upper()

        # Buscar activo
        try:
            asset = CryptoAsset.objects.get(symbol=symbol)
        except CryptoAsset.DoesNotExist:
            raise ValueError(f"Activo '{symbol}' no encontrado en el catálogo.") from None

        # El DTO ya transporta Decimal (el serializer valida con
        # DecimalField); no hay conversion desde float que redondee.
        qty = dto.quantity
        price = dto.price_usd
        total = qty * price

        if qty <= 0:
            raise ValueError("La cantidad debe ser mayor que cero.")
        if price <= 0:
            raise ValueError("El precio debe ser mayor que cero.")

        # Parsear fecha
        try:
            executed_at = datetime.fromisoformat(dto.executed_at)
        except ValueError:
            raise ValueError(
                f"Formato de fecha inválido: '{dto.executed_at}'. Usa ISO 8601."
            ) from None

        trade = TradeHistory.objects.create(
            user=user,
            asset=asset,
            trade_type=dto.trade_type,
            quantity=qty,
            price_usd=price,
            total_usd=total,
            notes=dto.notes,
            executed_at=executed_at,
        )

        return _to_dto(trade)


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
