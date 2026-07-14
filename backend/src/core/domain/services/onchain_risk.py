"""
onchain_risk.py — Riesgo de dirección, aprobaciones y grafo de entidad.

Segunda tanda del forense on-chain, las capacidades que las suites de
cumplimiento (Chainalysis, TRM, Elliptic) cobran por dirección:

  · address_risk_score:   puntuación 0-100 combinando exposición a etiquetas de
                          riesgo (sanciones, mixers, scams) de la propia
                          dirección y sus contrapartes con los patrones forenses.
  · analyze_approvals:     aprobaciones ERC-20 vivas y su peligrosidad (ilimitadas
                          a contratos sin verificar = el vector nº1 de drenaje).
  · cluster / entity graph: agrupa direcciones que se mueven juntas (componentes
                          conexos por fuerza de conexión) — heurística de entidad.

Capa de dominio pura (numpy opcional; sin HTTP, BD ni framework). Determinista.
"""

import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 1. Puntuación de riesgo de una dirección
# ═══════════════════════════════════════════════════════════════════

# Categoría de riesgo → (peso si es la PROPIA dirección, peso por CONTRAPARTE).
# Palabras clave que aparecen en las etiquetas públicas de los exploradores.
RISK_CATEGORIES: dict[str, dict] = {
    "sanction":  {"self": 100, "cp": 45, "keywords": ("sanction", "ofac", "sdn", "blocked", "lazarus")},
    "exploit":   {"self": 95,  "cp": 40, "keywords": ("exploit", "hack", "drainer", "attacker", "stolen")},
    "mixer":     {"self": 90,  "cp": 38, "keywords": ("mixer", "tornado", "tumbler", "coinjoin", "wasabi")},
    "scam":      {"self": 85,  "cp": 32, "keywords": ("scam", "fraud", "ponzi", "rugpull", "rug ")},
    "phishing":  {"self": 80,  "cp": 28, "keywords": ("phish", "phishing", "malicious", "spam")},
}

_CP_CONTRIBUTION_CAP = 60      # tope de la aportación total de contrapartes
_PATTERN_WEIGHTS = {"peel_chain": 15, "fan_out": 8}
_BOT_WEIGHT = 5

BANDS = (("SEVERO", 70), ("ALTO", 45), ("MEDIO", 20), ("BAJO", 0))


def classify_label_risk(label: str | None) -> str | None:
    """Categoría de riesgo de una etiqueta pública (o None si es benigna)."""
    if not label:
        return None
    low = label.lower()
    for category, meta in RISK_CATEGORIES.items():
        if any(kw in low for kw in meta["keywords"]):
            return category
    return None


def _band(score: float) -> str:
    for name, threshold in BANDS:
        if score >= threshold:
            return name
    return "BAJO"


