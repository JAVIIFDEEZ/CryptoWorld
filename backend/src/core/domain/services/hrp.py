"""
hrp.py — Hierarchical Risk Parity (López de Prado, 2016).

El problema que resuelve
────────────────────────
La optimización media-varianza de Markowitz **invierte la matriz de
covarianzas**. Con activos correlacionados esa matriz está mal condicionada, y
al invertirla los errores de estimación no se atenúan: se amplifican. El
resultado son carteras concentradas en unos pocos activos que resultan
espectaculares dentro de la muestra y se desmoronan fuera de ella. Es un caso
límpio de precisión aparente sin exactitud real.

HRP no invierte nada. Trabaja en tres pasos:

  1. **Clustering jerárquico** sobre la distancia `d = √(0.5·(1−ρ))`, que
     convierte la correlación en una métrica válida: dos series idénticas
     distan 0, dos opuestas distan 1.
  2. **Cuasi-diagonalización**: se reordenan los activos siguiendo el árbol, de
     modo que los parecidos queden adyacentes.
  3. **Bisección recursiva**: el peso se reparte entre las dos mitades en
     proporción inversa a su varianza, bajando por el árbol.

Al no invertir la covarianza, HRP es mucho más estable fuera de muestra — que es
donde se gana o se pierde el dinero.

Implementación propia con enlace simple: `scipy.cluster.hierarchy` haría lo
mismo, pero la dependencia no aporta aquí y el algoritmo cabe en cien líneas
legibles. Sin framework: NumPy puro.
"""

from __future__ import annotations

import numpy as np


def correlation_distance(corr: np.ndarray) -> np.ndarray:
    """Matriz de correlación → distancia métrica `d = √(0.5·(1−ρ))`."""
    c = np.clip(np.asarray(corr, dtype=float), -1.0, 1.0)
    return np.sqrt(np.maximum(0.5 * (1.0 - c), 0.0))


def _linkage_order(dist: np.ndarray) -> list[int]:
    """
    Orden cuasi-diagonal por aglomeración de enlace simple.

    Se van fusionando los dos grupos más cercanos; el orden final es el recorrido
    de las hojas del árbol, que deja juntos a los activos parecidos. Es lo que
    permite que la bisección posterior separe bloques con sentido en lugar de
    cortar por un índice arbitrario.
    """
    n = dist.shape[0]
    clusters: list[list[int]] = [[i] for i in range(n)]

    while len(clusters) > 1:
        best = (np.inf, 0, 1)
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                # Enlace simple: la distancia entre grupos es la de sus miembros
                # más cercanos.
                d = min(dist[i, j] for i in clusters[a] for j in clusters[b])
                if d < best[0]:
                    best = (d, a, b)
        _, a, b = best
        clusters[a] = clusters[a] + clusters[b]
        clusters.pop(b)

    return clusters[0]


def _inverse_variance_weights(cov: np.ndarray, idx: list[int]) -> np.ndarray:
    """Pesos por varianza inversa dentro de un grupo (paridad de riesgo ingenua)."""
    variances = np.diag(cov)[idx]
    variances = np.where(variances > 0, variances, np.nan)
    inv = 1.0 / variances
    if not np.isfinite(inv).any():
        return np.full(len(idx), 1.0 / len(idx))
    inv = np.where(np.isfinite(inv), inv, 0.0)
    total = inv.sum()
    return inv / total if total > 0 else np.full(len(idx), 1.0 / len(idx))


def _cluster_variance(cov: np.ndarray, idx: list[int]) -> float:
    """Varianza de un grupo ponderado por varianza inversa."""
    w = _inverse_variance_weights(cov, idx)
    sub = cov[np.ix_(idx, idx)]
    return float(w @ sub @ w)


