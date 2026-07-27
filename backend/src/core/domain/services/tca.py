"""
tca.py — Analítica de coste de ejecución (Transaction Cost Analysis).

Mide la calidad de la ejecución real comparando el precio de ejecución
(``fill_price``) contra el precio de referencia de la señal (``ref_price``,
la vela del paper que disparó la orden). El slippage se expresa en puntos
básicos con signo de COSTE (positivo = ejecutaste peor que la referencia):

    coste_bps = signo · (fill − ref) / ref · 10 000     (signo: +1 compra, −1 venta)

Dominio puro: recibe las órdenes ya cargadas y devuelve el agregado.
"""

from __future__ import annotations

from typing import Optional


def order_cost(side: str, ref_price: float, fill_price: Optional[float],
               notional_usd: float) -> Optional[dict]:
    """Coste de ejecución de una orden (None si no es medible)."""
    if fill_price is None or not ref_price:
        return None
    sign = 1.0 if side == "buy" else -1.0
    slip = sign * (fill_price - ref_price) / ref_price
    return {"slippage_bps": round(slip * 10_000, 2),
            "cost_usd": round(slip * notional_usd, 2)}


def aggregate_tca(orders: list[dict], total_attempts: int = 0) -> dict:
    """
    Agrega el coste de ejecución de una lista de órdenes.

    ``orders``: dicts con side/ref_price/fill_price/notional_usd/symbol.
    ``total_attempts``: nº de intentos (enviadas+fallidas+bloqueadas) para el
    fill rate. Devuelve slippage medio ponderado por nocional, coste total,
    peor/mejor ejecución y desglose por símbolo.
    """
    measured = []
    for o in orders:
        c = order_cost(o["side"], o["ref_price"], o.get("fill_price"),
                       o.get("notional_usd", 0.0) or 0.0)
        if c is not None:
            measured.append({**o, **c})

    if not measured:
        return {"status": "EMPTY", "fills": 0,
                "note": "Aún no hay ejecuciones reales con precio de llenado."}

    total_notional = sum(o.get("notional_usd", 0.0) or 0.0 for o in measured) or 1.0
    wavg_bps = sum(o["slippage_bps"] * (o.get("notional_usd", 0.0) or 0.0)
                   for o in measured) / total_notional
    total_cost = sum(o["cost_usd"] for o in measured)

    by_symbol: dict[str, dict] = {}
    for o in measured:
        b = by_symbol.setdefault(o["symbol"], {"symbol": o["symbol"], "fills": 0,
                                               "notional_usd": 0.0, "cost_usd": 0.0})
        b["fills"] += 1
        b["notional_usd"] += o.get("notional_usd", 0.0) or 0.0
        b["cost_usd"] += o["cost_usd"]
    for b in by_symbol.values():
        b["avg_slippage_bps"] = round(
            b["cost_usd"] / b["notional_usd"] * 10_000, 2) if b["notional_usd"] else 0.0
        b["notional_usd"] = round(b["notional_usd"], 2)
        b["cost_usd"] = round(b["cost_usd"], 2)

    worst = max(measured, key=lambda o: o["slippage_bps"])
    best = min(measured, key=lambda o: o["slippage_bps"])

    fills = len(measured)
    fill_rate = round(fills / total_attempts * 100.0, 1) if total_attempts else None

    return {
        "status": "OK",
        "fills": fills,
        "total_notional_usd": round(total_notional, 2),
        "avg_slippage_bps": round(wavg_bps, 2),
        "total_cost_usd": round(total_cost, 2),
        "fill_rate_pct": fill_rate,
        "worst": {"symbol": worst["symbol"], "side": worst["side"],
                  "slippage_bps": worst["slippage_bps"], "cost_usd": worst["cost_usd"]},
        "best": {"symbol": best["symbol"], "side": best["side"],
                 "slippage_bps": best["slippage_bps"], "cost_usd": best["cost_usd"]},
        "by_symbol": sorted(by_symbol.values(), key=lambda b: b["cost_usd"], reverse=True),
        "note": (
            "Slippage con signo de coste (positivo = peor que la referencia de "
            "la señal), en puntos básicos ponderados por nocional. Solo órdenes "
            "reales con precio de llenado devuelto por el broker."
        ),
    }