def address_risk_score(
    self_labels: list[str] | None,
    counterparties: list[dict] | None,
    patterns: list[dict] | None = None,
    fingerprint: dict | None = None,
) -> dict:
    """
    Puntuación 0-100 de riesgo de una dirección.

    - `self_labels`: etiquetas públicas de la propia dirección.
    - `counterparties`: [{"address","label",...}] con quienes ha interactuado.
    - `patterns`: patrones del rastreo de flujos (fan_out, peel_chain).
    - `fingerprint`: huella conductual (para el sesgo de bot).

    El máximo entre riesgo propio y riesgo agregado de contrapartes+conducta
    determina la puntuación; se listan los factores con su aportación.
    """
    factors: list[dict] = []

    # 1. Riesgo de la PROPIA dirección (domina si está etiquetada).
    self_score = 0
    for lab in (self_labels or []):
        cat = classify_label_risk(lab)
        if cat:
            w = RISK_CATEGORIES[cat]["self"]
            if w > self_score:
                self_score = w
                factors.append({"kind": "self", "category": cat, "weight": w,
                                "detail": f"La dirección está etiquetada como «{lab}»."})

    # 2. Riesgo por CONTRAPARTES (aportación acumulada, con tope).
    cp_score = 0
    flagged_cp: dict[str, int] = {}
    for cp in (counterparties or []):
        cat = classify_label_risk(cp.get("label"))
        if cat:
            cp_score += RISK_CATEGORIES[cat]["cp"]
            flagged_cp[cat] = flagged_cp.get(cat, 0) + 1
    cp_score = min(cp_score, _CP_CONTRIBUTION_CAP)
    for cat, n in flagged_cp.items():
        factors.append({"kind": "counterparty", "category": cat,
                        "weight": min(RISK_CATEGORIES[cat]["cp"] * n, _CP_CONTRIBUTION_CAP),
                        "detail": f"{n} contraparte(s) de riesgo ({cat})."})

    # 3. Conducta (patrones de flujo + arquetipo de bot).
    behavior = 0
    for p in (patterns or []):
        w = _PATTERN_WEIGHTS.get(p.get("type"), 0)
        if w:
            behavior += w
            factors.append({"kind": "pattern", "category": p.get("type"), "weight": w,
                            "detail": p.get("note", p.get("type"))})
    if fingerprint and fingerprint.get("archetype") == "Bot / automatizada":
        behavior += _BOT_WEIGHT
        factors.append({"kind": "behavior", "category": "bot", "weight": _BOT_WEIGHT,
                        "detail": "Conducta automatizada (bot)."})

    score = int(round(min(100, max(self_score, cp_score + behavior))))
    factors.sort(key=lambda f: f["weight"], reverse=True)
    return {
        "score": score,
        "band": _band(score),
        "factors": factors,
        "flagged_counterparties": sum(flagged_cp.values()),
        "note": ("Puntuación heurística sobre etiquetas públicas del explorador y patrones "
                 "on-chain; no es una atribución de identidad ni asesoramiento legal."),
    }


# ═══════════════════════════════════════════════════════════════════
# 2. Aprobaciones ERC-20
# ═══════════════════════════════════════════════════════════════════

# Umbral por encima del cual una allowance se considera "ilimitada" (≈ uint256 max
# o cualquier valor astronómico que en la práctica nunca se agota).
UNLIMITED_THRESHOLD = 1e30


def approval_risk(is_unlimited: bool, spender_verified: bool,
                  spender_flag: str | None) -> tuple[str, str]:
    """Nivel de riesgo (SEVERO/ALTO/MEDIO/BAJO) y motivo de una aprobación."""
    if spender_flag:
        return "SEVERO", f"El gastador está etiquetado como riesgo ({spender_flag})."
    if is_unlimited and not spender_verified:
        return "ALTO", "Aprobación ILIMITADA a un contrato sin verificar."
    if is_unlimited:
        return "MEDIO", "Aprobación ilimitada (a un contrato verificado)."
    return "BAJO", "Aprobación acotada."


