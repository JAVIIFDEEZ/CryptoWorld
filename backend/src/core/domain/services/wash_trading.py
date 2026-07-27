"""
wash_trading.py — Detección de wash trading (volumen artificial) en un token.

Capacidad forense diferencial (Chainalysis, Nansen la venden): detectar volumen
inflado artificialmente mediante transferencias circulares. El wash trading crea
la ilusión de liquidez/interés comprando y vendiendo entre direcciones que
controla la misma entidad. Señales:

  · Round-trips: pares (A→B) que también tienen el reverso (B→A) — el valor va y
    vuelve. El volumen bidireccional mínimo es "ficticio".
  · Concentración: mucho volumen entre pocos pares de direcciones.
  · Ping-pong: pares con muchas transferencias de ida y vuelta en poco tiempo.
  · Auto-transferencias: origen = destino.

A partir de las transferencias del token calcula un wash_score 0-100, un
veredicto y los pares más sospechosos. Dominio PURO (numpy), determinista.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

VERDICTS = (("MANIPULADO", 60), ("SOSPECHOSO", 35), ("DUDOSO", 18), ("ORGÁNICO", 0))


def _verdict(score: float) -> str:
    for name, threshold in VERDICTS:
        if score >= threshold:
            return name
    return "ORGÁNICO"


def detect_wash_trading(transfers: list[dict], min_transfers: int = 10) -> dict:
    """
    Analiza las transferencias de un token en busca de wash trading.

    `transfers`: [{"from","to","value","timestamp"}] (direcciones en minúsculas,
    value > 0). Devuelve wash_score 0-100, veredicto, métricas y pares sospechosos.
    """
    txs = [t for t in transfers if t.get("from") and t.get("to")
           and float(t.get("value") or 0) > 0]
    if len(txs) < min_transfers:
        return {"available": False,
                "note": f"Se necesitan ≥ {min_transfers} transferencias para el análisis."}

    total_volume = sum(float(t["value"]) for t in txs)
    self_transfers = sum(1 for t in txs if t["from"] == t["to"])

    # Volumen y recuento dirigido por par.
    pair_vol: dict[tuple, float] = {}
    pair_cnt: dict[tuple, int] = {}
    for t in txs:
        key = (t["from"], t["to"])
        pair_vol[key] = pair_vol.get(key, 0.0) + float(t["value"])
        pair_cnt[key] = pair_cnt.get(key, 0) + 1

    # Round-trips: pares con reverso presente. Volumen ficticio = 2×min(ida, vuelta).
    seen: set = set()
    round_trip_volume = 0.0
    suspicious = []
    for (a, b), vol_ab in pair_vol.items():
        if (a, b) in seen or a == b:
            continue
        vol_ba = pair_vol.get((b, a))
        if vol_ba is None:
            continue
        seen.add((a, b))
        seen.add((b, a))
        fictitious = 2.0 * min(vol_ab, vol_ba)
        round_trip_volume += fictitious
        cnt = pair_cnt[(a, b)] + pair_cnt.get((b, a), 0)
        suspicious.append({
            "a": a, "b": b,
            "volume_ab": round(vol_ab, 6), "volume_ba": round(vol_ba, 6),
            "round_trip_volume": round(fictitious, 6),
            "transfers": cnt,
            "share_pct": round(fictitious / total_volume * 100.0, 2) if total_volume > 0 else 0.0,
        })
    suspicious.sort(key=lambda p: p["round_trip_volume"], reverse=True)

    round_trip_ratio = round_trip_volume / total_volume if total_volume > 0 else 0.0

    # Concentración: cuota del volumen en los 5 pares dirigidos mayores.
    top_pairs = sorted(pair_vol.values(), reverse=True)[:5]
    top5_share = sum(top_pairs) / total_volume if total_volume > 0 else 0.0

    # Score: el round-trip domina (señal más fuerte de wash), reforzado por
    # concentración y auto-transferencias.
    score = min(100.0,
                round_trip_ratio * 80.0
                + max(0.0, top5_share - 0.5) * 40.0
                + (self_transfers / len(txs)) * 30.0)
    score = int(round(score))

    return {
        "available": True,
        "wash_score": score,
        "verdict": _verdict(score),
        "total_transfers": len(txs),
        "unique_addresses": len({a for t in txs for a in (t["from"], t["to"])}),
        "round_trip_ratio": round(round_trip_ratio, 4),
        "round_trip_volume_pct": round(round_trip_ratio * 100.0, 2),
        "top5_pair_share_pct": round(top5_share * 100.0, 2),
        "self_transfers": self_transfers,
        "suspicious_pairs": suspicious[:8],
        "note": ("Heurística sobre transferencias recientes del token: el volumen 'round-trip' "
                 "(ida y vuelta entre las mismas direcciones) es la firma del wash trading. "
                 "Señala patrones, no prueba intención."),
    }
