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

import math

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


# ═══════════════════════════════════════════════════════════════════
# Significancia de una PROPORCIÓN (precisión de un clasificador)
# ═══════════════════════════════════════════════════════════════════

def wilson_interval(successes: int, n: int, confidence: float = 0.95) -> dict:
    """
    Intervalo de Wilson para una proporción.

    Por qué Wilson y no el intervalo normal de toda la vida
    ──────────────────────────────────────────────────────
    El intervalo de Wald (`p ± z·√(p(1−p)/n)`) es el que sale en los manuales y
    es malo justo donde importa: con `n` moderado o `p` lejos de 0,5 da
    coberturas por debajo del nominal y llega a producir extremos fuera de
    [0, 1]. Wilson invierte el test de puntuación en lugar de aproximar la
    varianza, y su cobertura es correcta en el rango en el que trabajamos aquí
    —unos cientos de muestras y proporciones cerca de 0,5—.

    Devuelve `None` en los extremos si `n` es cero: sin muestras no hay
    intervalo, y devolver [0, 1] fingiría una medición que no existe.
    """
    n = int(n)
    if n <= 0:
        return {"point": None, "low": None, "high": None, "n": 0,
                "confidence": confidence,
                "note": "Sin muestras fuera de muestra: no hay intervalo que dar."}

    z = float(norm.ppf(0.5 + confidence / 2.0))
    p = successes / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return {
        "point": round(float(p), 4),
        "low": round(float(max(0.0, centre - half)), 4),
        "high": round(float(min(1.0, centre + half)), 4),
        "n": n,
        "confidence": confidence,
    }


def edge_significance(correct: int, n: int, baseline: float,
                      confidence: float = 0.95) -> dict:
    """
    ¿La precisión de un clasificador supera a su línea base, o es ruido?

    El problema que resuelve
    ────────────────────────
    Un veredicto del tipo «hay EDGE si la precisión supera a la base en 4 puntos»
    compara una magnitud contra un umbral sin mirar de cuántas muestras sale. Con
    500 observaciones, el error estándar de una proporción cerca de 0,5 es
    `√(0,25/500) ≈ 2,2 %`: un edge de 4 puntos son **1,8 desviaciones típicas**,
    que no alcanza la significancia ni en un contraste de una cola. El umbral no
    estaba midiendo señal, estaba midiendo ruido con un nombre bonito.

    Aquí el criterio pasa a ser el que corresponde: el edge es real si el
    **extremo inferior** del intervalo queda por encima de cero.

    Una advertencia honesta sobre el método
    ───────────────────────────────────────
    La línea base se estima de la MISMA muestra, así que la diferencia arrastra
    su incertidumbre además de la de la precisión. Aquí se trata como conocida y
    el intervalo se desplaza, lo que produce un intervalo algo **más estrecho**
    de lo que daría un contraste emparejado — es decir, la lectura GENEROSA. Se
    elige esa dirección a propósito: si ni siquiera con el criterio favorable el
    extremo inferior supera cero, la conclusión de que no hay señal es sólida.
    """
    interval = wilson_interval(correct, n, confidence)
    if interval["point"] is None:
        return {**interval, "edge": None, "edge_low": None, "edge_high": None,
                "baseline": round(float(baseline), 4), "significant": False,
                "note": interval["note"]}

    edge = interval["point"] - baseline
    low = interval["low"] - baseline
    high = interval["high"] - baseline
    significant = low > 0
    return {
        "accuracy": interval["point"],
        "accuracy_low": interval["low"],
        "accuracy_high": interval["high"],
        "baseline": round(float(baseline), 4),
        "edge": round(float(edge), 4),
        "edge_low": round(float(low), 4),
        "edge_high": round(float(high), 4),
        "n": interval["n"],
        "confidence": confidence,
        "significant": bool(significant),
        "note": (
            f"El edge se distingue de cero con {int(confidence * 100)} % de confianza "
            f"sobre {interval['n']} muestras fuera de muestra."
            if significant else
            f"El intervalo del edge cruza el cero sobre {interval['n']} muestras: "
            "la ventaja observada es compatible con el azar."
        ),
    }


def benjamini_hochberg(p_values: list[float], fdr: float = 0.10) -> dict:
    """
    Corrección por multiplicidad de Benjamini-Hochberg.

    Para qué hace falta aquí
    ────────────────────────
    Un usuario consulta el modelo sobre veinte activos y se queda con los que
    dicen que hay señal. Eso es *multiple testing* ejecutado por el propio
    producto: con edge verdadero cero y veinte consultas a un nivel del 5 %, se
    espera ver un puñado de veredictos positivos por puro azar. Sin corrección,
    **el producto fabrica falsos positivos como funcionalidad**.

    Se usa BH (control de la tasa de falsos descubrimientos) y no Bonferroni
    (control del error por familia) porque el objetivo aquí no es no equivocarse
    nunca: es acotar qué proporción de los positivos anunciados son falsos. Con
    veinte activos, Bonferroni exigiría un nivel de 0,25 % por prueba y no
    sobreviviría ninguna señal real moderada.

    Devuelve, por cada prueba, si sobrevive y su umbral, en el orden de entrada.
    """
    n = len(p_values)
    if n == 0:
        return {"n": 0, "fdr": fdr, "n_significant": 0, "results": [],
                "threshold": None,
                "note": "Sin pruebas en la familia: nada que corregir."}

    order = sorted(range(n), key=lambda i: p_values[i])
    # El mayor rango k cuyo p-valor ordenado cumple p(k) <= k/n · fdr marca el
    # corte: todo lo que quede por debajo de ese p-valor sobrevive.
    cutoff_rank = 0
    for rank, idx in enumerate(order, start=1):
        if p_values[idx] <= rank / n * fdr:
            cutoff_rank = rank
    threshold = (cutoff_rank / n * fdr) if cutoff_rank else 0.0

    survives = [False] * n
    for rank, idx in enumerate(order, start=1):
        survives[idx] = rank <= cutoff_rank

    return {
        "n": n,
        "fdr": fdr,
        "threshold": round(float(threshold), 6),
        "n_significant": cutoff_rank,
        "results": [{"p_value": p_values[i], "significant": survives[i]} for i in range(n)],
        "note": (
            f"{cutoff_rank} de {n} pruebas sobreviven a la corrección por "
            f"multiplicidad con una tasa de falsos descubrimientos del "
            f"{int(fdr * 100)} %."
        ),
    }
