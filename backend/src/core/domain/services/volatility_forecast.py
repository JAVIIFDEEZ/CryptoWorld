"""
volatility_forecast.py — La pregunta que sí tiene potencia estadística.

El reencuadre
─────────────
En cualquier mercado líquido la **dirección** del precio es esencialmente
impredecible: la autocorrelación de los retornos es ≈ 0. La **volatilidad** no:
la autocorrelación de |retornos| es alta y persistente, y el agrupamiento de
volatilidad es uno de los hechos estilizados más robustos que existen en
finanzas — la familia ARCH/GARCH le valió el Nobel a Engle, y los modelos HAR-RV
reportan R² fuera de muestra del orden de 0,35–0,60.

Traducido a tamaño de muestra, con los mismos datos y el mismo esfuerzo:

    Pregunta                          Efecto típico     Observaciones OOS
    Dirección (edge 1–2 %)            marginal          4.900 – 19.600
    Volatilidad (ρ = 0,30)            modesto           85
    Volatilidad (ρ = 0,45)            típico HAR-RV     36

Con unos cientos de observaciones fuera de muestra, la primera pregunta no se
puede responder ni aunque la respuesta exista. La segunda sí. Ese es el punto: no
es una cuestión de mejores modelos, es de a qué pregunta alcanza la muestra.

Qué hay aquí
────────────
El aparato mínimo para **falsar** esa afirmación sobre datos propios, no para
darla por buena: volatilidad realizada, el modelo HAR de referencia, las dos
líneas base contra las que hay que ganar (persistencia y HAR), R² fuera de
muestra y el contraste de Diebold-Mariano para decir si la diferencia entre dos
predictores se distingue del azar.

La línea base es lo que hace honesto el ejercicio. Un R² de 0,45 prediciendo
volatilidad suena magnífico y puede ser peor que repetir el valor de ayer: la
volatilidad es tan persistente que la persistencia sola ya explica muchísimo.
Sin comparar contra ella, cualquier modelo parece bueno.

Capa de dominio: Python puro (numpy), sin sklearn ni Django.
"""

from __future__ import annotations

import numpy as np

# Retardos del HAR clásico, en múltiplos de la ventana de volatilidad
# realizada. Corresponden a los componentes diario / semanal / mensual del
# modelo de Corsi: el mercado tiene participantes con horizontes distintos y
# cada uno deja su huella en una escala.
HAR_LAGS: tuple[int, int, int] = (1, 5, 22)


def realized_volatility(returns, window: int) -> np.ndarray:
    """
    Volatilidad realizada sobre las últimas `window` velas, causal.

    Raíz de la suma de retornos al cuadrado, que es el estimador estándar. La
    posición `i` usa las velas `[i-window+1, i]` — solo pasado. Las primeras
    `window-1` salen NaN en vez de calcularse con menos datos: rellenarlas con
    una ventana parcial daría valores sistemáticamente más bajos al principio de
    la serie, y el modelo aprendería que «al principio hay poca volatilidad».
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    out = np.full(n, np.nan)
    if window < 1 or n < window:
        return out
    sq = r * r
    cumulative = np.concatenate([[0.0], np.cumsum(sq)])
    sums = cumulative[window:] - cumulative[:-window]
    out[window - 1:] = np.sqrt(sums)
    return out


def future_volatility(returns, horizon: int) -> np.ndarray:
    """
    Volatilidad realizada de las PRÓXIMAS `horizon` velas — la variable objetivo.

    La posición `i` cubre `[i+1, i+horizon]`, así que su etiqueta se resuelve
    `horizon` velas después de `i`. Ese número es exactamente el que hay que
    purgar en la validación cruzada; usar otro dejaría solapamiento.

    Las últimas `horizon` posiciones son NaN: su futuro aún no ha ocurrido.
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    out = np.full(n, np.nan)
    if horizon < 1 or n <= horizon:
        return out
    sq = r * r
    cumulative = np.concatenate([[0.0], np.cumsum(sq)])
    # Para i: suma de sq[i+1 .. i+horizon]
    out[: n - horizon] = np.sqrt(cumulative[horizon + 1:] - cumulative[1: n - horizon + 1])
    return out


