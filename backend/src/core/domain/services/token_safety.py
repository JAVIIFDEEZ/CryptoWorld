"""
token_safety.py — Análisis de seguridad de un token/contrato ERC-20 (due diligence).

Detecta las señales de rug-pull y honeypot a nivel de CONTRATO que las suites de
due diligence (GoPlus, TokenSniffer, De.Fi) cobran por token, aplicando
heurísticas sobre metadatos públicos del contrato verificado:

  · Verificación: sin código fuente verificado = caja negra (riesgo alto de base).
  · Proxy actualizable: el dueño puede CAMBIAR la lógica en cualquier momento.
  · Poderes del propietario: mint, pause, blacklist, comisiones ajustables,
    límites de transacción — cada uno es un vector de abuso.
  · Ownership renunciado (dueño = dirección cero) = poderes desactivados.

Combina esas señales con la concentración de tenedores (onchain_forensics) en un
score 0-100 y un veredicto. Capa de dominio PURA: recibe metadatos ya
normalizados; sin HTTP, BD ni framework. Determinista y testeable.
"""

import logging

logger = logging.getLogger(__name__)

# Firmas de funciones peligrosas → (peso de riesgo, explicación para el usuario).
# Se buscan en los NOMBRES de las funciones del ABI y, como refuerzo, en el
# código fuente. Cada una es un poder que el propietario puede usar contra los
# tenedores.
DANGEROUS_FUNCTIONS: dict[str, dict] = {
    "mint":         {"weight": 22, "label": "Emisión (mint)",
                     "detail": "El propietario puede crear tokens nuevos y diluir a los tenedores."},
    "blacklist":    {"weight": 25, "label": "Lista negra",
                     "detail": "El propietario puede bloquear a direcciones concretas (no podrían vender)."},
    "pause":        {"weight": 18, "label": "Pausa",
                     "detail": "El propietario puede congelar todas las transferencias."},
    "setfee":       {"weight": 15, "label": "Comisión ajustable",
                     "detail": "El propietario puede subir la comisión de transacción (posible honeypot)."},
    "setmaxtx":     {"weight": 12, "label": "Límite de transacción",
                     "detail": "El propietario puede limitar cuánto se puede vender por operación."},
    "settaxwallet": {"weight": 8,  "label": "Destino de comisiones",
                     "detail": "El propietario redirige las comisiones a una wallet que controla."},
}

# Alias/subcadenas que también cuentan para cada categoría (nombres reales varían).
_FUNCTION_ALIASES: dict[str, tuple] = {
    "mint": ("mint",),
    "blacklist": ("blacklist", "blocklist", "denylist", "setbot", "banaddress"),
    "pause": ("pause", "freeze", "enabletrading", "settrading"),
    "setfee": ("setfee", "settax", "setbuytax", "setselltax", "updatefee"),
    "setmaxtx": ("setmaxtx", "setmaxwallet", "maxtxamount", "setmaxtransaction"),
    "settaxwallet": ("settaxwallet", "setmarketingwallet", "setfeewallet", "settreasury"),
}

_ZERO_ADDRESSES = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}

VERDICTS = (("PELIGROSO", 65), ("RIESGO ALTO", 45), ("PRECAUCIÓN", 25), ("RAZONABLE", 0))


def _function_names_from_abi(abi: list | None) -> set[str]:
    """Nombres de funciones (en minúsculas, sin separadores) del ABI."""
    names: set[str] = set()
    for item in abi or []:
        if isinstance(item, dict) and item.get("type") == "function" and item.get("name"):
            names.add(item["name"].lower().replace("_", ""))
    return names


def _detect_powers(abi: list | None, source: str | None) -> list[dict]:
    """Poderes peligrosos presentes según el ABI (y refuerzo por código fuente)."""
    fn_names = _function_names_from_abi(abi)
    src = (source or "").lower()
    found: list[dict] = []
    for category, meta in DANGEROUS_FUNCTIONS.items():
        aliases = _FUNCTION_ALIASES[category]
        in_abi = any(any(al in fn for al in aliases) for fn in fn_names)
        in_src = any(al in src for al in aliases) if not in_abi else False
        if in_abi or in_src:
            found.append({"category": category, "label": meta["label"],
                          "detail": meta["detail"], "weight": meta["weight"],
                          "source": "abi" if in_abi else "source"})
    return found


def _verdict(score: float) -> str:
    for name, threshold in VERDICTS:
        if score >= threshold:
            return name
    return "RAZONABLE"


def analyze_token_safety(contract: dict, concentration: dict | None = None) -> dict:
    """
    Puntuación de riesgo 0-100 de un token.

    `contract`: metadatos NORMALIZOS del contrato:
       {"is_verified": bool, "is_proxy": bool, "owner": str|None,
        "abi": list|None, "source_code": str|None,
        "name": str, "symbol": str}
    `concentration`: salida de onchain_forensics.holder_concentration (opcional).

    Devuelve score, veredicto, banderas rojas (con su peso) y señales verdes.
    """
    flags: list[dict] = []
    green: list[str] = []
    score = 0

    verified = bool(contract.get("is_verified"))
    if not verified:
        score += 35
        flags.append({"category": "unverified", "weight": 35, "label": "Sin verificar",
                      "detail": "El código fuente no está verificado: no se puede auditar lo que hace."})
    else:
        green.append("Código fuente verificado y auditable.")

    owner = (contract.get("owner") or "").lower()
    renounced = owner in _ZERO_ADDRESSES or owner == ""
    powers = _detect_powers(contract.get("abi"), contract.get("source_code"))

    if contract.get("is_proxy"):
        score += 28
        flags.append({"category": "proxy", "weight": 28, "label": "Proxy actualizable",
                      "detail": "La lógica del contrato puede cambiarse en cualquier momento."})

    # Los poderes del propietario solo cuentan si el ownership NO está renunciado.
    if renounced:
        green.append("Propiedad renunciada: los poderes del dueño están desactivados.")
    else:
        for p in powers:
            score += p["weight"]
            flags.append({"category": p["category"], "weight": p["weight"],
                          "label": p["label"], "detail": p["detail"], "source": p["source"]})
        if owner:
            green.append(f"Propietario activo: {owner[:10]}…")

    # Concentración de tenedores: refuerza el riesgo (dump/rug).
    conc_pct = None
    if concentration and concentration.get("available"):
        conc_pct = concentration.get("top10_share_pct")
        if conc_pct is not None:
            if conc_pct >= 60:
                score += 20
                flags.append({"category": "concentration", "weight": 20, "label": "Concentración crítica",
                              "detail": f"El top-10 controla el {conc_pct}% del sample."})
            elif conc_pct >= 35:
                score += 10
                flags.append({"category": "concentration", "weight": 10, "label": "Concentración alta",
                              "detail": f"El top-10 controla el {conc_pct}% del sample."})
            elif conc_pct < 20:
                green.append(f"Base de tenedores amplia (top-10 {conc_pct}%).")

    score = int(round(min(100, score)))
    flags.sort(key=lambda f: f["weight"], reverse=True)
    return {
        "score": score,
        "verdict": _verdict(score),
        "verified": verified,
        "ownership_renounced": renounced,
        "is_proxy": bool(contract.get("is_proxy")),
        "owner": owner or None,
        "flags": flags,
        "green_flags": green,
        "top10_concentration_pct": conc_pct,
        "note": ("Análisis heurístico sobre el contrato verificado y la distribución de "
                 "tenedores; señala CAPACIDADES de abuso, no que se hayan usado. No es "
                 "auditoría de seguridad ni consejo de inversión."),
    }
