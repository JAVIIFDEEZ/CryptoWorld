"""
significance.py — Intervalos de confianza y significancia de las métricas.

El problema de la magnitud sin incertidumbre
────────────────────────────────────────────
«Sharpe 1.8» no es una afirmación completa. Un Sharpe de 1.8 medido sobre 60
velas y uno medido sobre 3 000 son cosas distintas: el primero es compatible con
que el Sharpe verdadero sea 0, y el segundo no. Reportar solo la magnitud invita
a leer como sólido lo que es ruido, y es el mismo error de fondo que corregía el
Deflated Sharpe, solo que a nivel de cada métrica en lugar de la selección.

El error estándar del Sharpe (Lo, 2002)
───────────────────────────────────────
    SE(SR) = √[ (1 − γ₃·SR + (γ₄−1)/4 · SR²) / (T−1) ]

donde γ₃ es la asimetría y γ₄ la curtosis. Los dos términos importan y explican
por qué los retornos financieros engañan:

  · **Asimetría negativa** —muchas ganancias pequeñas y pérdidas grandes, el
    perfil de vender volatilidad— **aumenta** el error: el Sharpe observado es
    menos fiable de lo que su magnitud sugiere.
  · **Curtosis alta** —colas gordas, que es la norma en cripto— también lo
    aumenta.

Asumir normalidad, como hace el intervalo ingenuo, subestima sistemáticamente la
incertidumbre justo en las estrategias que más lo necesitan.

Probabilistic Sharpe Ratio (Bailey & López de Prado)
────────────────────────────────────────────────────
PSR = probabilidad de que el Sharpe VERDADERO supere un umbral de referencia.
Es la misma familia que el Deflated Sharpe: el DSR es un PSR cuyo umbral se ha
subido para absorber el número de pruebas. Aquí el umbral por defecto es 0 —
«¿hay edge?»— y es configurable.

Capa de dominio: NumPy y SciPy, sin framework.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import kurtosis, norm, skew


def _moments(returns) -> tuple | None:
    """
    (SR por periodo, asimetría, curtosis total, T). Curtosis 3 = normal.

    None si la serie no admite un Sharpe: demasiado corta, o constante. Una
    estrategia que no opera da retornos planos, y ahí no hay ni magnitud ni
    incertidumbre que reportar — devolver ceros sugeriría una certeza que no
    existe.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    T = r.size
    if T < 4:
        return None
    sd = float(r.std(ddof=1))
    if sd <= 0:
        return None
    sk = float(skew(r))
    ku = float(kurtosis(r, fisher=False))
    if not np.isfinite(sk):
        sk = 0.0
    if not np.isfinite(ku):
        ku = 3.0
    return float(r.mean() / sd), sk, ku, T


def sharpe_standard_error(returns) -> float | None:
    """
    Error estándar del Sharpe por periodo, corregido por asimetría y curtosis.

    None si la serie es demasiado corta o constante: no hay incertidumbre que
    estimar sobre algo que no varía, y devolver un cero sugeriría certeza.
    """
    moments = _moments(returns)
    if moments is None:
        return None
    sr, sk, ku, T = moments
    variance = (1.0 - sk * sr + (ku - 1.0) / 4.0 * sr ** 2) / (T - 1)
    if variance <= 0:
        return None
    return float(np.sqrt(variance))


def sharpe_confidence_interval(returns, ppy: float = 365.0,
                               confidence: float = 0.95) -> dict:
    """
    Intervalo de confianza del Sharpe ANUALIZADO.

    El intervalo se calcula por periodo y se anualiza al final multiplicando por
    √ppy — anualizar primero y aplicar el error después mezclaría escalas.
    """
    moments = _moments(returns)
    se = sharpe_standard_error(returns)
    if moments is None or se is None:
        return {"sharpe": None,
                "note": "Serie demasiado corta o constante para un intervalo."}
    sr, sk, ku, T = moments

    z = float(norm.ppf(0.5 + confidence / 2.0))
    scale = float(np.sqrt(ppy))
    lower, upper = (sr - z * se) * scale, (sr + z * se) * scale

    return {
        "sharpe": round(sr * scale, 3),
        "ci_lower": round(lower, 3),
        "ci_upper": round(upper, 3),
        "confidence": confidence,
        "standard_error": round(se * scale, 4),
        "observations": int(T),
        "skew": round(sk, 3),
        "kurtosis": round(ku, 3),
        # El dato accionable: si el intervalo incluye el 0, la magnitud del
        # Sharpe no permite descartar que no haya edge en absoluto.
        "excludes_zero": bool(lower > 0),
        "note": (
            f"Sharpe {sr * scale:.2f} (IC {confidence * 100:.0f}%: "
            f"{lower:.2f} a {upper:.2f}) sobre {T} observaciones."
            + ("" if lower > 0 else
               " El intervalo incluye el cero: con estos datos no puede "
               "descartarse que no haya edge.")
        ),
    }


