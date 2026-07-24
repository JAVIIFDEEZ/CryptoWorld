"""
derivatives_metrics.py — Microestructura de perpetuos (funding / basis / OI).

Traduce los datos crudos del perpetuo USDⓈ-M (premiumIndex + openInterest) a
métricas legibles con veredicto:

- **Funding** anualizado: el funding se paga cada 8 h (3/día). Positivo = los
  largos pagan a los cortos (multitud alcista, riesgo de long-squeeze si es
  extremo); negativo = lo contrario.
- **Basis**: prima del perpetuo sobre el índice spot. Positivo = contango
  (apalancamiento alcista); negativo = backwardation.
- **Interés abierto (OI)**: contratos vivos y su nocional en USD.

Dominio puro: recibe los dicts de la API y devuelve el snapshot; sin red.
"""

from __future__ import annotations

from typing import Optional

# Umbrales de veredicto (funding anualizado en %, basis en %).
_FUNDING_HOT = 30.0
_FUNDING_BIAS = 10.0
_BASIS_STRONG = 0.5
_BASIS_MILD = 0.1


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _funding_verdict(ann_pct: float) -> str:
    if ann_pct >= _FUNDING_HOT:
        return "LARGOS SOBRECALENTADOS"
    if ann_pct >= _FUNDING_BIAS:
        return "sesgo alcista (largos pagan)"
    if ann_pct <= -_FUNDING_HOT:
        return "CORTOS SOBRECALENTADOS"
    if ann_pct <= -_FUNDING_BIAS:
        return "sesgo bajista (cortos pagan)"
    return "NEUTRAL"


def _basis_verdict(basis_pct: Optional[float]) -> str:
    if basis_pct is None:
        return "—"
    if basis_pct >= _BASIS_STRONG:
        return "contango fuerte"
    if basis_pct > _BASIS_MILD:
        return "contango"
    if basis_pct <= -_BASIS_STRONG:
        return "backwardation fuerte"
    if basis_pct < -_BASIS_MILD:
        return "backwardation"
    return "NEUTRAL"


def compute_derivatives_snapshot(premium_index: dict, open_interest: dict) -> dict:
    """Construye el snapshot de microestructura a partir de la API de futuros."""
    mark = _f((premium_index or {}).get("markPrice"))
    index = _f((premium_index or {}).get("indexPrice"))
    funding = _f((premium_index or {}).get("lastFundingRate"))
    oi = _f((open_interest or {}).get("openInterest"))

    if mark is None or funding is None:
        return {"available": False, "note": "Sin datos de derivados para este activo."}

    funding_ann = funding * 3.0 * 365.0 * 100.0            # % anualizado
    basis_pct = ((mark - index) / index * 100.0) if index else None
    oi_notional = (oi * mark) if (oi is not None) else None

    return {
        "available": True,
        "mark_price": round(mark, 4),
        "index_price": round(index, 4) if index is not None else None,
        "funding_rate": round(funding, 8),
        "funding_annualized_pct": round(funding_ann, 2),
        "funding_verdict": _funding_verdict(funding_ann),
        "basis_pct": round(basis_pct, 4) if basis_pct is not None else None,
        "basis_verdict": _basis_verdict(basis_pct),
        "open_interest": round(oi, 4) if oi is not None else None,
        "open_interest_usd": round(oi_notional, 2) if oi_notional is not None else None,
        "note": (
            "Funding anualizado (se paga cada 8 h); basis = prima del perpetuo "
            "sobre el índice spot; OI en contratos y nocional. Datos de Binance "
            "USDⓈ-M. No es consejo financiero."
        ),
    }