def analyze_approvals(approvals: list[dict]) -> dict:
    """
    Clasifica las aprobaciones ERC-20 VIVAS por peligrosidad. Cada aprobación:
      {token, token_symbol, spender, spender_label, amount (float|None),
       spender_verified (bool)}
    Se conserva la última por (token, spender); las revocaciones (amount 0) se
    excluyen. Devuelve la lista enriquecida + resumen.
    """
    latest: dict[tuple, dict] = {}
    for a in approvals:
        key = ((a.get("token") or "").lower(), (a.get("spender") or "").lower())
        latest[key] = a          # el input llega en orden cronológico ascendente

    items = []
    for a in latest.values():
        amount = a.get("amount")
        if amount is not None and amount <= 0:
            continue             # revocada: allowance a 0
        is_unlimited = amount is None or amount >= UNLIMITED_THRESHOLD
        flag = classify_label_risk(a.get("spender_label"))
        level, reason = approval_risk(is_unlimited, bool(a.get("spender_verified")), flag)
        items.append({
            "token": a.get("token"),
            "token_symbol": a.get("token_symbol"),
            "spender": a.get("spender"),
            "spender_label": a.get("spender_label"),
            "spender_verified": bool(a.get("spender_verified")),
            "is_unlimited": is_unlimited,
            "amount": amount,
            "risk": level,
            "reason": reason,
        })

    order = {"SEVERO": 0, "ALTO": 1, "MEDIO": 2, "BAJO": 3}
    items.sort(key=lambda x: order.get(x["risk"], 9))
    counts = {lvl: sum(1 for it in items if it["risk"] == lvl) for lvl in order}
    return {
        "approvals": items,
        "total": len(items),
        "unlimited": sum(1 for it in items if it["is_unlimited"]),
        "counts": counts,
        "worst": items[0]["risk"] if items else "NINGUNO",
        "note": ("Aprobaciones ERC-20 activas (última por token+gastador, revocaciones "
                 "excluidas). Las ilimitadas a contratos sin verificar son el principal "
                 "vector de drenaje de wallets: revócalas si no las usas."),
    }


# ═══════════════════════════════════════════════════════════════════
# 3. Grafo de entidad (direcciones que se mueven juntas)
# ═══════════════════════════════════════════════════════════════════

def connected_components(nodes: list[str], edges: list[dict], min_weight: float = 1.0) -> list[list[str]]:
    """
    Componentes conexos (union-find) considerando solo aristas con
    weight ≥ `min_weight`. Cada arista: {"a","b","weight"}. Determinista: los
    componentes y sus miembros salen ordenados.
    """
    parent = {n: n for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            # Unión determinista: la raíz "menor" gana.
            if ra < rb:
                parent[rb] = ra
            else:
                parent[ra] = rb

    for e in edges:
        if e.get("weight", 0) >= min_weight and e["a"] in parent and e["b"] in parent:
            union(e["a"], e["b"])

    groups: dict[str, list[str]] = {}
    for n in nodes:
        groups.setdefault(find(n), []).append(n)
    return sorted((sorted(g) for g in groups.values()), key=lambda g: (-len(g), g[0]))


def build_entity_graph(root: str, edges: list[dict], min_weight: float = 2.0) -> dict:
    """
    Grafo de entidad alrededor de `root`: nodos (con grado y fuerza), aristas y
    componentes conexos por fuerza ≥ `min_weight`. La "entidad probable" es el
    componente que contiene a `root` (direcciones fuertemente conectadas a él).
    """
    root = root.lower()
    nodes: set[str] = {root}
    for e in edges:
        nodes.add(e["a"])
        nodes.add(e["b"])

    strength: dict[str, float] = {n: 0.0 for n in nodes}
    degree: dict[str, int] = {n: 0 for n in nodes}
    for e in edges:
        w = float(e.get("weight", 0))
        strength[e["a"]] += w
        strength[e["b"]] += w
        degree[e["a"]] += 1
        degree[e["b"]] += 1

    components = connected_components(sorted(nodes), edges, min_weight)
    entity = next((c for c in components if root in c), [root])

    return {
        "root": root,
        "min_weight": min_weight,
        "nodes": [
            {"address": n, "degree": degree[n], "strength": round(strength[n], 4),
             "in_entity": n in entity, "is_root": n == root}
            for n in sorted(nodes, key=lambda x: (-strength[x], x))
        ],
        "edges": [
            {"a": e["a"], "b": e["b"], "weight": round(float(e.get("weight", 0)), 4)}
            for e in edges
        ],
        "entity": entity,
        "entity_size": len(entity),
        "components": len(components),
        "note": ("Agrupación heurística por fuerza de co-movimiento (nº de transferencias "
                 "entre pares). La 'entidad probable' es el grupo fuertemente conectado a la "
                 "dirección raíz; sugiere control común, no lo prueba."),
    }
