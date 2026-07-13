"""
onchain_forensics.py — Forense on-chain: flujos, concentración y conducta.

Tres analíticas diferenciales sobre datos públicos de la cadena, del tipo que
las suites institucionales (Chainalysis, Glassnode, Nansen) venden como producto:

  · build_flow_tree:        "sigue el dinero" — árbol de flujo saliente por
                            valor con detección de patrones (fan-out, peel chain).
  · holder_concentration:   radiografía de concentración de un token (Gini, HHI,
                            cuotas top-N, contratos vs. EOAs) con veredicto.
  · wallet_fingerprint:     huella conductual de una dirección (heatmap hora×día,
                            cadencia, diversidad de contrapartes, arquetipo).

Capa de dominio pura: recibe datos ya normalizados (o un fetch inyectable);
sin HTTP, sin BD, sin framework. Todo determinista y testeable en sintético.
"""

import logging
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 1. Rastreador de flujos (sigue el dinero)
# ═══════════════════════════════════════════════════════════════════

# Un nodo con ≥ FAN_OUT_MIN contrapartes salientes distintas es un patrón de
# distribución (fan-out); una cadena de ≥ PEEL_MIN_DEPTH saltos donde cada nodo
# reenvía ≥ PEEL_DOMINANCE de lo que saca a UNA contraparte es un peel chain.
FAN_OUT_MIN = 8
PEEL_DOMINANCE = 0.8
PEEL_MIN_DEPTH = 2

TxFetcher = Callable[[str], list[dict]]
# Cada tx normalizada: {"from": str, "to": str, "value": float, "timestamp": int}
# con direcciones en minúsculas y value en unidades del nativo (no wei).


def _outgoing_by_counterparty(address: str, txs: list[dict]) -> dict[str, dict]:
    """Agrega el valor SALIENTE de `address` por contraparte."""
    out: dict[str, dict] = {}
    for tx in txs:
        if tx.get("from") != address or not tx.get("to") or tx.get("to") == address:
            continue
        value = float(tx.get("value") or 0.0)
        if value <= 0:
            continue
        agg = out.setdefault(tx["to"], {"value": 0.0, "tx_count": 0})
        agg["value"] += value
        agg["tx_count"] += 1
    return out


def build_flow_tree(
    root: str,
    fetch_txs: TxFetcher,
    depth: int = 2,
    top_k: int = 4,
    max_nodes: int = 12,
    min_value: float = 0.0,
) -> dict:
    """
    Árbol de flujo SALIENTE desde `root`: en cada nodo, las top_k contrapartes
    por valor recibido; recursivo hasta `depth` saltos con presupuesto de
    `max_nodes` consultas (el coste real es fetch_txs). Ciclo-seguro: una
    dirección ya visitada no se re-expande (se marca `revisited`).
    Devuelve el árbol + patrones detectados (fan-out, peel chain).
    """
    root = root.lower()
    visited: set[str] = set()
    budget = {"nodes": 0}
    patterns: list[dict] = []

    def _expand(address: str, level: int) -> dict:
        visited.add(address)
        node = {"address": address, "level": level, "children": [],
                "fan_out": 0, "total_out": 0.0}
        if level >= depth or budget["nodes"] >= max_nodes:
            return node
        budget["nodes"] += 1
        try:
            txs = fetch_txs(address)
        except Exception as exc:  # noqa: BLE001 — un nodo sin datos no rompe el árbol
            logger.warning("flow_tree fetch %s: %s", address, exc)
            return node

        out = _outgoing_by_counterparty(address, txs)
        out = {a: v for a, v in out.items() if v["value"] >= min_value}
        node["fan_out"] = len(out)
        node["total_out"] = round(sum(v["value"] for v in out.values()), 6)
        if len(out) >= FAN_OUT_MIN:
            patterns.append({"type": "fan_out", "address": address,
                             "counterparties": len(out),
                             "note": "Distribución: el valor se reparte entre muchas direcciones."})

        ranked = sorted(out.items(), key=lambda kv: kv[1]["value"], reverse=True)[:top_k]
        for counterparty, agg in ranked:
            share = agg["value"] / node["total_out"] if node["total_out"] > 0 else 0.0
            child = {"address": counterparty, "level": level + 1, "children": [],
                     "value_in": round(agg["value"], 6), "tx_count": agg["tx_count"],
                     "share": round(share, 3), "revisited": counterparty in visited,
                     "fan_out": 0, "total_out": 0.0}
            if counterparty not in visited:
                expanded = _expand(counterparty, level + 1)
                child.update({k: expanded[k] for k in ("children", "fan_out", "total_out")})
            node["children"].append(child)
        return node

    tree = _expand(root, 0)

    # Peel chain: cadena de dominancia ≥ PEEL_DOMINANCE con profundidad mínima.
    def _peel_depth(node: dict) -> int:
        if not node["children"]:
            return 0
        dominant = max(node["children"], key=lambda c: c.get("share", 0.0))
        if dominant.get("share", 0.0) >= PEEL_DOMINANCE:
            return 1 + _peel_depth(dominant)
        return 0

    peel = _peel_depth(tree)
    if peel >= PEEL_MIN_DEPTH:
        patterns.append({"type": "peel_chain", "address": root, "depth": peel,
                         "note": "Peel chain: el grueso del valor se reenvía en cadena "
                                 "salto a salto (patrón típico de ofuscación o barrido)."})

    return {
        "root": root,
        "depth": depth,
        "nodes_fetched": budget["nodes"],
        "tree": tree,
        "patterns": patterns,
    }


