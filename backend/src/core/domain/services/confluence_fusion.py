"""
confluence_fusion.py — Motor de confluencia 360° (dominio puro).

Fusiona las lecturas direccionales de las fuentes del sistema — técnica,
ML, on-chain y noticias — en un único score por activo ∈ [-1, +1], con dos
principios innegociables:

  · PESOS APRENDIDOS, NO INVENTADOS. Cada lectura de confluencia se registra y
    se verifica al vencer su horizonte (¿acertó la dirección cada fuente?).
    El peso de una fuente se deriva de su acierto histórico REAL: las fuentes
    que baten al azar se promocionan, las que no, se degradan. Sin muestra
    suficiente (arranque en frío) se usan pesos a priori y se dice claramente.

  · HONESTIDAD ESTRUCTURAL. Fuentes no disponibles no puntúan (los pesos se
    renormalizan sobre las presentes); el veredicto exige acuerdo real entre
    fuentes, y con menos de dos fuentes el motor responde INSUFICIENTE en vez
    de disfrazar una sola opinión de consenso.

Capa de dominio: Python puro, sin BD ni framework.
"""

import math

# Pesos a priori (arranque en frío, suman 1). La técnica pesa más porque es la
# única fuente con validación walk-forward integrada desde el origen.
PRIOR_WEIGHTS: dict[str, float] = {
    "technical": 0.35,
    "ml": 0.25,
    "onchain": 0.25,
    "news": 0.15,
}

SOURCES = tuple(PRIOR_WEIGHTS)

# Muestra mínima de lecturas resueltas para confiar en el acierto aprendido.
MIN_SAMPLE = 20
# Una lectura de fuente solo es "direccional" (evaluable) si |score| ≥ umbral.
DIRECTIONAL_MIN = 0.15
# Límites del multiplicador aprendido sobre el peso a priori: una fuente nunca
# se anula del todo (podría recuperarse) ni domina por racha corta.
_MULT_RANGE = (0.4, 1.6)


def clamp(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(value)))


def learn_weights(resolved: list[dict]) -> dict[str, dict]:
    """
    Deriva el peso de cada fuente de su acierto histórico.

    `resolved`: lecturas verificadas, cada una {"scores": {fuente: score},
    "actual_return_pct": float}. Para cada fuente se evalúan solo sus lecturas
    direccionales (|score| ≥ DIRECTIONAL_MIN): acierto = el signo del score
    coincide con el del retorno realizado.

    Devuelve {fuente: {weight, hit_rate, n, mode}} con los pesos normalizados
    (suman 1). mode = "aprendido" | "a_priori" (muestra insuficiente).
    """
    stats: dict[str, dict] = {s: {"hits": 0, "n": 0} for s in SOURCES}
    for row in resolved:
        ret = row.get("actual_return_pct")
        if ret is None or ret == 0:
            continue
        for source, score in (row.get("scores") or {}).items():
            if source not in stats or score is None or abs(score) < DIRECTIONAL_MIN:
                continue
            stats[source]["n"] += 1
            if (score > 0) == (ret > 0):
                stats[source]["hits"] += 1

    lo, hi = _MULT_RANGE
    out: dict[str, dict] = {}
    for source in SOURCES:
        n = stats[source]["n"]
        prior = PRIOR_WEIGHTS[source]
        if n >= MIN_SAMPLE:
            hit_rate = stats[source]["hits"] / n
            # 50% de acierto → multiplicador 1 (peso a priori); cada punto de
            # edge mueve el peso proporcionalmente, acotado para evitar rachas.
            mult = clamp(2.0 * hit_rate, lo, hi)
            out[source] = {"weight": prior * mult, "hit_rate": round(hit_rate, 4),
                           "n": n, "mode": "aprendido"}
        else:
            out[source] = {"weight": prior, "hit_rate": None, "n": n, "mode": "a_priori"}

    total = sum(v["weight"] for v in out.values()) or 1.0
    for v in out.values():
        v["weight"] = round(v["weight"] / total, 4)
    return out


