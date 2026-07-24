"""
lead_lag.py — Señales lead-lag entre activos (quién adelanta a quién).

Para cada par de la cesta calcula la correlación cruzada de sus retornos a
distintos desfases y se queda con el desfase que la maximiza: si los retornos
de A en t predicen los de B en t+k (k>0), A *adelanta* a B en k barras. Agrega
un ranking de liderazgo (a cuántos activos adelanta cada uno).

Endurecido (hardening): topes defensivos de desfase y de tamaño de cesta,
recorte de series y umbral mínimo de correlación para no reportar ruido.
Dominio puro sobre retornos ya alineados.
"""

from __future__ import annotations

import numpy as np

_MAX_LAG_CAP = 20          # tope duro del desfase explorado (hardening)
_MIN_OVERLAP = 30          # mínimo de solape para que un par sea evaluable
_MAX_SYMBOLS = 20          # tope de activos de la cesta (evita O(n²) desbocado)


def cross_lag_correlation(a, b, max_lag: int = 5) -> dict | None:
    """
    Mejor desfase de la correlación cruzada de ``a`` con ``b``.

    ``best_lag`` > 0 ⇒ ``a`` adelanta a ``b`` en esas barras.
    """
    max_lag = max(1, min(int(max_lag), _MAX_LAG_CAP))
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    n = min(a.size, b.size)
    if n < _MIN_OVERLAP or n < max_lag * 2 + 10:
        return None
    a, b = a[-n:], b[-n:]

    best_lag, best_corr = 0, 0.0
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            x, y = a[:n - lag] if lag else a, b[lag:]
        else:
            x, y = a[-lag:], b[:n + lag]
        if x.size < 10 or np.std(x) == 0 or np.std(y) == 0:
            continue
        c = float(np.corrcoef(x, y)[0, 1])
        if c == c and abs(c) > abs(best_corr):
            best_corr, best_lag = c, lag
    return {"best_lag": int(best_lag), "best_corr": round(best_corr, 3)}


def lead_lag_matrix(returns_by_symbol: dict, max_lag: int = 5,
                    min_corr: float = 0.3) -> dict:
    """Relaciones lead-lag de la cesta + ranking de liderazgo."""
    usable = {s: np.asarray(r, dtype=float) for s, r in returns_by_symbol.items()
              if np.asarray(r).size >= _MIN_OVERLAP}
    symbols = sorted(usable)[:_MAX_SYMBOLS]
    if len(symbols) < 2:
        return {"status": "INSUFICIENTE", "symbols": [], "pairs": [], "leaders": []}

    leads = {s: 0 for s in symbols}
    pairs = []
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            si, sj = symbols[i], symbols[j]
            cl = cross_lag_correlation(usable[si], usable[sj], max_lag)
            if cl is None or cl["best_lag"] == 0 or abs(cl["best_corr"]) < min_corr:
                continue
            if cl["best_lag"] > 0:
                leader, follower, lag = si, sj, cl["best_lag"]
            else:
                leader, follower, lag = sj, si, -cl["best_lag"]
            leads[leader] += 1
            pairs.append({"leader": leader, "follower": follower,
                          "lag": int(lag), "corr": cl["best_corr"]})

    leaders = sorted(
        ({"symbol": s, "leads": c} for s, c in leads.items()),
        key=lambda x: x["leads"], reverse=True,
    )
    pairs.sort(key=lambda p: abs(p["corr"]), reverse=True)

    return {
        "status": "OK",
        "symbols": symbols,
        "pairs": pairs,
        "leaders": leaders,
        "max_lag": max(1, min(int(max_lag), _MAX_LAG_CAP)),
    }