# ═══════════════════════════════════════════════════════════════════
# 2. Radiografía de concentración de un token
# ═══════════════════════════════════════════════════════════════════

def gini_coefficient(values: list[float]) -> float | None:
    """Gini de una distribución de saldos (0 = igualdad, →1 = un solo dueño).
    Conserva los ceros (un tenedor con saldo 0 es un punto legítimo de la
    distribución); solo descarta valores negativos, imposibles en un supply."""
    arr = np.sort(np.asarray([v for v in values if v >= 0], dtype=float))
    n = arr.size
    if n < 2 or arr.sum() <= 0:
        return None
    index = np.arange(1, n + 1)
    return float((2 * (index * arr).sum() - (n + 1) * arr.sum()) / (n * arr.sum()))


def holder_concentration(holders: list[dict], holders_count_total: int | None = None) -> dict:
    """
    Concentración de un token a partir de sus mayores tenedores (muestra top-N,
    honesto: las métricas de cuota usan el TOTAL del supply si se conoce la
    suma; Gini/HHI se calculan sobre la muestra).

    `holders`: [{"address", "value" (float), "is_contract" (bool)}] ordenados o no.
    """
    vals = sorted((float(h.get("value") or 0.0) for h in holders), reverse=True)
    vals = [v for v in vals if v > 0]
    if len(vals) < 3:
        return {"available": False, "note": "Muestra de tenedores insuficiente."}

    sample_total = sum(vals)
    top10 = sum(vals[:10]) / sample_total * 100.0
    top50 = sum(vals[:50]) / sample_total * 100.0
    shares = np.asarray(vals, dtype=float) / sample_total
    hhi = float((shares ** 2).sum())            # 1/N (distribuido) → 1 (monopolio)
    gini = gini_coefficient(vals)
    contract_value = sum(float(h.get("value") or 0.0) for h in holders if h.get("is_contract"))
    contract_share = contract_value / sample_total * 100.0

    if top10 >= 60:
        verdict, verdict_note = "CRÍTICA", "El top-10 controla la mayoría del sample: riesgo extremo de dump/rug."
    elif top10 >= 35:
        verdict, verdict_note = "ALTA", "Concentración alta: pocas manos pueden mover el precio."
    elif top10 >= 20:
        verdict, verdict_note = "MODERADA", "Concentración típica: vigilar a los mayores tenedores."
    else:
        verdict, verdict_note = "DISTRIBUIDA", "Base de tenedores amplia para la muestra analizada."

    return {
        "available": True,
        "sample_size": len(vals),
        "holders_count_total": holders_count_total,
        "top10_share_pct": round(top10, 2),
        "top50_share_pct": round(top50, 2),
        "gini": round(gini, 4) if gini is not None else None,
        "hhi": round(hhi, 4),
        "contract_share_pct": round(contract_share, 2),
        "top_holders": [
            {"address": h.get("address"), "value": float(h.get("value") or 0.0),
             "share_pct": round(float(h.get("value") or 0.0) / sample_total * 100.0, 2),
             "is_contract": bool(h.get("is_contract"))}
            for h in sorted(holders, key=lambda x: float(x.get("value") or 0.0), reverse=True)[:10]
        ],
        "verdict": verdict,
        "verdict_note": verdict_note,
        "note": ("Métricas sobre la muestra de mayores tenedores (top-N del explorador). "
                 "Gini 0=igualdad→1=monopolio; HHI 1/N=distribuido→1=monopolio."),
    }


# ═══════════════════════════════════════════════════════════════════
# 3. Huella conductual de una wallet
# ═══════════════════════════════════════════════════════════════════

