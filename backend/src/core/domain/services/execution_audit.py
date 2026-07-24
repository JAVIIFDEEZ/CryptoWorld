"""
execution_audit.py — Resumen del rastro de auditoría de la ejecución real.

Convierte la auditoría de órdenes reales (cada intento: enviada/fallida/
bloqueada) en un resumen de cumplimiento: recuento por estado, nocional
realmente ejecutado, fill rate y desglose de motivos de bloqueo y fallo. Es la
foto de "qué hizo exactamente la promoción paper→real y por qué". Dominio puro.
"""

from __future__ import annotations


def summarize(records: list[dict]) -> dict:
    """Resumen de cumplimiento sobre una lista de intentos de orden."""
    total = len(records)
    if total == 0:
        return {"total_attempts": 0, "sent": 0, "failed": 0, "blocked": 0,
                "executed_notional_usd": 0.0, "fill_rate_pct": None,
                "distinct_symbols": 0, "blocked_reasons": [], "failed_reasons": []}

    by_status: dict[str, int] = {}
    blocked_reasons: dict[str, int] = {}
    failed_reasons: dict[str, int] = {}
    executed_notional = 0.0
    symbols: set[str] = set()

    for r in records:
        st = r.get("status", "")
        by_status[st] = by_status.get(st, 0) + 1
        symbols.add(r.get("symbol", ""))
        if st == "sent" and r.get("fill_price") is not None:
            executed_notional += r.get("notional_usd", 0.0) or 0.0
        reason = (r.get("error") or "").strip()
        if reason and st == "blocked":
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1
        elif reason and st == "failed":
            failed_reasons[reason] = failed_reasons.get(reason, 0) + 1

    sent = by_status.get("sent", 0)

    def _reasons(d: dict) -> list[dict]:
        return [{"reason": k, "count": v}
                for k, v in sorted(d.items(), key=lambda x: -x[1])]

    return {
        "total_attempts": total,
        "sent": sent,
        "failed": by_status.get("failed", 0),
        "blocked": by_status.get("blocked", 0),
        "executed_notional_usd": round(executed_notional, 2),
        "fill_rate_pct": round(sent / total * 100.0, 1) if total else None,
        "distinct_symbols": len({s for s in symbols if s}),
        "blocked_reasons": _reasons(blocked_reasons),
        "failed_reasons": _reasons(failed_reasons),
    }
