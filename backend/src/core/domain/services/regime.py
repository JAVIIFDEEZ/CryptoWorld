"""
regime.py — Detección de régimen y estabilidad temporal del edge.

Dos preguntas que un filtro ADX estático no responde:

  1. **¿En qué régimen vive este mercado?** Alta o baja volatilidad, tendencia o
     rango. Un edge no es una propiedad absoluta de una estrategia: es una
     propiedad de la pareja estrategia-régimen. Saber en cuál funciona es la
     diferencia entre desactivarla a tiempo y descubrirlo con el drawdown.

  2. **¿El edge está repartido o concentrado?** Una estrategia cuyo beneficio
     entero sale de un 10 % del histórico no tiene edge: tuvo un buen trimestre.
     Es una de las causas número uno de fallo fuera de muestra, y no la detecta
     ningún walk-forward que promedie tramos.

El detector de régimen es un clasificador por volatilidad realizada con
histéresis, no un HMM. Es una decisión deliberada: un HMM de dos o tres estados
sobre una sola serie de retornos añade un ajuste por máxima verosimilitud —es
decir, más parámetros que estimar y más superficie de sobreajuste— para producir
una clasificación que en la práctica sigue de cerca a los cuantiles de
volatilidad. Con la histéresis se evita el defecto real del umbral simple, que
es parpadear en la frontera.

Capa de dominio: NumPy puro.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

CALM, NORMAL, TURBULENT = "calm", "normal", "turbulent"


@dataclass(frozen=True)
class RegimeConfig:
    """Parámetros del clasificador de régimen."""
    vol_window: int = 20         # ventana de volatilidad realizada
    calm_quantile: float = 0.33  # por debajo → régimen tranquilo
    turbulent_quantile: float = 0.67
    # Margen de histéresis: hay que superar el umbral por este factor para
    # CAMBIAR de régimen. Sin él, una serie que roza la frontera alterna de
    # etiqueta cada pocas velas y el régimen deja de significar nada.
    hysteresis: float = 0.1


def detect_regimes(close, config: RegimeConfig | None = None) -> dict:
    """
    Clasifica cada vela en régimen tranquilo / normal / turbulento.

    Los umbrales salen de los cuantiles de la propia serie, así que la
    clasificación es relativa a su historia: «turbulento» significa turbulento
    *para este activo*, no por encima de un número fijo que no significaría lo
    mismo en BTC y en una stablecoin.

    Los umbrales se calculan sobre toda la serie a propósito: esto es una
    herramienta de ANÁLISIS del histórico, no una señal operativa. Para decidir
    en vivo hay que usar `current_regime`, que estima con datos hasta la vela.
    """
    cfg = config or RegimeConfig()
    c = np.asarray(close, dtype=float)
    if c.size < cfg.vol_window + 5:
        return {"n": 0, "note": "Serie insuficiente para clasificar regímenes."}

    returns = np.zeros(c.size)
    returns[1:] = np.diff(c) / np.where(c[:-1] != 0, c[:-1], 1.0)

    vol = np.full(c.size, np.nan)
    for i in range(cfg.vol_window, c.size):
        vol[i] = float(np.std(returns[i - cfg.vol_window:i], ddof=1))
    valid = vol[np.isfinite(vol)]
    if valid.size < 3:
        return {"n": 0, "note": "Volatilidad no estimable en esta serie."}

    lo = float(np.quantile(valid, cfg.calm_quantile))
    hi = float(np.quantile(valid, cfg.turbulent_quantile))

    labels: list[str] = []
    current = NORMAL
    for v in vol:
        if not np.isfinite(v):
            labels.append(NORMAL)
            continue
        # Histéresis: salir del régimen actual exige rebasar el umbral con
        # margen; mantenerse en él, no.
        if current == CALM:
            current = NORMAL if v > lo * (1 + cfg.hysteresis) else CALM
        elif current == TURBULENT:
            current = NORMAL if v < hi * (1 - cfg.hysteresis) else TURBULENT
        else:
            if v < lo * (1 - cfg.hysteresis):
                current = CALM
            elif v > hi * (1 + cfg.hysteresis):
                current = TURBULENT
        labels.append(current)

    counts = {r: labels.count(r) for r in (CALM, NORMAL, TURBULENT)}
    switches = sum(1 for a, b in zip(labels, labels[1:]) if a != b)
    return {
        "n": len(labels),
        "labels": labels,
        "counts": counts,
        "thresholds": {"calm_below": round(lo, 6), "turbulent_above": round(hi, 6)},
        "switches": switches,
        "current": labels[-1],
        "note": (
            f"{counts[CALM]} velas en calma, {counts[NORMAL]} normales y "
            f"{counts[TURBULENT]} turbulentas, con {switches} cambios de régimen."
        ),
    }


def current_regime(close, config: RegimeConfig | None = None) -> dict:
    """
    Régimen de la última vela usando SOLO datos hasta ella.

    Es la versión utilizable en vivo: los umbrales se estiman con el histórico
    disponible en ese momento, sin mirar hacia delante.
    """
    cfg = config or RegimeConfig()
    c = np.asarray(close, dtype=float)
    if c.size < cfg.vol_window + 5:
        return {"regime": NORMAL, "note": "Histórico insuficiente: se asume normal."}
    out = detect_regimes(c[:-1], cfg)
    if out.get("n", 0) == 0:
        return {"regime": NORMAL, "note": out.get("note", "")}
    return {"regime": out["current"], "thresholds": out["thresholds"]}


def performance_by_regime(bar_returns, labels: list[str]) -> dict:
    """
    Reparte el rendimiento entre regímenes: ¿dónde vive el edge?

    Saber que una estrategia solo gana en régimen turbulento no la invalida —
    la convierte en una estrategia de régimen, que es una decisión de cartera
    perfectamente legítima. Lo que no es legítimo es no saberlo.
    """
    r = np.asarray(bar_returns, dtype=float)
    if r.size == 0 or len(labels) == 0:
        return {"note": "Sin datos para repartir por régimen."}

    length = min(r.size, len(labels))
    r, labs = r[:length], labels[:length]

    out: dict[str, dict] = {}
    for regime in (CALM, NORMAL, TURBULENT):
        mask = np.array([lab == regime for lab in labs])
        segment = r[mask]
        if segment.size < 2:
            out[regime] = {"bars": int(segment.size), "note": "Muestra insuficiente."}
            continue
        sd = float(segment.std(ddof=1))
        out[regime] = {
            "bars": int(segment.size),
            "share_pct": round(segment.size / length * 100, 1),
            "mean_return": round(float(segment.mean()), 6),
            "total_return_pct": round(float((np.prod(1 + segment) - 1) * 100), 2),
            "sharpe_per_period": round(float(segment.mean() / sd), 4) if sd > 0 else 0.0,
        }
    return out


def temporal_stability(bar_returns, n_buckets: int = 10) -> dict:
    """
    ¿El beneficio está repartido en el tiempo o concentrado en un tramo?

    Se parte la serie en `n_buckets` periodos iguales y se mide qué fracción del
    beneficio total aporta cada uno. Si un solo periodo explica casi todo, la
    estrategia no tiene edge: tuvo una racha. Es una de las causas número uno de
    fallo fuera de muestra y ningún walk-forward que promedie tramos la delata,
    porque el promedio es justamente lo que la esconde.

    `concentration` es la fracción del beneficio que aporta el mejor periodo, y
    `stable` exige además que la mayoría de periodos sean positivos: un edge
    real aparece muchas veces, aunque de forma desigual.
    """
    r = np.asarray(bar_returns, dtype=float)
    n_buckets = max(2, int(n_buckets))
    if r.size < n_buckets * 3:
        return {"n_buckets": 0, "note": "Serie insuficiente para medir estabilidad."}

    chunks = np.array_split(r, n_buckets)
    profits = np.array([float(np.prod(1 + c) - 1) for c in chunks])
    positive = int((profits > 0).sum())

    total_gain = float(profits[profits > 0].sum())
    concentration = float(profits.max() / total_gain) if total_gain > 0 else 0.0

    return {
        "n_buckets": n_buckets,
        "bucket_returns_pct": [round(p * 100, 2) for p in profits],
        "positive_buckets": positive,
        "pct_buckets_positive": round(positive / n_buckets * 100, 1),
        # Fracción del beneficio total que aporta el MEJOR periodo.
        "concentration": round(concentration, 4),
        "best_bucket": int(np.argmax(profits)) + 1,
        "worst_bucket": int(np.argmin(profits)) + 1,
        "stable": bool(concentration < 0.5 and positive >= n_buckets * 0.5),
        "note": (
            f"El mejor de {n_buckets} periodos aporta el {concentration * 100:.0f}% "
            f"del beneficio y {positive} de {n_buckets} son positivos. "
            + ("El edge está repartido en el tiempo."
               if concentration < 0.5 and positive >= n_buckets * 0.5 else
               "El beneficio se concentra demasiado: se parece más a una racha "
               "que a una ventaja sostenida.")
        ),
    }
