"""
market_regime.py — Correlaciones cross-asset y clasificador de régimen.

Dominio puro sobre retornos diarios alineados:

- **Matriz de correlación** de Pearson entre los activos de la cesta y la
  correlación media (fuera de la diagonal). Correlación alta = el mercado se
  mueve en bloque (poca diversificación real); baja = dispersión/rotación.
- **Régimen de mercado**: combina la correlación media con la tendencia de BTC
  y la amplitud (breadth: qué parte de la cesta está por encima de su media)
  para etiquetar risk-on / risk-off / rotación / neutral.

Sin BD ni red: recibe los retornos ya calculados.
"""

from __future__ import annotations

import numpy as np

_MIN_DAYS = 20
_CORR_HIGH = 0.70
_CORR_LOW = 0.40


def correlation_matrix(returns_by_symbol: dict) -> dict:
    """Matriz de correlación y correlación media de la cesta."""
    usable = {s: np.asarray(r, dtype=float) for s, r in returns_by_symbol.items()
              if np.asarray(r).size > 1}
    if len(usable) < 2:
        return {"status": "INSUFICIENTE", "symbols": [], "matrix": [], "avg_correlation": None}

    min_len = min(r.size for r in usable.values())
    if min_len < _MIN_DAYS:
        return {"status": "INSUFICIENTE", "symbols": [], "matrix": [], "avg_correlation": None}

    symbols = sorted(usable)
    matrix = np.column_stack([usable[s][-min_len:] for s in symbols])   # T×N
    corr = np.corrcoef(matrix, rowvar=False)                            # N×N
    corr = np.nan_to_num(corr, nan=0.0)

    n = len(symbols)
    off_diag = corr[~np.eye(n, dtype=bool)]
    avg_corr = float(off_diag.mean()) if off_diag.size else 0.0

    # Pares más y menos correlacionados (para el detalle de la UI).
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            pairs.append({"a": symbols[i], "b": symbols[j], "corr": round(float(corr[i, j]), 3)})
    pairs.sort(key=lambda p: p["corr"], reverse=True)

    return {
        "status": "OK",
        "symbols": symbols,
        "matrix": np.round(corr, 3).tolist(),
        "avg_correlation": round(avg_corr, 3),
        "most_correlated": pairs[:3],
        "least_correlated": pairs[-3:][::-1],
        "days": int(min_len),
    }


def classify_regime(avg_correlation, btc_trend_pct: float, breadth_pct: float) -> dict:
    """Etiqueta el régimen de mercado a partir de correlación, tendencia y amplitud."""
    if avg_correlation is None:
        return {"regime": "UNKNOWN", "label": "Sin datos suficientes", "correlation_state": "—"}

    high = avg_correlation >= _CORR_HIGH
    low = avg_correlation <= _CORR_LOW
    corr_state = "alta" if high else ("baja" if low else "media")

    if high and btc_trend_pct < 0:
        regime, label = "RISK_OFF", "Risk-off — todo cae en bloque"
    elif btc_trend_pct > 0 and breadth_pct >= 60.0:
        regime, label = "RISK_ON", "Risk-on — amplitud alcista"
    elif low:
        regime, label = "ROTACION", "Rotación — dispersión, selección de activos"
    else:
        regime, label = "NEUTRAL", "Neutral / mixto"

    return {"regime": regime, "label": label, "correlation_state": corr_state}


def trend_pct(closes, window: int = 20) -> float:
    """Retorno % de la serie en la ventana reciente (0 si insuficiente)."""
    c = np.asarray(closes, dtype=float) if closes is not None else np.array([])
    if c.size <= 1:
        return 0.0
    w = min(window, c.size - 1)
    if c[-w - 1] == 0:
        return 0.0
    return round(float(c[-1] / c[-w - 1] - 1.0) * 100.0, 2)


def breadth_pct(closes_by_symbol: dict, window: int = 20) -> float:
    """% de la cesta cuyo último cierre está por encima de su media móvil."""
    above = total = 0
    for c in closes_by_symbol.values():
        arr = np.asarray(c, dtype=float) if c is not None else np.array([])
        if arr.size < window:
            continue
        total += 1
        if arr[-1] > arr[-window:].mean():
            above += 1
    return round(above / total * 100.0, 1) if total else 0.0
