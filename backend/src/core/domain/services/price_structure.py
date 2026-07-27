"""
price_structure.py — Estructura de precio: soportes/resistencias y divergencias.

Dos herramientas profesionales clásicas, computadas sobre datos reales:

  · Niveles de soporte/resistencia por AGRUPACIÓN DE PIVOTES: un pivote es un
    máximo/mínimo local confirmado por k velas a cada lado; los pivotes cuyos
    precios caen dentro de una tolerancia se agrupan en un nivel, y su FUERZA es
    el número de toques (cuantas más veces reaccionó el precio ahí, más
    relevante es el nivel).

  · Divergencias RSI/precio sobre los dos últimos pivotes: precio hace máximo
    más alto con RSI más bajo = divergencia bajista (el impulso no acompaña);
    precio hace mínimo más bajo con RSI más alto = divergencia alcista.

Dominio puro (numpy): sin Django ni red, 100% testeable.
"""

from __future__ import annotations

import numpy as np


def find_pivots(high: np.ndarray, low: np.ndarray, k: int = 3) -> tuple[list[int], list[int]]:
    """Índices de pivotes confirmados: máximos locales de `high` y mínimos de
    `low` que dominan ESTRICTAMENTE a las k velas de cada lado (el empate no
    confirma: evita que las mesetas planas generen pivotes en cada vela). Los
    últimos k índices no pueden confirmarse todavía (faltan velas futuras) —
    sin lookahead escondido."""
    n = len(high)
    highs: list[int] = []
    lows: list[int] = []
    for i in range(k, n - k):
        neigh_h = np.concatenate([high[i - k: i], high[i + 1: i + k + 1]])
        neigh_l = np.concatenate([low[i - k: i], low[i + 1: i + k + 1]])
        if high[i] > neigh_h.max():
            highs.append(i)
        if low[i] < neigh_l.min():
            lows.append(i)
    return highs, lows


def cluster_levels(prices: list[float], tolerance_pct: float = 0.6) -> list[dict]:
    """Agrupa precios de pivote en niveles: dos toques pertenecen al mismo nivel
    si distan menos de `tolerance_pct` % del nivel acumulado. Devuelve niveles
    con precio medio y nº de toques, ordenados por fuerza."""
    if not prices:
        return []
    tol = max(tolerance_pct, 0.01) / 100.0
    clusters: list[list[float]] = []
    for p in sorted(prices):
        if clusters and abs(p - np.mean(clusters[-1])) <= float(np.mean(clusters[-1])) * tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    levels = [
        {"price": round(float(np.mean(c)), 8), "touches": len(c)}
        for c in clusters
    ]
    levels.sort(key=lambda lv: lv["touches"], reverse=True)
    return levels


def support_resistance(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                       k: int = 3, tolerance_pct: float = 0.6,
                       max_levels: int = 8) -> list[dict]:
    """Niveles de soporte/resistencia relevantes cerca del precio actual.

    Clasifica cada nivel como soporte (bajo el último cierre) o resistencia
    (sobre él) e incluye la distancia porcentual. Devuelve como mucho
    `max_levels`, priorizando fuerza (toques) y cercanía."""
    if len(close) < (2 * k + 3):
        return []
    last = float(close[-1])
    hi_idx, lo_idx = find_pivots(high, low, k=k)
    levels = cluster_levels([float(high[i]) for i in hi_idx] + [float(low[i]) for i in lo_idx],
                            tolerance_pct=tolerance_pct)
    for lv in levels:
        lv["kind"] = "resistance" if lv["price"] >= last else "support"
        lv["distance_pct"] = round((lv["price"] / last - 1.0) * 100.0, 2)

    # Relevancia: toques primero y, a igualdad, cercanía al precio.
    levels.sort(key=lambda lv: (-lv["touches"], abs(lv["distance_pct"])))
    return levels[:max_levels]


def detect_divergences(close: np.ndarray, rsi: np.ndarray, k: int = 3,
                       lookback: int = 60) -> list[dict]:
    """Divergencias RSI/precio sobre los DOS últimos pivotes de cada lado dentro
    de la ventana `lookback`. Umbral mínimo de diferencia de RSI (1 punto) para
    no señalar ruido."""
    n = len(close)
    if n < (2 * k + 5) or len(rsi) != n:
        return []
    start = max(0, n - lookback)
    hi_idx, lo_idx = find_pivots(close, close, k=k)   # pivotes sobre el cierre
    hi_idx = [i for i in hi_idx if i >= start]
    lo_idx = [i for i in lo_idx if i >= start]

    out: list[dict] = []
    if len(hi_idx) >= 2:
        a, b = hi_idx[-2], hi_idx[-1]
        if close[b] > close[a] and (rsi[a] - rsi[b]) >= 1.0 and not np.isnan(rsi[a]) and not np.isnan(rsi[b]):
            out.append({
                "type": "bearish",
                "detail": "El precio marca un máximo más alto pero el RSI uno más bajo: "
                          "el impulso no acompaña la subida.",
                "price_from": round(float(close[a]), 8), "price_to": round(float(close[b]), 8),
                "rsi_from": round(float(rsi[a]), 2), "rsi_to": round(float(rsi[b]), 2),
            })
    if len(lo_idx) >= 2:
        a, b = lo_idx[-2], lo_idx[-1]
        if close[b] < close[a] and (rsi[b] - rsi[a]) >= 1.0 and not np.isnan(rsi[a]) and not np.isnan(rsi[b]):
            out.append({
                "type": "bullish",
                "detail": "El precio marca un mínimo más bajo pero el RSI uno más alto: "
                          "la caída pierde fuerza.",
                "price_from": round(float(close[a]), 8), "price_to": round(float(close[b]), 8),
                "rsi_from": round(float(rsi[a]), 2), "rsi_to": round(float(rsi[b]), 2),
            })
    return out
