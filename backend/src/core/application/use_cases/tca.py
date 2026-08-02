"""
tca.py — Caso de uso: analítica de coste de ejecución del usuario.

Carga las órdenes reales del libro del usuario (auditoría LiveOrderRecord) y
calcula el coste de ejecución agregado con el dominio TCA.
"""

from __future__ import annotations

import logging

from core.domain.services.tca import aggregate_tca

logger = logging.getLogger(__name__)


class ExecutionTcaUseCase:
    """Coste de ejecución real del usuario (slippage, fill rate, por símbolo)."""

    _LIMIT = 500   # últimas N órdenes para el análisis

    def execute(self, owner) -> dict:
        from core.infrastructure.persistence.models import LiveOrderRecord

        # Por `owner`: el coste de ejecución del usuario incluye sus órdenes
        # manuales, no solo las espejadas desde una cartera de paper.
        qs = (LiveOrderRecord.objects.filter(owner=owner)
              .order_by("-created_at")[:self._LIMIT])
        records = list(qs)
        if not records:
            return {"status": "EMPTY", "fills": 0,
                    "note": "Sin órdenes reales registradas todavía."}

        total_attempts = len(records)
        filled = [
            {"side": r.side, "ref_price": r.ref_price, "fill_price": r.fill_price,
             "notional_usd": r.notional_usd, "symbol": r.symbol}
            for r in records if r.status == "sent" and r.fill_price is not None
        ]
        result = aggregate_tca(filled, total_attempts=total_attempts)
        result["orders_analyzed"] = total_attempts
        return result