def har_features(rv, lags: tuple[int, ...] = HAR_LAGS) -> np.ndarray:
    """
    Componentes HAR: media de la volatilidad realizada sobre varias escalas.

    Cada columna es la media de `rv` sobre las últimas `lag` observaciones,
    incluyendo la actual. La intuición de Corsi es que el mercado tiene
    operadores con horizontes distintos —intradía, semanal, mensual— y que cada
    uno deja huella en su escala; la suma de tres medias móviles reproduce la
    memoria larga de la volatilidad sin necesidad de un modelo fraccionario.

    Causal por construcción: la fila `i` solo usa `rv[≤ i]`.
    """
    series = np.asarray(rv, dtype=float)
    n = series.size
    cols = []
    for lag in lags:
        col = np.full(n, np.nan)
        if n >= lag:
            cumulative = np.concatenate([[0.0], np.nancumsum(series)])
            valid = np.concatenate([[0.0], np.cumsum(~np.isnan(series))])
            sums = cumulative[lag:] - cumulative[:-lag]
            counts = valid[lag:] - valid[:-lag]
            with np.errstate(invalid="ignore", divide="ignore"):
                col[lag - 1:] = np.where(counts > 0, sums / counts, np.nan)
        cols.append(col)
    return np.column_stack(cols)


class HARModel:
    """
    Regresión lineal de la volatilidad futura sobre sus componentes HAR.

    Mínimos cuadrados sobre tres regresores. Deliberadamente simple: el papel de
    este modelo en el estudio no es ganar, es **ser la línea base exigente**. Si
    algo más elaborado no lo bate, ese algo no aporta.
    """

    def __init__(self) -> None:
        self.coef_: np.ndarray | None = None

    def fit(self, X, y) -> "HARModel":
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        design = np.column_stack([np.ones(len(X)), X])
        self.coef_, *_ = np.linalg.lstsq(design, y, rcond=None)
        return self

    def predict(self, X) -> np.ndarray:
        if self.coef_ is None:
            raise ValueError("El modelo no está ajustado.")
        X = np.asarray(X, dtype=float)
        return np.column_stack([np.ones(len(X)), X]) @ self.coef_


def oos_r2(actual, predicted, baseline) -> float:
    """
    R² fuera de muestra frente a una línea base (Campbell-Thompson).

    `1 − SSE(modelo) / SSE(base)`. Positivo significa que el modelo comete menos
    error cuadrático que la base; negativo, que lo empeora.

    NO es el R² de un manual. El R² clásico compara contra la media de la
    muestra, y contra la media es fácil ganar cuando la serie es persistente:
    predecir «lo mismo que ayer» ya da un R² clásico altísimo sobre volatilidad.
    Comparar contra la base correcta es lo que separa un modelo útil de uno que
    solo ha descubierto que la volatilidad se agrupa.
    """
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    b = np.asarray(baseline, dtype=float)
    ok = np.isfinite(a) & np.isfinite(p) & np.isfinite(b)
    if ok.sum() < 3:
        return float("nan")
    sse_model = float(np.sum((a[ok] - p[ok]) ** 2))
    sse_base = float(np.sum((a[ok] - b[ok]) ** 2))
    if sse_base <= 0:
        return float("nan")
    return 1.0 - sse_model / sse_base


