"""
onchain_pressure.py — Escáner de movimientos de ballenas + presión on-chain.

Dos piezas que juntas construyen el edge on-chain:

  · ScanWhaleMovementsUseCase: pasa periódicamente (Celery) por las redes
    soportadas, trae los mayores movimientos recientes (GetWhaleMovementsUseCase)
    y los PERSISTE clasificados por dirección respecto a exchanges. La restricción
    de unicidad deduplica: escanear dos veces no duplica movimientos.

  · OnChainPressureUseCase: agrega el histórico persistido en una ventana
    (24h/72h/7d): flujo de entrada (depósitos → presión vendedora potencial) vs
    salida (retiradas → acumulación), puntuación de presión en [-1, +1], serie
    temporal por tramos y los mayores movimientos clasificados de la ventana.
"""

import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from core.domain.services.onchain_flow import (
    aggregate_pressure,
    bucket_flows,
    classify_flow,
    pressure_verdict,
)

logger = logging.getLogger(__name__)

# Redes que escanea la tarea periódica. Ethereum concentra el grueso del flujo
# de exchanges; se amplía según se necesite (cada red = 2 llamadas por pasada).
SCAN_CHAINS: tuple[str, ...] = ("ethereum", "base")

_SCAN_MIN_USD = 100_000.0
_SCAN_LIMIT = 100


def _parse_ts(value) -> datetime | None:
    """Timestamp ISO de Blockscout → datetime consciente de zona (UTC)."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class ScanWhaleMovementsUseCase:
    """Trae y persiste los grandes movimientos recientes de cada red soportada."""

    def __init__(self, whales_uc=None) -> None:
        from core.application.use_cases.get_whale_movements import GetWhaleMovementsUseCase
        self._whales = whales_uc or GetWhaleMovementsUseCase()

    def execute(self, chains: tuple[str, ...] = SCAN_CHAINS,
                min_usd: float = _SCAN_MIN_USD) -> dict:
        from core.infrastructure.persistence.models import WhaleMovementSnapshot

        scanned = created = 0
        for chain in chains:
            result = self._whales.execute(chain=chain, min_usd=min_usd, limit=_SCAN_LIMIT)
            if result.get("error"):
                logger.warning("scan_whales %s: %s", chain, result["error"])
                continue
            scanned += 1

            rows = []
            for m in result.get("movements", []):
                moved_at = _parse_ts(m.get("timestamp"))
                if moved_at is None or not m.get("hash"):
                    continue
                from_p = m.get("from") or {}
                to_p = m.get("to") or {}
                rows.append(WhaleMovementSnapshot(
                    chain=chain,
                    symbol=(m.get("symbol") or "?")[:20],
                    kind=m.get("kind") or "native",
                    amount=float(m.get("amount") or 0.0),
                    value_usd=float(m.get("value_usd") or 0.0),
                    from_address=(from_p.get("address") or "")[:64],
                    to_address=(to_p.get("address") or "")[:64],
                    from_label=(from_p.get("label") or "")[:120],
                    to_label=(to_p.get("label") or "")[:120],
                    direction=classify_flow(from_p.get("label"), to_p.get("label")),
                    tx_hash=(m.get("hash") or "")[:80],
                    moved_at=moved_at,
                ))
            if rows:
                # ignore_conflicts: la restricción de unicidad hace el dedup.
                before = WhaleMovementSnapshot.objects.count()
                WhaleMovementSnapshot.objects.bulk_create(rows, ignore_conflicts=True)
                created += WhaleMovementSnapshot.objects.count() - before

        logger.info("scan_whales: %d redes, %d movimientos nuevos", scanned, created)
        return {"chains_scanned": scanned, "created": created}


class OnChainPressureUseCase:
    """Indicador de presión on-chain a partir del histórico persistido."""

    def execute(self, chain: str = "ethereum", hours: int = 24,
                bucket_hours: int | None = None, top: int = 10) -> dict:
        from core.infrastructure.persistence.models import WhaleMovementSnapshot

        chain = (chain or "ethereum").strip().lower()
        hours = min(max(int(hours), 1), 24 * 30)
        if bucket_hours is None:
            bucket_hours = 1 if hours <= 24 else (6 if hours <= 24 * 7 else 24)

        since = datetime.now(dt_timezone.utc) - timedelta(hours=hours)
        qs = (WhaleMovementSnapshot.objects
              .filter(chain=chain, moved_at__gte=since)
              .order_by("-value_usd"))

        movements = [
            {
                "direction": m.direction,
                "value_usd": m.value_usd,
                "ts_ms": int(m.moved_at.timestamp() * 1000),
            }
            for m in qs
        ]
        summary = aggregate_pressure(movements)
        verdict, verdict_text = pressure_verdict(summary)
        series = bucket_flows(movements, bucket_hours=bucket_hours)

        top_moves = [
            {
                "symbol": m.symbol,
                "kind": m.kind,
                "amount": m.amount,
                "value_usd": m.value_usd,
                "direction": m.direction,
                "from_label": m.from_label or None,
                "to_label": m.to_label or None,
                "tx_hash": m.tx_hash,
                "moved_at": m.moved_at.isoformat(),
            }
            for m in qs[:top]
        ]

        return {
            "chain": chain,
            "window_hours": hours,
            "bucket_hours": bucket_hours,
            "total_movements": len(movements),
            "inflow_usd": summary.inflow_usd,
            "outflow_usd": summary.outflow_usd,
            "net_flow_usd": summary.net_flow_usd,
            "pressure": summary.pressure,
            "classified_count": summary.classified_count,
            "unknown_count": summary.unknown_count,
            "verdict": verdict,
            "verdict_text": verdict_text,
            "series": series,
            "top_movements": top_moves,
            "note": "Depósito en exchange = presión vendedora potencial; retirada = acumulación. "
                    "Histórico propio construido por el escáner periódico (Blockscout).",
        }
