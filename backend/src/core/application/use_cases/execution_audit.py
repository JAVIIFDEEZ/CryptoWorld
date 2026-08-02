"""
execution_audit.py — Caso de uso: rastro de auditoría de la ejecución real.

Surface de cumplimiento sobre la auditoría de órdenes reales del usuario:
resumen (recuentos, nocional ejecutado, motivos de bloqueo/fallo) + registro
cronológico detallado, con filtro opcional por estado.
"""

from __future__ import annotations

import logging

from core.domain.services.execution_audit import summarize

logger = logging.getLogger(__name__)


class ExecutionAuditUseCase:
    """Rastro de auditoría de ejecución real del usuario (cumplimiento)."""

    _SUMMARY_CAP = 2000   # intentos considerados para el resumen
    _ENTRIES_CAP = 200    # máximo de entradas devueltas en el registro

    def execute(self, owner, limit: int = 50, status_filter: str = "") -> dict:
        from core.infrastructure.persistence.models import LiveOrderRecord

        # Se consulta por `owner`, no por `account__owner`: así entran tanto
        # las órdenes espejadas por la promoción paper→real como las manuales
        # (que no cuelgan de ninguna cartera de paper).
        base = (LiveOrderRecord.objects.filter(owner=owner)
                .order_by("-created_at"))

        summary_rows = list(
            base.values("status", "symbol", "fill_price", "notional_usd")[:self._SUMMARY_CAP]
        )
        summary = summarize(summary_rows)

        entries_qs = base
        if status_filter in ("sent", "failed", "blocked", "pending"):
            entries_qs = entries_qs.filter(status=status_filter)

        limit = max(1, min(limit, self._ENTRIES_CAP))
        entries = [
            {
                "id": r.id,
                "created_at": r.created_at.isoformat(),
                "symbol": r.symbol,
                "side": r.side,
                "amount": r.amount,
                "ref_price": r.ref_price,
                "fill_price": r.fill_price,
                "notional_usd": r.notional_usd,
                "status": r.status,
                "error": r.error,
                "broker_order_id": r.broker_order_id,
                "is_testnet": r.is_testnet,
            }
            for r in entries_qs.select_related("account")[:limit]
        ]

        return {
            "status": "OK" if summary["total_attempts"] else "EMPTY",
            "summary": summary,
            "entries": entries,
            "note": (
                "Rastro de auditoría de cada intento de orden real de la "
                "promoción paper→real: enviadas, fallidas y bloqueadas, con su "
                "motivo. Registro de cumplimiento inmutable para reconstruir "
                "qué se ejecutó y por qué."
            ),
        }
