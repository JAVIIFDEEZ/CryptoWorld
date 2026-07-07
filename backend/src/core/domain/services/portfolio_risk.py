"""
portfolio_risk.py — Riesgo agregado del libro completo (dominio puro).

Tres piezas de nivel institucional sobre las posiciones del usuario:

  · Exposición firmada: LONG suma, SHORT resta. El riesgo se mide sobre lo que
    de verdad tienes, no sobre valores absolutos que esconden coberturas.

  · VaR/CVaR por SIMULACIÓN HISTÓRICA: se aplica cada día del histórico real a
    la cartera actual (P&L = retornos · exposiciones) y se leen los percentiles.
    Sin asumir normalidad — las colas gordas de cripto son el punto, no un
    estorbo. CVaR (expected shortfall) = pérdida media DENTRO de la cola, la
    métrica que los reguladores prefieren al VaR desde Basilea III.

  · Stress testing con escenarios OBSERVADOS: el peor movimiento de k días que
    cada activo ha tenido en el histórico disponible, aplicado a la posición
    actual. No inventamos escenarios: reproducimos los que ya ocurrieron.

Capa de dominio: Python puro (numpy), sin BD ni framework.
"""

import numpy as np

# Días mínimos de histórico solapado para que el VaR tenga sentido.
MIN_OVERLAP_DAYS = 60


def daily_returns(closes: np.ndarray) -> np.ndarray:
    closes = np.asarray(closes, dtype=float)
    if closes.size < 2:
        return np.array([])
    return closes[1:] / closes[:-1] - 1.0


def align_returns_matrix(returns_by_symbol: dict[str, np.ndarray]) -> tuple[list[str], np.ndarray]:
    """Recorta todas las series por el final a la longitud común (los retornos
    diarios más recientes quedan alineados). Devuelve (símbolos, matriz T×N)."""
    usable = {s: np.asarray(r, dtype=float) for s, r in returns_by_symbol.items()
              if np.asarray(r).size > 0}
    if not usable:
        return [], np.empty((0, 0))
    min_len = min(r.size for r in usable.values())
    symbols = sorted(usable)
    matrix = np.column_stack([usable[s][-min_len:] for s in symbols])
    return symbols, matrix


def historical_var_cvar(returns_matrix: np.ndarray, exposures_usd: np.ndarray) -> dict:
    """
    VaR/CVaR 1 día por simulación histórica sobre la cartera ACTUAL.

    `returns_matrix`: T×N retornos diarios alineados. `exposures_usd`: vector N
    firmado (SHORT negativo — un día de caída da P&L positivo al corto).
    Devuelve pérdidas como números POSITIVOS (VaR 95 = 120 → "un día de cada
    veinte pierdes 120 USD o más").
    """
    exposures = np.asarray(exposures_usd, dtype=float)
    if returns_matrix.size == 0 or returns_matrix.shape[0] < MIN_OVERLAP_DAYS:
        return {"status": "INSUFICIENTE", "days": int(returns_matrix.shape[0]) if returns_matrix.size else 0,
                "note": f"Se necesitan ≥ {MIN_OVERLAP_DAYS} días de histórico solapado."}

    pnl = returns_matrix @ exposures          # P&L diario simulado en USD
    out = {"status": "OK", "days": int(pnl.size)}
    for conf, tail in (("95", 5.0), ("99", 1.0)):
        cutoff = np.percentile(pnl, tail)
        tail_losses = pnl[pnl <= cutoff]
        out[f"var{conf}_usd"] = round(max(0.0, -float(cutoff)), 2)
        out[f"cvar{conf}_usd"] = round(max(0.0, -float(tail_losses.mean())) if tail_losses.size else 0.0, 2)
    out["worst_day_usd"] = round(-float(pnl.min()), 2)
    out["best_day_usd"] = round(float(pnl.max()), 2)
    return out


def worst_window_return(closes: np.ndarray, window: int) -> "float | None":
    """Peor retorno de `window` días realmente observado en la serie (fracción,
    p. ej. -0.37). None si no hay serie suficiente."""
    closes = np.asarray(closes, dtype=float)
    if closes.size <= window:
        return None
    rets = closes[window:] / closes[:-window] - 1.0
    return float(rets.min())


def stress_scenarios(closes_by_symbol: dict[str, np.ndarray],
                     exposures_by_symbol: dict[str, float],
                     windows: tuple[int, ...] = (1, 7, 30)) -> list[dict]:
    """
    Aplica a la cartera actual el peor movimiento de k días que CADA activo ha
    tenido en su histórico (escenario 'todo lo malo a la vez': conservador a
    propósito — en los cracks reales las correlaciones van a 1). Los cortos se
    benefician de las caídas: exposición firmada × shock firmado.
    """
    scenarios = []
    for window in windows:
        impact = 0.0
        shocks = {}
        covered = 0
        for symbol, exposure in exposures_by_symbol.items():
            closes = closes_by_symbol.get(symbol)
            worst = worst_window_return(closes, window) if closes is not None else None
            if worst is None:
                continue
            covered += 1
            shocks[symbol] = round(worst * 100.0, 2)
            impact += exposure * worst
        scenarios.append({
            "window_days": window,
            "impact_usd": round(impact, 2),
            "shocks_pct": shocks,
            "symbols_covered": covered,
            "symbols_total": len(exposures_by_symbol),
        })
    return scenarios
