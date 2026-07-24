"""
risk_attribution.py — Atribución de riesgo institucional.

Descompone el riesgo del libro completo en dos ejes complementarios:

1. **Por componentes** (Euler): reparte el riesgo de cola (CVaR histórico 95%)
   entre las posiciones. La contribución de cada activo es su P&L medio en los
   peores días de la cartera; por construcción, las contribuciones SUMAN el
   riesgo total (descomposición coherente), así que se lee "quién aporta el
   riesgo", no solo "quién es grande".

2. **Por factor** (mercado): regresa el P&L del libro sobre un factor de
   mercado (BTC) y separa la varianza en sistemática (beta) e idiosincrásica.

Todo es dominio puro sobre matrices de retornos ya alineadas — sin BD ni red.
"""

from __future__ import annotations

import numpy as np


def component_tail_risk(matrix: np.ndarray, exposures, symbols: list[str],
                        tail_pct: float = 5.0) -> dict:
    """
    Descompone el CVaR histórico (media de las peores colas) por posición.

    ``matrix``: T×N retornos diarios alineados. ``exposures``: vector N firmado.
    Devuelve las contribuciones en USD (positivas = añaden pérdida) y su % del
    total; suman el riesgo de cola de la cartera (Euler).
    """
    exp = np.asarray(exposures, dtype=float)
    if matrix.size == 0 or matrix.shape[0] < 2:
        return {"status": "INSUFICIENTE", "components": []}

    pnl = matrix @ exp                                   # P&L USD por día
    cutoff = np.percentile(pnl, tail_pct)
    tail = pnl <= cutoff
    if tail.sum() == 0:                                  # cola vacía por empates
        tail = pnl <= np.min(pnl)

    # Contribución = -media en cola de (exposición · retorno) del activo.
    contrib = -(matrix[tail] * exp).mean(axis=0)         # vector N (USD)
    marginal = -(matrix[tail]).mean(axis=0)              # pérdida por unidad de exposición
    total = float(contrib.sum())

    components = []
    for i, s in enumerate(symbols):
        components.append({
            "symbol": s,
            "component_usd": round(float(contrib[i]), 2),
            "marginal": round(float(marginal[i]), 6),
            "pct": round(float(contrib[i]) / total * 100.0, 1) if total else 0.0,
            "exposure_usd": round(float(exp[i]), 2),
        })
    components.sort(key=lambda c: abs(c["component_usd"]), reverse=True)

    return {
        "status": "OK",
        "tail_cvar_usd": round(total, 2),
        "days": int(pnl.size),
        "tail_days": int(tail.sum()),
        "components": components,
    }


def factor_attribution(matrix: np.ndarray, exposures, symbols: list[str],
                       factor_returns) -> dict:
    """
    Separa la varianza del P&L del libro en sistemática (beta·factor) e
    idiosincrásica (residual). ``factor_returns`` debe venir alineado (misma T).
    """
    exp = np.asarray(exposures, dtype=float)
    port = matrix @ exp
    f = np.asarray(factor_returns, dtype=float)
    n = min(port.size, f.size)
    if n < 30:
        return {"status": "INSUFICIENTE", "note": "Histórico insuficiente para el factor."}
    port, f = port[-n:], f[-n:]

    fv = float(np.var(f))
    total_var = float(np.var(port))
    if fv == 0.0 or total_var == 0.0:
        return {"status": "INSUFICIENTE", "note": "Sin varianza suficiente."}

    beta = float(np.cov(port, f, bias=True)[0, 1] / fv)   # USD por unidad de retorno del factor
    systematic = beta * f
    sys_var = float(np.var(systematic))
    sys_pct = min(100.0, max(0.0, sys_var / total_var * 100.0))

    return {
        "status": "OK",
        "beta_usd": round(beta, 2),
        "systematic_pct": round(sys_pct, 1),
        "idiosyncratic_pct": round(100.0 - sys_pct, 1),
        "r_squared": round(sys_var / total_var, 3),
        "days": int(n),
    }