def fuse(sources: dict[str, dict], weights: dict[str, dict]) -> dict:
    """
    Fusiona las lecturas disponibles en un score único con veredicto.

    `sources`: {fuente: {"score": float∈[-1,1], "available": bool, ...}}.
    Los pesos se renormalizan sobre las fuentes DISPONIBLES. El acuerdo mide
    qué fracción del peso disponible apunta en la dirección del score fusionado
    (las lecturas casi planas, |s| < DIRECTIONAL_MIN, no votan dirección).
    """
    available = {k: v for k, v in sources.items()
                 if v.get("available") and v.get("score") is not None}
    n_avail = len(available)
    if n_avail < 2:
        return {"score": 0.0, "verdict": "INSUFICIENTE", "agreement_pct": 0.0,
                "sources_available": n_avail,
                "verdict_text": "Menos de dos fuentes disponibles: una sola "
                                "opinión no es una confluencia."}

    w_avail = {k: weights.get(k, {}).get("weight", PRIOR_WEIGHTS.get(k, 0.1))
               for k in available}
    w_total = sum(w_avail.values()) or 1.0
    fused = sum((w_avail[k] / w_total) * clamp(available[k]["score"]) for k in available)

    # Acuerdo ponderado: peso de las fuentes direccionales que apuntan como el
    # score fusionado, sobre el peso direccional total.
    directional = {k: v for k, v in available.items()
                   if abs(v["score"]) >= DIRECTIONAL_MIN}
    dir_weight = sum(w_avail[k] for k in directional) or 0.0
    if fused != 0 and dir_weight > 0:
        agree_weight = sum(
            w_avail[k] for k, v in directional.items()
            if math.copysign(1, v["score"]) == math.copysign(1, fused)
        )
        agreement = agree_weight / dir_weight
    else:
        agreement = 0.0

    if abs(fused) >= 0.3 and agreement >= 0.66:
        verdict = "CONFLUENCIA_ALCISTA" if fused > 0 else "CONFLUENCIA_BAJISTA"
        verdict_text = (f"{int(round(agreement * 100))}% del peso direccional apunta "
                        f"{'al alza' if fused > 0 else 'a la baja'} "
                        f"(score {fused:+.2f}, {n_avail} fuentes).")
    elif abs(fused) >= 0.15 and agreement < 0.66:
        verdict = "MIXTO"
        verdict_text = "Las fuentes discrepan: hay señal pero sin consenso suficiente."
    else:
        verdict = "NEUTRAL"
        verdict_text = "Sin dirección clara agregando todas las fuentes."

    return {
        "score": round(clamp(fused), 4),
        "verdict": verdict,
        "verdict_text": verdict_text,
        "agreement_pct": round(agreement * 100.0, 1),
        "sources_available": n_avail,
    }


def learn_weights_hierarchical(asset_rows: list[dict], global_rows: list[dict]) -> dict[str, dict]:
    """
    Aprendizaje jerárquico de pesos: para cada fuente se usa el acierto sobre
    las lecturas de ESTE activo si hay muestra suficiente (los regímenes de BTC
    y de una altcoin no tienen por qué parecerse); si no, el acierto GLOBAL de
    la fuente; y sin muestra global, el peso a priori. El modo lo declara:
    "aprendido_activo" | "aprendido_global" | "a_priori".
    """
    per_asset = learn_weights(asset_rows)
    global_ = learn_weights(global_rows)
    out: dict[str, dict] = {}
    for source in SOURCES:
        if per_asset[source]["mode"] == "aprendido":
            out[source] = {**per_asset[source], "mode": "aprendido_activo"}
        elif global_[source]["mode"] == "aprendido":
            out[source] = {**global_[source], "mode": "aprendido_global"}
        else:
            out[source] = global_[source]   # a_priori (n = muestra global)
    total = sum(v["weight"] for v in out.values()) or 1.0
    for v in out.values():
        v["weight"] = round(v["weight"] / total, 4)
    return out


def engine_track_record(resolved: list[dict]) -> dict:
    """
    Track record del PROPIO motor: sobre lecturas verificadas, ¿acertó la
    dirección el score fusionado? Global y desglosado por veredicto. El retorno
    medio va FIRMADO por la dirección de la lectura (positivo = la lectura fue
    rentable en su sentido), que es lo que un operador querría saber.
    """
    total = {"n": 0, "hits": 0, "signed_return_sum": 0.0}
    by_verdict: dict[str, dict] = {}
    for row in resolved:
        ret = row.get("actual_return_pct")
        fused = row.get("fused_score")
        verdict = row.get("verdict") or "—"
        if ret is None or fused is None or abs(fused) < DIRECTIONAL_MIN:
            continue
        hit = (fused > 0) == (ret > 0)
        signed = ret if fused > 0 else -ret
        for bucket in (total, by_verdict.setdefault(
                verdict, {"n": 0, "hits": 0, "signed_return_sum": 0.0})):
            bucket["n"] += 1
            bucket["hits"] += int(hit)
            bucket["signed_return_sum"] += signed

    def _fmt(b: dict) -> dict:
        n = b["n"]
        return {
            "n": n,
            "hit_rate": round(b["hits"] / n, 4) if n else None,
            "avg_signed_return_pct": round(b["signed_return_sum"] / n, 4) if n else None,
        }

    return {"overall": _fmt(total),
            "by_verdict": {k: _fmt(v) for k, v in by_verdict.items()}}