def wallet_fingerprint(address: str, txs: list[dict], now_ts: int) -> dict:
    """
    Perfil conductual de una dirección a partir de sus transacciones
    normalizadas ({"from","to","value","timestamp"}): heatmap de actividad
    hora×día (UTC), cadencia, diversidad de contrapartes y un ARQUETIPO
    heurístico con su evidencia. `now_ts` en segundos (inyectado, determinista).
    """
    address = address.lower()
    txs = [t for t in txs if t.get("timestamp")]
    if len(txs) < 3:
        return {"available": False, "note": "Actividad insuficiente para perfilar."}

    heatmap = [[0] * 24 for _ in range(7)]      # [día_semana][hora] (UTC)
    ts_sorted = sorted(int(t["timestamp"]) for t in txs)
    counterparties: set[str] = set()
    in_count = out_count = 0
    in_value = out_value = 0.0
    for t in txs:
        ts = int(t["timestamp"])
        dow = int((ts // 86400 + 3) % 7)        # lunes=0; 1970-01-01 fue jueves → +3
        heatmap[dow][int(ts % 86400 // 3600)] += 1
        if t.get("from") == address:
            out_count += 1
            out_value += float(t.get("value") or 0.0)
            if t.get("to"):
                counterparties.add(t["to"])
        elif t.get("to") == address:
            in_count += 1
            in_value += float(t.get("value") or 0.0)
            if t.get("from"):
                counterparties.add(t["from"])

    span_days = max(1.0, (ts_sorted[-1] - ts_sorted[0]) / 86400.0)
    txs_per_week = len(txs) / span_days * 7.0
    diversity = len(counterparties) / len(txs)  # 1 = cada tx con contraparte nueva
    gaps = np.diff(ts_sorted)
    gaps = gaps[gaps > 0]
    median_gap_h = float(np.median(gaps)) / 3600.0 if gaps.size else None
    burstiness = float(gaps.std() / gaps.mean()) if gaps.size and gaps.mean() > 0 else None
    days_since_last = (now_ts - ts_sorted[-1]) / 86400.0

    # ── Arquetipo heurístico (orden de precedencia) con evidencia ──
    traits: list[str] = []
    if days_since_last > 30:
        archetype = "Durmiente"
        traits.append(f"Sin actividad desde hace {days_since_last:.0f} días.")
    elif txs_per_week >= 50 and (diversity < 0.15 or (burstiness is not None and burstiness < 0.6)):
        archetype = "Bot / automatizada"
        traits.append(f"{txs_per_week:.0f} tx/semana con cadencia regular "
                      f"y {len(counterparties)} contrapartes.")
    elif out_count >= 3 * max(1, in_count) and len(counterparties) >= 10:
        archetype = "Distribuidora"
        traits.append(f"{out_count} salidas frente a {in_count} entradas "
                      f"hacia {len(counterparties)} contrapartes.")
    elif in_value > 3 * max(out_value, 1e-12) and txs_per_week < 10:
        archetype = "Acumuladora"
        traits.append("Entra mucho más valor del que sale y opera poco: perfil holder.")
    else:
        archetype = "Trader activo"
        traits.append(f"Actividad regular ({txs_per_week:.1f} tx/semana) "
                      f"con flujo bidireccional.")
    if diversity >= 0.6 and len(txs) >= 10:
        traits.append("Alta diversidad de contrapartes: poco comportamiento repetitivo.")
    if burstiness is not None and burstiness > 2.0:
        traits.append("Actividad a ráfagas: períodos quietos con estallidos de operaciones.")

    return {
        "available": True,
        "sample_txs": len(txs),
        "first_seen_ts": ts_sorted[0],
        "last_seen_ts": ts_sorted[-1],
        "span_days": round(span_days, 1),
        "days_since_last": round(days_since_last, 1),
        "txs_per_week": round(txs_per_week, 2),
        "in_count": in_count, "out_count": out_count,
        "in_value": round(in_value, 6), "out_value": round(out_value, 6),
        "unique_counterparties": len(counterparties),
        "diversity": round(diversity, 3),
        "median_gap_hours": round(median_gap_h, 2) if median_gap_h is not None else None,
        "burstiness": round(burstiness, 3) if burstiness is not None else None,
        "heatmap": heatmap,
        "archetype": archetype,
        "traits": traits,
        "note": ("Perfil sobre la muestra de transacciones recientes del explorador "
                 "(heatmap en UTC). Heurístico: describe conducta, no identidad."),
    }
