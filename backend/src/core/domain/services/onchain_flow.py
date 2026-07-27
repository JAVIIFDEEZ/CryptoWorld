"""
onchain_flow.py — Análisis de flujo on-chain hacia/desde exchanges (dominio puro).

El edge clásico de las plataformas de analítica on-chain (CryptoQuant, Nansen):
  · Transferencia grande HACIA un exchange  → el dueño puede querer VENDER
    (presión vendedora potencial: deposita para tener el activo disponible).
  · Transferencia grande DESDE un exchange → retirada a custodia propia
    (acumulación: quien retira no piensa vender a corto plazo).

Este módulo clasifica movimientos usando las etiquetas públicas de entidad que
expone Blockscout (p. ej. «Binance 14», «MEXC: Deposit Address») y agrega la
presión neta en una puntuación honesta en [-1, +1] con su serie temporal.
Es dominio puro: sin Django ni red, 100% testeable.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

# Nombres de exchanges centralizados reconocibles en las etiquetas públicas.
# Se comparan en minúsculas por subcadena; incluye variantes habituales.
EXCHANGE_KEYWORDS: tuple[str, ...] = (
    "binance", "coinbase", "kraken", "okx", "okex", "bybit", "kucoin",
    "mexc", "gate.io", "gateio", "htx", "huobi", "bitfinex", "bitstamp",
    "crypto.com", "gemini", "upbit", "bithumb", "poloniex", "bitget",
    "deposit address", "hot wallet", "exchange",
)

# Direcciones de flujo respecto a exchanges.
TO_EXCHANGE = "to_exchange"          # depósito → presión vendedora potencial
FROM_EXCHANGE = "from_exchange"      # retirada → acumulación
BETWEEN_EXCHANGES = "between_exchanges"  # interno entre exchanges → neutro
UNKNOWN = "unknown"                  # sin etiqueta de exchange en ninguno de los lados


def is_exchange_label(label: str | None) -> bool:
    """True si la etiqueta pública corresponde a un exchange centralizado."""
    if not label:
        return False
    low = label.lower()
    return any(kw in low for kw in EXCHANGE_KEYWORDS)


def classify_flow(from_label: str | None, to_label: str | None) -> str:
    """Clasifica la dirección de un movimiento respecto a exchanges."""
    src = is_exchange_label(from_label)
    dst = is_exchange_label(to_label)
    if src and dst:
        return BETWEEN_EXCHANGES
    if dst:
        return TO_EXCHANGE
    if src:
        return FROM_EXCHANGE
    return UNKNOWN


@dataclass(frozen=True)
class PressureSummary:
    """Resumen agregado del flujo hacia/desde exchanges en una ventana."""
    inflow_usd: float          # total depositado en exchanges (venta potencial)
    outflow_usd: float         # total retirado de exchanges (acumulación)
    net_flow_usd: float        # inflow − outflow (positivo = domina el depósito)
    pressure: float            # (outflow − inflow) / (outflow + inflow) ∈ [-1, +1]
    classified_count: int      # movimientos con dirección conocida
    unknown_count: int         # movimientos sin etiqueta de exchange


def aggregate_pressure(movements: list[dict]) -> PressureSummary:
    """Agrega una lista de movimientos clasificados.

    Cada movimiento: {"direction": str, "value_usd": float}. La puntuación es
    positiva cuando domina la RETIRADA (acumulación, sesgo alcista) y negativa
    cuando domina el DEPÓSITO (presión vendedora); los flujos entre exchanges y
    los desconocidos no puntúan (no aportan dirección).
    """
    inflow = outflow = 0.0
    classified = unknown = 0
    for m in movements:
        value = float(m.get("value_usd") or 0.0)
        direction = m.get("direction")
        if direction == TO_EXCHANGE:
            inflow += value
            classified += 1
        elif direction == FROM_EXCHANGE:
            outflow += value
            classified += 1
        elif direction == BETWEEN_EXCHANGES:
            classified += 1
        else:
            unknown += 1

    total = inflow + outflow
    pressure = round((outflow - inflow) / total, 4) if total > 0 else 0.0
    return PressureSummary(
        inflow_usd=round(inflow, 2),
        outflow_usd=round(outflow, 2),
        net_flow_usd=round(inflow - outflow, 2),
        pressure=pressure,
        classified_count=classified,
        unknown_count=unknown,
    )


def pressure_verdict(summary: PressureSummary, min_classified: int = 5) -> tuple[str, str]:
    """Veredicto honesto de la presión on-chain.

    Exige una muestra mínima de movimientos clasificados: con pocos datos el
    indicador no es fiable y se dice claramente (sin inventar señal).
    """
    if summary.classified_count < min_classified:
        return "INSUFICIENTE", (
            f"Muestra insuficiente ({summary.classified_count} movimientos con dirección "
            f"conocida): el indicador aún no es fiable en esta ventana."
        )
    p = summary.pressure
    if p >= 0.25:
        return "ACUMULACION", (
            "Dominan las RETIRADAS de exchanges: quien mueve tamaño está llevando el activo "
            "a custodia propia (sesgo de acumulación)."
        )
    if p <= -0.25:
        return "PRESION_VENDEDORA", (
            "Dominan los DEPÓSITOS en exchanges: hay tamaño posicionándose para poder vender "
            "(presión vendedora potencial)."
        )
    return "EQUILIBRIO", (
        "Flujos hacia y desde exchanges equilibrados: sin sesgo direccional claro en esta ventana."
    )


def bucket_flows(movements: list[dict], bucket_hours: int = 6) -> list[dict]:
    """Serie temporal de flujos: agrupa por tramos de `bucket_hours` usando el
    timestamp epoch-ms de cada movimiento. Devuelve buckets ordenados con
    inflow/outflow/pressure por tramo."""
    if bucket_hours <= 0:
        bucket_hours = 6
    span_ms = bucket_hours * 3600 * 1000
    grouped: dict[int, list[dict]] = defaultdict(list)
    for m in movements:
        ts = m.get("ts_ms")
        if ts is None:
            continue
        grouped[int(ts) // span_ms].append(m)

    out = []
    for key in sorted(grouped):
        s = aggregate_pressure(grouped[key])
        out.append({
            "start_ms": key * span_ms,
            "inflow_usd": s.inflow_usd,
            "outflow_usd": s.outflow_usd,
            "pressure": s.pressure,
            "count": s.classified_count + s.unknown_count,
        })
    return out
