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

# Redes que escanea la tarea periódica (cada red = 2 llamadas a Blockscout por
# pasada, 8 en total cada 15 min — muy por debajo de cualquier límite). Ethereum
# concentra el grueso del flujo de exchanges; las L2 aportan el flujo minorista.
SCAN_CHAINS: tuple[str, ...] = ("ethereum", "base", "arbitrum", "optimism")

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

        scanned = created = watched_alerts = 0
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
                existing = set(WhaleMovementSnapshot.objects.filter(
                    chain=chain, tx_hash__in=[r.tx_hash for r in rows],
                ).values_list("tx_hash", flat=True))
                new_rows = [r for r in rows if r.tx_hash not in existing]
                before = WhaleMovementSnapshot.objects.count()
                WhaleMovementSnapshot.objects.bulk_create(rows, ignore_conflicts=True)
                created += WhaleMovementSnapshot.objects.count() - before
                # Cruce con direcciones vigiladas: si una wallet del radar del
                # usuario aparece en un movimiento NUEVO, alerta inmediata.
                watched_alerts += self._alert_watched(chain, new_rows)

        logger.info("scan_whales: %d redes, %d movimientos nuevos, %d alertas vigiladas",
                    scanned, created, watched_alerts)
        return {"chains_scanned": scanned, "created": created, "watched_alerts": watched_alerts}

    @staticmethod
    def _alert_watched(chain: str, new_rows: list) -> int:
        """Crea una alerta (máx. una por dirección vigilada y pasada) cuando una
        dirección de la watchlist aparece en un movimiento grande nuevo, y la
        empuja por WebSocket: «esa ballena volvió a mover»."""
        from core.infrastructure.persistence.models import AddressAlert, WatchedAddress
        from core.interfaces.ws.broadcast import broadcast_notification

        if not new_rows:
            return 0
        watches = list(WatchedAddress.objects.filter(chain=chain))
        if not watches:
            return 0
        by_addr: dict[str, list] = {}
        for w in watches:
            by_addr.setdefault(w.address.lower(), []).append(w)

        best: dict[int, tuple] = {}   # watch_id → (movimiento mayor, rol, watch)
        for r in new_rows:
            for role, addr in (("decrease", r.from_address), ("increase", r.to_address)):
                for w in by_addr.get((addr or "").lower(), []):
                    prev = best.get(w.id)
                    if prev is None or r.value_usd > prev[0].value_usd:
                        best[w.id] = (r, role, w)

        created = 0
        for r, role, w in best.values():
            AddressAlert.objects.create(
                watched=w, owner=w.owner,
                direction=role,
                balance_before=w.last_balance or 0.0,
                balance_after=w.last_balance or 0.0,
                delta=r.amount if role == "increase" else -r.amount,
                delta_pct=0.0,
                value_usd=r.value_usd,
                notified=False,
            )
            broadcast_notification(w.owner_id, {"kind": "whale"})
            created += 1
        return created


class DetectPressureSignalUseCase:
    """Registra un evento cuando el RÉGIMEN de presión de una red cambia.

    Se ejecuta tras cada pasada del escáner: compara el veredicto actual (24h)
    con el del último evento registrado y solo crea uno nuevo en la transición.
    INSUFICIENTE nunca genera evento (sin muestra no hay señal) ni resetea el
    último régimen conocido.
    """

    def execute(self, chains: tuple[str, ...] = SCAN_CHAINS) -> dict:
        from core.infrastructure.persistence.models import OnChainSignalEvent

        created = 0
        for chain in chains:
            pressure = OnChainPressureUseCase().execute(chain=chain, hours=24)
            verdict = pressure.get("verdict")
            if verdict in (None, "INSUFICIENTE"):
                continue
            last = OnChainSignalEvent.objects.filter(chain=chain).first()  # ordering -created_at
            if last is not None and last.verdict == verdict:
                continue
            OnChainSignalEvent.objects.create(
                chain=chain,
                verdict=verdict,
                previous_verdict=last.verdict if last else "",
                pressure=pressure["pressure"],
                window_hours=24,
                inflow_usd=pressure["inflow_usd"],
                outflow_usd=pressure["outflow_usd"],
            )
            created += 1
            logger.info("señal on-chain %s: %s → %s (%.2f)",
                        chain, last.verdict if last else "—", verdict, pressure["pressure"])
        return {"created": created}


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
