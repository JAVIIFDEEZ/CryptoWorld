"""
onchain_market_pulse.py — Pulso on-chain de mercado (grado institucional).

Unifica en una sola señal todo lo que el escáner ha persistido en TODAS las
cadenas (WhaleMovementSnapshot): flujo neto a/desde exchanges valorado en USD,
veredicto de presión agregado, desglose por cadena y por exchange, activos con
más flujo y una serie temporal del flujo neto. Es la vista que un actor
institucional mira primero — el paradigma CryptoQuant/Glassnode replicado con
datos propios: dónde está entrando y saliendo el dinero grande AHORA, cruzando
redes.

Todo se calcula sobre el histórico propio ya clasificado (dirección
to_exchange/from_exchange), sin llamadas externas en el momento de la consulta.
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class OnChainMarketPulseUseCase:

    def execute(self, hours: int = 24, bucket_hours: int = 4) -> dict:
        from django.utils import timezone
        from datetime import timedelta
        from core.domain.services.onchain_flow import pressure_verdict
        from core.domain.services.onchain_flow import PressureSummary
        from core.infrastructure.persistence.models import WhaleMovementSnapshot

        since = timezone.now() - timedelta(hours=hours)
        movements = list(
            WhaleMovementSnapshot.objects.filter(moved_at__gte=since)
            .values("chain", "symbol", "value_usd", "direction", "from_label",
                    "to_label", "moved_at")
        )
        if not movements:
            return {"status": "INSUFICIENTE", "hours": hours,
                    "note": "Sin movimientos on-chain en la ventana; el escáner "
                            "aún no ha acumulado datos suficientes."}

        inflow = outflow = 0.0            # USD depositado / retirado de exchanges
        classified = 0
        by_chain: dict[str, dict] = defaultdict(lambda: {"inflow": 0.0, "outflow": 0.0, "n": 0})
        by_exchange: dict[str, dict] = defaultdict(lambda: {"inflow": 0.0, "outflow": 0.0, "n": 0})
        by_symbol: dict[str, dict] = defaultdict(lambda: {"inflow": 0.0, "outflow": 0.0, "n": 0})

        for m in movements:
            usd = float(m["value_usd"] or 0.0)
            d = m["direction"]
            chain, sym = m["chain"], m["symbol"]
            if d == "to_exchange":
                inflow += usd
                classified += 1
                by_chain[chain]["inflow"] += usd
                by_symbol[sym]["inflow"] += usd
                ex = _exchange_name(m["to_label"])
                if ex:
                    by_exchange[ex]["inflow"] += usd
                    by_exchange[ex]["n"] += 1
            elif d == "from_exchange":
                outflow += usd
                classified += 1
                by_chain[chain]["outflow"] += usd
                by_symbol[sym]["outflow"] += usd
                ex = _exchange_name(m["from_label"])
                if ex:
                    by_exchange[ex]["outflow"] += usd
                    by_exchange[ex]["n"] += 1
            by_chain[chain]["n"] += 1
            by_symbol[sym]["n"] += 1

        net = outflow - inflow           # positivo = acumulación (retiradas netas)
        total = inflow + outflow
        pressure = (net / total) if total > 0 else 0.0
        summary = PressureSummary(
            inflow_usd=inflow, outflow_usd=outflow, net_flow_usd=inflow - outflow,
            pressure=pressure, classified_count=classified,
            unknown_count=len(movements) - classified,
        )
        verdict, verdict_text = pressure_verdict(summary)

        return {
            "status": "OK",
            "hours": hours,
            "verdict": verdict,
            "verdict_text": verdict_text,
            "pressure": round(pressure, 4),
            "inflow_usd": round(inflow, 2),
            "outflow_usd": round(outflow, 2),
            "net_flow_usd": round(net, 2),
            "movements": len(movements),
            "classified": classified,
            "chains": _top(by_chain, key="chain", limit=8),
            "exchanges": _top(by_exchange, key="exchange", limit=8),
            "symbols": _top(by_symbol, key="symbol", limit=10),
            "series": _net_flow_series(movements, bucket_hours),
            "note": (
                "Pulso on-chain agregado de todas las redes escaneadas sobre el "
                "histórico propio ya clasificado. Retirada de exchange = "
                "acumulación; depósito = presión vendedora potencial. No "
                "constituye consejo financiero."
            ),
        }


def _exchange_name(label: str | None) -> str | None:
    """Normaliza la etiqueta de exchange a su nombre base ('Binance 14' →
    'Binance') para agregar por entidad, no por hot-wallet."""
    from core.domain.services.onchain_flow import is_exchange_label
    if not label or not is_exchange_label(label):
        return None
    return label.split()[0].capitalize()


def _top(agg: dict, key: str, limit: int) -> list[dict]:
    rows = []
    for name, v in agg.items():
        net = v["outflow"] - v["inflow"]
        rows.append({
            key: name,
            "inflow_usd": round(v["inflow"], 2),
            "outflow_usd": round(v["outflow"], 2),
            "net_flow_usd": round(net, 2),
            "movements": v["n"],
        })
    rows.sort(key=lambda r: abs(r["net_flow_usd"]), reverse=True)
    return rows[:limit]


def _net_flow_series(movements: list[dict], bucket_hours: int) -> list[dict]:
    """Serie temporal del flujo NETO (retiradas − depósitos) por tramo, en USD.
    Positivo = acumulación en ese tramo."""
    if not movements:
        return []
    bucket_ms = bucket_hours * 3_600_000
    buckets: dict[int, dict] = defaultdict(lambda: {"inflow": 0.0, "outflow": 0.0})
    for m in movements:
        ts = m["moved_at"]
        epoch_ms = int(ts.timestamp() * 1000)
        b = (epoch_ms // bucket_ms) * bucket_ms
        usd = float(m["value_usd"] or 0.0)
        if m["direction"] == "to_exchange":
            buckets[b]["inflow"] += usd
        elif m["direction"] == "from_exchange":
            buckets[b]["outflow"] += usd
    out = []
    for b in sorted(buckets):
        v = buckets[b]
        out.append({
            "t": b,
            "net_flow_usd": round(v["outflow"] - v["inflow"], 2),
            "inflow_usd": round(v["inflow"], 2),
            "outflow_usd": round(v["outflow"], 2),
        })
    return out