def _recursive_bisection(cov: np.ndarray, order: list[int]) -> np.ndarray:
    """
    Reparte el peso bajando por el árbol: en cada corte, cada mitad recibe una
    parte inversamente proporcional a su varianza.
    """
    n = cov.shape[0]
    weights = np.ones(n, dtype=float)
    groups: list[list[int]] = [list(order)]

    while groups:
        # Se parten solo los grupos con más de un miembro.
        groups = [g[j:k] for g in groups
                  for j, k in ((0, len(g) // 2), (len(g) // 2, len(g)))
                  if len(g) > 1]
        for i in range(0, len(groups), 2):
            left, right = groups[i], groups[i + 1]
            var_l, var_r = _cluster_variance(cov, left), _cluster_variance(cov, right)
            total = var_l + var_r
            # El grupo con MENOS varianza se lleva más peso.
            alpha = 1.0 - var_l / total if total > 0 else 0.5
            weights[left] *= alpha
            weights[right] *= 1.0 - alpha

    return weights


def _round_preserving_sum(weights: np.ndarray, decimals: int = 4) -> list[float]:
    """
    Redondea los pesos de modo que sigan sumando exactamente 1.

    Redondear cada uno por su cuenta deja un residuo (0.9999, 1.0001) que en una
    asignación de capital es un error: los pesos son instrucciones, no
    estadísticos. El residuo se absorbe en el peso mayor, donde es relativamente
    más pequeño y no altera el orden.
    """
    rounded = np.round(weights, decimals)
    residual = round(1.0 - float(rounded.sum()), decimals + 2)
    if abs(residual) > 0:
        rounded[int(np.argmax(rounded))] += residual
    return [round(float(w), decimals + 2) for w in rounded]


def hierarchical_risk_parity(returns_matrix, labels: list[str] | None = None) -> dict:
    """
    Pesos HRP a partir de una matriz (T, N) de retornos por activo/estrategia.

    Devuelve los pesos, el orden cuasi-diagonal del árbol y las métricas de la
    cartera resultante, además de los pesos equiponderados para comparar.
    """
    M = np.asarray(returns_matrix, dtype=float)
    if M.ndim != 2 or M.shape[1] < 1:
        return {"n_assets": 0, "note": "Se requiere una matriz (T, N) de retornos."}

    T, n = M.shape
    names = labels if labels and len(labels) == n else [f"#{i + 1}" for i in range(n)]

    if n == 1:
        return {
            "n_assets": 1, "weights": {names[0]: 1.0}, "order": [0],
            "note": "Una sola estrategia: no hay nada que diversificar.",
        }
    if T < 3:
        equal = {name: round(1.0 / n, 4) for name in names}
        return {"n_assets": n, "weights": equal, "order": list(range(n)),
                "note": "Histórico común insuficiente: se reparte a partes iguales."}

    cov = np.cov(M, rowvar=False)
    sd = np.sqrt(np.diag(cov))
    # Series constantes: sin varianza no hay correlación definida.
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = cov / np.outer(sd, sd)
    corr = np.nan_to_num(corr, nan=0.0)
    np.fill_diagonal(corr, 1.0)

    order = _linkage_order(correlation_distance(corr))
    weights = _recursive_bisection(cov, order)
    total = weights.sum()
    weights = weights / total if total > 0 else np.full(n, 1.0 / n)

    hrp_var = float(weights @ cov @ weights)
    equal_w = np.full(n, 1.0 / n)
    equal_var = float(equal_w @ cov @ equal_w)

    # Concentración: 1/HHI es el "nº efectivo de estrategias" de la cartera.
    hhi = float(np.sum(weights ** 2))

    rounded = _round_preserving_sum(weights)
    return {
        "n_assets": n,
        "weights": {names[i]: rounded[i] for i in range(n)},
        "order": [int(i) for i in order],
        "ordered_labels": [names[i] for i in order],
        "portfolio_volatility": round(float(np.sqrt(max(hrp_var, 0.0))), 6),
        "equal_weight_volatility": round(float(np.sqrt(max(equal_var, 0.0))), 6),
        "effective_n_strategies": round(1.0 / hhi, 2) if hhi > 0 else float(n),
        "mean_correlation": round(
            float(corr[np.triu_indices(n, k=1)].mean()) if n > 1 else 0.0, 4
        ),
        "note": (
            "Pesos por paridad de riesgo jerárquica: clustering por correlación, "
            "reordenación cuasi-diagonal y bisección recursiva por varianza "
            "inversa. No invierte la matriz de covarianzas, que es lo que hace "
            "que la optimización media-varianza amplifique el error de "
            "estimación y produzca carteras que solo brillan dentro de muestra."
        ),
    }