def diebold_mariano(errors_a, errors_b, horizon: int = 1) -> dict:
    """
    ¿Predice B mejor que A, o la diferencia cabe dentro del azar?

    Contraste de Diebold-Mariano sobre el diferencial de pérdida cuadrática. Es
    el análogo, para predicción continua, del contraste emparejado que se usa
    con clasificadores: compara los dos predictores **sobre las mismas
    observaciones** en vez de mirar dos métricas agregadas por separado.

    La corrección de Newey-West no es opcional aquí. Con horizonte `h > 1` las
    predicciones se solapan —la de `t` y la de `t+1` comparten `h−1` velas de
    futuro— y sus errores están autocorrelacionados por construcción. Ignorarlo
    subestima la varianza y produce significancia donde no la hay; es el mismo
    error que la falta de purga, cometido en el otro extremo del cálculo.

    Devuelve el estadístico, el p-valor de una cola (¿B mejor que A?) y el
    veredicto.
    """
    ea = np.asarray(errors_a, dtype=float)
    eb = np.asarray(errors_b, dtype=float)
    ok = np.isfinite(ea) & np.isfinite(eb)
    d = ea[ok] ** 2 - eb[ok] ** 2      # positivo = B comete menos error
    n = d.size
    if n < 10:
        return {"n": int(n), "statistic": None, "p_value": None, "better": False,
                "note": "Muestra insuficiente para el contraste."}

    mean_d = float(d.mean())
    # Varianza de largo plazo con ventana de Bartlett: los solapamientos del
    # horizonte hacen que las observaciones contiguas no sean independientes.
    lag_max = max(0, int(horizon) - 1)
    gamma0 = float(np.mean((d - mean_d) ** 2))
    variance = gamma0
    for lag in range(1, lag_max + 1):
        cov = float(np.mean((d[lag:] - mean_d) * (d[:-lag] - mean_d)))
        weight = 1.0 - lag / (lag_max + 1)
        variance += 2.0 * weight * cov
    if variance <= 0:
        return {"n": int(n), "statistic": None, "p_value": None, "better": False,
                "note": "Varianza no positiva tras la corrección de autocorrelación."}

    stat = mean_d / np.sqrt(variance / n)
    from scipy.stats import norm
    p = float(norm.sf(stat))
    return {
        "n": int(n),
        "statistic": round(float(stat), 4),
        "p_value": round(p, 6),
        "mean_loss_diff": round(mean_d, 10),
        "better": bool(p < 0.05),
        "note": (
            f"Diebold-Mariano sobre {n} predicciones solapadas (horizonte {horizon}), "
            f"con corrección de autocorrelación: p = {p:.4f}."
        ),
    }


def observations_needed(effect_r: float, power: float = 0.80,
                        alpha: float = 0.05) -> int | None:
    """
    Observaciones fuera de muestra para detectar una correlación de tamaño `r`.

    Aproximación de Fisher: con la transformación z, el error estándar es
    `1/√(n−3)`, así que `n ≈ 3 + ((z_α + z_β) / z_r)²`.

    Sirve para lo único que importa antes de elegir pregunta: saber si la
    muestra disponible alcanza. Un edge direccional del 1–2 % necesita del orden
    de cuatro a quince mil observaciones; una correlación de 0,3 sobre
    volatilidad necesita menos de cien. Con unos cientos de observaciones, la
    primera pregunta no se puede responder aunque la respuesta exista.

    Por qué una cola y no dos
    ─────────────────────────
    El cálculo de potencia tiene que dimensionar EL CONTRASTE QUE SE VA A HACER,
    no un contraste genérico. Los dos de este motor son de una cola —«¿bate el
    modelo a la línea base?», nunca «¿difiere de ella?»—, tanto el de Wilson
    sobre la precisión como el de Diebold-Mariano sobre el error cuadrático, así
    que el `z_α` que corresponde es el de una cola.

    Esto da números un 21 % MENORES que los de la literatura divulgativa, que
    suele citar la versión de dos colas: 3.863 observaciones para un edge del
    2 % en vez de 4.905. La diferencia no es un error de ninguno de los dos: es
    que el contraste de dos colas gasta la mitad de su alfa en detectar que el
    modelo es PEOR que la base, que es información que aquí no se usa. Se deja
    dicho porque un número más pequeño que el publicado invita a pensar que el
    cálculo es optimista, y conviene poder comprobar que no lo es.
    """
    r = abs(float(effect_r))
    if not 0 < r < 1:
        return None
    from scipy.stats import norm
    z_r = 0.5 * np.log((1 + r) / (1 - r))     # transformación de Fisher
    z_alpha = float(norm.ppf(1 - alpha))       # una cola
    z_beta = float(norm.ppf(power))
    return int(np.ceil(3 + ((z_alpha + z_beta) / z_r) ** 2))


def accuracy_edge_to_r(edge: float) -> float:
    """
    Traduce un edge de clasificación a la correlación equivalente, para que las
    dos preguntas se puedan comparar en la misma escala.

    Con clases equilibradas, una precisión de `0,5 + e` corresponde
    aproximadamente a `r = 2e` (coeficiente phi). Es la conversión que permite
    poner en la misma tabla «edge del 2 % en dirección» y «correlación de 0,45
    en volatilidad», y ver que la primera pide dos órdenes de magnitud más
    muestra que la segunda.
    """
    return 2.0 * abs(float(edge))
