"""
smart_money.py — Radar de dinero inteligente (dominio puro).

La pregunta profesional: ¿QUIÉN acierta? Una dirección que retira de exchanges
justo antes de subidas y deposita justo antes de caídas tiene información (o
suerte persistente, que a efectos de seguimiento es lo mismo). Este módulo
evalúa cada movimiento del histórico contra el retorno FUTURO del activo:

  · Retirada de exchange (intención de acumular) acierta si el precio SUBE
    en el horizonte posterior.
  · Depósito en exchange (intención de vender) acierta si el precio BAJA.

El «retorno capturado» de un movimiento es el retorno futuro con el signo de la
intención (positivo = el movimiento fue rentable). Una dirección puntúa solo con
una muestra mínima de movimientos RESUELTOS (cuyo horizonte ya transcurrió):
sin muestra no hay señal. Dominio puro: sin Django ni red.
"""

from __future__ import annotations

from collections import defaultdict

from core.domain.services.onchain_flow import FROM_EXCHANGE, TO_EXCHANGE


def price_at(prices: list[tuple[int, float]], ts_ms: int) -> float | None:
    """Precio de la primera vela con timestamp ≥ ts_ms (None si la serie no
    llega). `prices` debe venir ordenada por timestamp ascendente."""
    for ts, close in prices:
        if ts >= ts_ms:
            return float(close)
    return None


def evaluate_movements(movements: list[dict],
                       prices_by_symbol: dict[str, list[tuple[int, float]]],
                       horizon_hours: int = 24) -> list[dict]:
    """Evalúa cada movimiento contra el retorno futuro de su activo.

    Cada movimiento: {address, symbol, direction, value_usd, ts_ms}. Devuelve
    los RESUELTOS (con precio en el momento y al final del horizonte) con
    forward_return_pct, captured_pct (retorno con el signo de la intención) y
    correct. Los depósitos/retiradas son las únicas direcciones con intención.
    """
    horizon_ms = horizon_hours * 3600 * 1000
    out: list[dict] = []
    for m in movements:
        direction = m.get("direction")
        if direction not in (TO_EXCHANGE, FROM_EXCHANGE):
            continue
        prices = prices_by_symbol.get(m.get("symbol") or "")
        if not prices:
            continue
        ts = int(m["ts_ms"])
        p0 = price_at(prices, ts)
        p1 = price_at(prices, ts + horizon_ms)
        if p0 is None or p1 is None or p0 <= 0:
            continue  # sin datos o el horizonte aún no ha transcurrido
        fwd = (p1 / p0 - 1.0) * 100.0
        captured = fwd if direction == FROM_EXCHANGE else -fwd
        out.append({
            **m,
            "forward_return_pct": round(fwd, 4),
            "captured_pct": round(captured, 4),
            "correct": captured > 0,
        })
    return out


def score_addresses(evaluated: list[dict], min_moves: int = 3,
                    max_results: int = 15) -> list[dict]:
    """Agrega los movimientos evaluados por dirección y puntúa.

    hit_rate y captured medios se PONDERAN por el tamaño (value_usd): acertar
    con $5M pesa más que con $100K. Solo puntúan direcciones con al menos
    `min_moves` movimientos resueltos. Orden: mejor retorno capturado primero.
    """
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in evaluated:
        addr = e.get("address")
        if addr:
            grouped[addr].append(e)

    board = []
    for addr, moves in grouped.items():
        if len(moves) < min_moves:
            continue
        total_value = sum(float(m.get("value_usd") or 0.0) for m in moves) or 1.0
        hit_rate = sum(float(m.get("value_usd") or 0.0) for m in moves if m["correct"]) / total_value
        captured = sum(m["captured_pct"] * float(m.get("value_usd") or 0.0) for m in moves) / total_value
        board.append({
            "address": addr,
            "moves": len(moves),
            "hit_rate": round(hit_rate, 4),
            "avg_captured_pct": round(captured, 4),
            "total_value_usd": round(total_value, 2),
            "last_move_ts": max(int(m["ts_ms"]) for m in moves),
        })

    board.sort(key=lambda r: (r["avg_captured_pct"], r["hit_rate"]), reverse=True)
    return board[:max_results]
