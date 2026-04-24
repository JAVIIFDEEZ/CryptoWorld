"""
delete_trade.py — Caso de uso: Eliminar una operación del historial.
"""

import logging

from core.infrastructure.persistence.models import TradeHistory

logger = logging.getLogger(__name__)


class DeleteTradeUseCase:
    """
    Elimina una operación del historial.
    Solo el propietario puede eliminar sus propias operaciones.
    """

    def execute(self, user, trade_id: int) -> None:
        try:
            trade = TradeHistory.objects.get(pk=trade_id, user=user)
        except TradeHistory.DoesNotExist:
            raise ValueError(f"Operación {trade_id} no encontrada.")

        trade.delete()