def probabilistic_sharpe_ratio(returns, benchmark_sharpe: float = 0.0,
                               ppy: float = 365.0) -> dict:
    """
    PSR: probabilidad de que el Sharpe verdadero supere `benchmark_sharpe`.

    `benchmark_sharpe` se da ANUALIZADO por comodidad y se convierte a la escala
    por periodo internamente. Con umbral 0 responde a «¿hay edge?»; con un
    umbral mayor, a «¿supera a lo que ya tengo?».

    Es la misma familia que el Deflated Sharpe: el DSR es un PSR cuyo umbral se
    ha elevado para absorber el número de configuraciones probadas. Este mide la
    incertidumbre de UNA serie; aquel, la del proceso de selección.
    """
    moments = _moments(returns)
    if moments is None:
        return {"psr": None,
                "note": "Serie demasiado corta o constante para estimar significancia."}
    sr, sk, ku, T = moments

    sr0 = float(benchmark_sharpe) / float(np.sqrt(ppy))
    denom = 1.0 - sk * sr + (ku - 1.0) / 4.0 * sr ** 2
    if denom <= 0:
        return {"psr": None, "note": "Momentos degenerados: PSR no estimable."}

    psr = float(norm.cdf((sr - sr0) * np.sqrt(T - 1) / np.sqrt(denom)))
    return {
        "psr": round(psr, 4),
        "benchmark_sharpe": round(float(benchmark_sharpe), 3),
        "observations": int(T),
        # Nº de observaciones que harían falta para afirmar el edge con 95 %.
        "min_track_record_length": _min_track_record(sr, sr0, sk, ku),
        "note": (
            f"Probabilidad del {psr * 100:.0f}% de que el Sharpe verdadero supere "
            f"{benchmark_sharpe:.2f}."
            + ("" if psr >= 0.95 else
               " Por debajo del 95%: la evidencia todavía no basta para afirmarlo.")
        ),
    }


def _min_track_record(sr: float, sr0: float, sk: float, ku: float,
                      confidence: float = 0.95) -> int | None:
    """
    Observaciones mínimas para declarar el edge significativo (Bailey & LdP).

    Convierte la pregunta «¿es fiable?» en «¿cuánto histórico falta?», que es
    accionable en lugar de un veredicto seco.
    """
    if sr <= sr0:
        return None          # sin exceso sobre el umbral, ningún histórico basta
    z = float(norm.ppf(confidence))
    excess_sq = (sr - sr0) ** 2
    if excess_sq <= 0:
        return None
    n = 1.0 + (1.0 - sk * sr + (ku - 1.0) / 4.0 * sr ** 2) * (z ** 2) / excess_sq
    return int(np.ceil(n)) if np.isfinite(n) and n > 0 else None


def annotate(returns, ppy: float = 365.0, benchmark_sharpe: float = 0.0) -> dict:
    """
    Bloque de significancia listo para acompañar a cualquier métrica reportada.

    Junta intervalo y PSR en una sola llamada, porque separar magnitud de
    incertidumbre en dos sitios distintos es cómo se acaban mostrando solo
    magnitudes.
    """
    ci = sharpe_confidence_interval(returns, ppy)
    psr = probabilistic_sharpe_ratio(returns, benchmark_sharpe, ppy)
    significant = bool(ci.get("excludes_zero") and (psr.get("psr") or 0) >= 0.95)
    return {
        "confidence_interval": ci,
        "probabilistic_sharpe": psr,
        "significant": significant,
        "note": (
            "El Sharpe es estadísticamente distinguible de cero con este histórico."
            if significant else
            "La magnitud del Sharpe no basta con este histórico: podría ser ruido."
        ),
    }
