"""
portfolio_analysis.py — Análisis de cartera de estrategias (dominio puro).

Una estrategia buena aislada no basta: lo profesional es medir cómo COMBINAN.
Dos estrategias rentables pero perfectamente correlacionadas no diversifican
nada; dos poco correlacionadas suavizan la equity conjunta y reducen el drawdown
más de lo que reducen el retorno (el único "free lunch" de la gestión).

Funciones puras sobre curvas de equity: retornos diarios, alineación por fechas
comunes, matriz de correlación y métricas de la cartera equiponderada.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone as dt_tz

import numpy as np


def daily_returns_from_equity(timestamps_ms: list[int], equity: list[float]) -> dict[str, float]:
    """Convierte una curva de equity por vela en retornos DIARIOS.

    `equity` tiene n+1 puntos (incluye el capital inicial); el punto i+1
    corresponde a la vela i. Se toma el último equity de cada día natural (UTC)
    y se calcula el retorno respecto al día anterior. Trabajar en retornos
    diarios permite comparar estrategias de marcos distintos (1h vs 1d).
    """
    if not timestamps_ms or len(equity) < 2:
        return {}
    eod: dict[str, float] = {}
    for i, ts in enumerate(timestamps_ms):
        day = datetime.fromtimestamp(ts / 1000.0, tz=dt_tz.utc).strftime("%Y-%m-%d")
        eod[day] = float(equity[min(i + 1, len(equity) - 1)])

    days = sorted(eod)
    out: dict[str, float] = {}
    for prev, cur in zip(days, days[1:]):
        if eod[prev] > 0:
            out[cur] = eod[cur] / eod[prev] - 1.0
    return out


def align_returns(series: dict[str, dict[str, float]]) -> tuple[list[str], dict[str, list[float]]]:
    """Alinea varias series de retornos diarios sobre sus fechas COMUNES
    (intersección). Devuelve (fechas ordenadas, {nombre: retornos alineados})."""
    if not series:
        return [], {}
    common: set[str] | None = None
    for rets in series.values():
        keys = set(rets)
        common = keys if common is None else (common & keys)
    dates = sorted(common or set())
    return dates, {name: [rets[d] for d in dates] for name, rets in series.items()}


def correlation_matrix(aligned: dict[str, list[float]]) -> tuple[list[str], list[list[float | None]]]:
    """Matriz de correlación de Pearson entre las series alineadas. Una serie
    sin varianza (estrategia plana en la ventana) da None frente a las demás."""
    names = list(aligned)
    n = len(names)
    matrix: list[list[float | None]] = [[None] * n for _ in range(n)]
    arrays = {name: np.asarray(vals, dtype=float) for name, vals in aligned.items()}
    for i, a in enumerate(names):
        for j, b in enumerate(names):
            if i == j:
                matrix[i][j] = 1.0
                continue
            xa, xb = arrays[a], arrays[b]
            if len(xa) < 2 or float(np.std(xa)) == 0.0 or float(np.std(xb)) == 0.0:
                matrix[i][j] = None
                continue
            matrix[i][j] = round(float(np.corrcoef(xa, xb)[0, 1]), 4)
    return names, matrix


def avg_pairwise_correlation(matrix: list[list[float | None]]) -> float | None:
    """Media de las correlaciones fuera de la diagonal (ignora None)."""
    vals = [
        matrix[i][j]
        for i in range(len(matrix))
        for j in range(i + 1, len(matrix))
        if matrix[i][j] is not None
    ]
    return round(float(np.mean(vals)), 4) if vals else None


def portfolio_stats(dates: list[str], aligned: dict[str, list[float]]) -> dict:
    """Métricas de la cartera EQUIPONDERADA sobre los retornos alineados:
    curva de equity (base 100), retorno total, drawdown máximo y Sharpe diario
    anualizado (√365, cripto opera todos los días)."""
    if not dates or not aligned:
        return {"equity": [], "total_return_pct": 0.0, "max_drawdown_pct": 0.0, "sharpe": 0.0}

    rows = np.asarray(list(aligned.values()), dtype=float)   # (n_estrategias, n_días)
    port = rows.mean(axis=0)                                  # retorno diario equiponderado

    equity = 100.0 * np.cumprod(1.0 + port)
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / peak
    std = float(np.std(port, ddof=1)) if len(port) > 1 else 0.0
    sharpe = float(np.mean(port)) / std * math.sqrt(365.0) if std > 0 else 0.0

    return {
        "equity": [{"date": d, "value": round(float(v), 2)} for d, v in zip(dates, equity)],
        "total_return_pct": round((float(equity[-1]) / 100.0 - 1.0) * 100.0, 2),
        "max_drawdown_pct": round(float(drawdown.max()) * 100.0, 2),
        "sharpe": round(sharpe, 2),
    }
