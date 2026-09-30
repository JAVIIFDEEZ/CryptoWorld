"""
conformal.py — Decir «no sé» con una tasa de error controlada.

La constante que este módulo sustituye
──────────────────────────────────────
El modelo de dirección decidía NEUTRAL así:

    _NEUTRAL_BAND = 0.05
    if prob_up >= 0.55: ALCISTA
    elif prob_up <= 0.45: BAJISTA
    else: NEUTRAL

Ese 0,05 no sale de ningún sitio. Es un número elegido a mano que gobierna
cuándo la herramienta se calla, y por tanto cuántas veces se equivoca cuando
habla. No hay forma de saber si es prudente o temerario porque no está atado a
nada medible.

La predicción conformal ata esa decisión a una cifra que sí se puede pedir: **la
tasa de error que se está dispuesto a tolerar**. Se fija α = 10 % y el umbral se
CALCULA para que, a la larga, la etiqueta verdadera esté en el conjunto devuelto
el 90 % de las veces. El número deja de ser una opinión.

Cómo funciona, en una frase
───────────────────────────
Para cada observación de calibración se mide cuánta probabilidad asignó el modelo
a la etiqueta que resultó cierta. Si el modelo es bueno, esa cantidad suele ser
alta; si es malo, baja. El cuantil (1−α) de «lo mal que suele estar» es el listón:
en producción se devuelven todas las etiquetas cuya probabilidad supere ese
listón.

De ahí salen tres respuestas posibles, y la tercera es la interesante:

  · **{ALCISTA}** o **{BAJISTA}** — una sola etiqueta pasa el listón.
  · **{ALCISTA, BAJISTA}** — las dos lo pasan: el modelo no distingue, y lo dice.
    Esto es el NEUTRAL de antes, pero derivado en vez de elegido.
  · **∅** — ninguna lo pasa. La observación es atípica para lo que el modelo vio
    al calibrarse: no es que dude entre dos, es que no reconoce el terreno. Un
    conjunto vacío es información, no un error, y se reporta como tal.

Lo que NO se puede afirmar, y casi todo el mundo afirma
──────────────────────────────────────────────────────
La garantía clásica de la predicción conformal es de **muestra finita** y
**libre de distribución**, y descansa en una hipótesis: **intercambiabilidad**.
Las series financieras la violan de forma flagrante — hay dependencia temporal y
cambios de régimen, que es precisamente el motivo de que todo este motor use
purga y embargo.

En el caso general de series temporales, ningún método conformal ofrece una
garantía incondicional de cobertura en muestra finita. Quien lo venda así está
citando el teorema sin sus condiciones.

Lo que sí se puede afirmar es el resultado de la **inferencia conformal
adaptativa** (Gibbs y Candès): actualizando el nivel tras cada resultado
observado,

    α_{t+1} = α_t + γ · (α − error_t)

la tasa de fallo converge a α **a largo plazo**, sin hipótesis sobre la
distribución ni sobre la estacionariedad. Es una garantía más débil y es la
verdadera. Este módulo implementa las dos piezas y la salida distingue
explícitamente entre ellas.

Capa de dominio: NumPy puro.
"""

from __future__ import annotations

import numpy as np

# Tasa de error objetivo. Un 10 % significa: de cada diez veces que el conjunto
# devuelto excluya la etiqueta verdadera, se admite una. Es el parámetro que
# sustituye al 0,05 de la banda neutral, con la diferencia de que este sí se
# puede razonar: es la frecuencia de equivocación que se tolera.
DEFAULT_ALPHA = 0.10

# Tasa de aprendizaje de la actualización adaptativa. 0,01 es el valor habitual
# en la literatura: suficientemente pequeño para no reaccionar a un fallo aislado
# y suficientemente grande para seguir un cambio de régimen en decenas de
# observaciones.
DEFAULT_GAMMA = 0.01

# Calibración mínima. Con n observaciones, el cuantil conformal usa el índice
# ⌈(n+1)(1−α)⌉; por debajo de 1/α ese índice se sale del vector y el umbral
# degenera a «acepta todo». Con α = 0,10 hacen falta al menos 10, y se exige más
# para que el cuantil no lo decida una sola observación.
MIN_CALIBRATION = 30

LABEL_UP = "ALCISTA"
LABEL_DOWN = "BAJISTA"


def nonconformity(proba_up, labels) -> np.ndarray:
    """
    Cuánta probabilidad NO asignó el modelo a la etiqueta que resultó cierta.

    Con `proba_up` la probabilidad de subida y `labels` el resultado (1 = subió),
    la puntuación es `1 − p_verdadera`. Cero es una predicción perfecta; uno, un
    fallo total. Es la medida de «lo mal que suele estar» cuyo cuantil define el
    listón.
    """
    p = np.asarray(list(proba_up), dtype=float)
    y = np.asarray(list(labels), dtype=float)
    p_verdadera = np.where(y >= 0.5, p, 1.0 - p)
    return 1.0 - p_verdadera


def calibrate(scores, alpha: float = DEFAULT_ALPHA) -> dict:
    """
    Umbral conformal a partir de las puntuaciones de calibración.

    El cuantil usa el índice `⌈(n+1)(1−α)⌉` y no `⌈n(1−α)⌉`: la corrección de
    muestra finita del método. Con n pequeño la diferencia no es cosmética — es
    lo que separa la cobertura nominal de una cobertura sistemáticamente por
    debajo.

    Devuelve el umbral en la escala de las puntuaciones (`q_hat`) y, ya
    traducido, la probabilidad mínima que una etiqueta debe tener para entrar en
    el conjunto (`min_proba`), que es la cifra comparable con la vieja banda.
    """
    s = np.asarray(list(scores), dtype=float)
    s = s[np.isfinite(s)]
    n = s.size
    if n < MIN_CALIBRATION:
        return {
            "available": False,
            "n_calibration": int(n),
            "note": (f"Calibración insuficiente: {n} observaciones y hacen falta "
                     f"{MIN_CALIBRATION}. Con menos, el cuantil lo decide un "
                     "puñado de puntos y el umbral no significa nada."),
        }

    k = int(np.ceil((n + 1) * (1.0 - alpha)))
    if k > n:
        # Ocurre cuando n < 1/α − 1: el cuantil pedido cae fuera de la muestra.
        # Aceptar todo es la única respuesta honesta, y se dice.
        return {
            "available": True,
            "n_calibration": int(n),
            "alpha": alpha,
            "q_hat": 1.0,
            "min_proba": 0.0,
            "degenerate": True,
            "note": (f"Con {n} observaciones y α = {alpha:.0%} el cuantil pedido se "
                     "sale de la muestra: el conjunto contiene siempre las dos "
                     "etiquetas. No es un fallo, es lo que esa muestra permite."),
        }

    q_hat = float(np.sort(s)[k - 1])
    return {
        "available": True,
        "n_calibration": int(n),
        "alpha": alpha,
        "q_hat": round(q_hat, 6),
        "min_proba": round(1.0 - q_hat, 6),
        "degenerate": False,
        "note": (f"Con α = {alpha:.0%} sobre {n} observaciones, una etiqueta entra "
                 f"en el conjunto si su probabilidad supera {1.0 - q_hat:.3f}."),
    }


def _in_set(proba_up: float, q_hat: float) -> tuple[bool, bool]:
    """
    Qué etiquetas entran, decidido en el espacio de PUNTUACIONES.

    La condición canónica es `puntuación ≤ q̂`, y la puntuación de cada etiqueta
    es `1 − su probabilidad`:

        ALCISTA entra  ⟺  (1 − p) ≤ q̂
        BAJISTA entra  ⟺        p ≤ q̂

    Algebraicamente es lo mismo que `p ≥ 1 − q̂`, y numéricamente no. La forma con
    resta falla en los empates exactos: con `p = 0,05` y `q̂ = 0,95`, `1 − q̂` da
    `0,050000000000000044` y la comparación `0,05 ≥ 0,05000000000000004` sale
    FALSA — se excluye la etiqueta que debía entrar justo en el límite.

    No es hipotético. Ocurre en cuanto las probabilidades vienen cuantizadas, y
    en la calibración costó 15 puntos de cobertura sobre un modelo de prueba: se
    pedía un 90 % y salía un 74 %. Comparar en el espacio de puntuaciones evita
    la resta y el problema con ella.
    """
    p = float(proba_up)
    q = float(q_hat)
    return ((1.0 - p) <= q, p <= q)


def prediction_set(proba_up: float, q_hat: float) -> dict:
    """
    Conjunto de etiquetas para una probabilidad concreta.

    Entra toda etiqueta cuya puntuación de no conformidad no supere `q_hat`. De
    ahí las tres respuestas: una etiqueta, las dos (el modelo no distingue) o
    ninguna (la observación es atípica para lo que el modelo vio).
    """
    minimo = 1.0 - float(q_hat)
    arriba, abajo = _in_set(proba_up, q_hat)
    conjunto = []
    if arriba:
        conjunto.append(LABEL_UP)
    if abajo:
        conjunto.append(LABEL_DOWN)

    if len(conjunto) == 1:
        etiqueta, estado = conjunto[0], "DECIDIDO"
    elif len(conjunto) == 2:
        etiqueta, estado = "NEUTRAL", "AMBOS"
    else:
        # Conjunto vacío: no es duda entre dos opciones, es que ninguna encaja.
        etiqueta, estado = "NEUTRAL", "VACIO"

    return {
        "set": conjunto,
        "label": etiqueta,
        "status": estado,
        "min_proba": round(minimo, 6),
        "note": {
            "DECIDIDO": "Una sola etiqueta supera el umbral conformal.",
            "AMBOS": ("Las dos etiquetas lo superan: el modelo no distingue, y el "
                      "umbral que lo decide sale de la tasa de error pedida, no de "
                      "una constante elegida."),
            "VACIO": ("Ninguna etiqueta lo supera. La observación es atípica para lo "
                      "que el modelo vio al calibrarse: no duda entre dos, no "
                      "reconoce el terreno."),
        }[estado],
    }


def coverage(proba_up, labels, q_hat: float) -> dict:
    """
    Cobertura empírica: ¿estaba la etiqueta verdadera en el conjunto?

    Es la comprobación que convierte la teoría en una medición. Una cobertura
    muy por debajo de 1−α sobre datos posteriores a la calibración es la señal de
    que la intercambiabilidad se ha roto — es decir, de que hubo cambio de
    régimen — y es exactamente por lo que hace falta la versión adaptativa.
    """
    p = np.asarray(list(proba_up), dtype=float)
    y = np.asarray(list(labels), dtype=float)
    n = min(p.size, y.size)
    if n == 0:
        return {"n": 0, "covered_pct": None,
                "note": "Sin observaciones para medir cobertura."}
    p, y = p[:n], y[:n]

    # Igual que en `_in_set`: se compara en el espacio de puntuaciones para no
    # perder los empates exactos por el error de la resta.
    q = float(q_hat)
    dentro_up = (1.0 - p) <= q
    dentro_down = p <= q
    cubierta = np.where(y >= 0.5, dentro_up, dentro_down)
    ambos = dentro_up & dentro_down
    vacios = ~dentro_up & ~dentro_down

    return {
        "n": int(n),
        "covered_pct": round(float(cubierta.mean()) * 100, 2),
        "both_labels_pct": round(float(ambos.mean()) * 100, 2),
        "empty_pct": round(float(vacios.mean()) * 100, 2),
        "avg_set_size": round(float((dentro_up.astype(int)
                                     + dentro_down.astype(int)).mean()), 3),
        "note": (
            "El tamaño medio del conjunto es la medida de utilidad: una cobertura "
            "del 90 % con conjuntos de tamaño 2 se consigue sin saber nada — "
            "equivale a decir siempre «no sé». Lo que hay que mirar es cobertura "
            "alta CON conjuntos pequeños."
        ),
    }


class AdaptiveConformal:
    """
    Inferencia conformal adaptativa (Gibbs y Candès).

    Por qué hace falta
    ──────────────────
    La garantía conformal clásica exige intercambiabilidad, y las series
    financieras no la cumplen: hay dependencia temporal y cambios de régimen. Con
    un umbral fijo, la cobertura real se desvía de la pedida justo cuando el
    mercado cambia — y ese es el momento en que la herramienta más importa.

    Qué hace en su lugar
    ────────────────────
    Ajusta el nivel tras cada resultado observado:

        α_{t+1} = α_t + γ · (α − error_t)

    Si acaba de fallar, `error_t = 1` y α baja: el umbral se vuelve más
    conservador y los conjuntos crecen. Si acierta, α sube y los conjuntos se
    estrechan. El resultado es que la frecuencia de fallo converge a α **a largo
    plazo**, sin hipótesis sobre distribución ni estacionariedad.

    Es una garantía más débil que la de muestra finita, y es la que de verdad se
    sostiene aquí. Confundirlas es el error que este módulo documenta para no
    cometerlo.
    """

    def __init__(self, alpha: float = DEFAULT_ALPHA, gamma: float = DEFAULT_GAMMA):
        self.alpha_target = float(alpha)
        self.gamma = float(gamma)
        self.alpha_t = float(alpha)
        self.errors: list[int] = []

    def update(self, covered: bool) -> float:
        """Registra un resultado y devuelve el nuevo nivel."""
        error = 0 if covered else 1
        self.errors.append(error)
        self.alpha_t += self.gamma * (self.alpha_target - error)
        # El nivel se acota: fuera de (0,1) no define un cuantil, y al tocar los
        # extremos significa «acepta todo» o «no aceptes nada», que son las dos
        # respuestas degeneradas útiles.
        self.alpha_t = float(min(max(self.alpha_t, 1e-4), 1.0 - 1e-4))
        return self.alpha_t

    @property
    def empirical_error(self) -> float | None:
        if not self.errors:
            return None
        return float(np.mean(self.errors))

    def run(self, proba_up, labels, calibration_scores) -> dict:
        """
        Recorre una serie actualizando el nivel y devuelve el resultado.

        La calibración se mantiene fija y lo que se mueve es α: es la variante
        más simple y la que no requiere recalibrar el modelo en cada paso, que
        sería inviable dentro de un endpoint.
        """
        p = np.asarray(list(proba_up), dtype=float)
        y = np.asarray(list(labels), dtype=float)
        s = np.asarray(list(calibration_scores), dtype=float)
        s = np.sort(s[np.isfinite(s)])
        n = min(p.size, y.size)
        if n == 0 or s.size < MIN_CALIBRATION:
            return {"available": False,
                    "note": "Sin serie o sin calibración suficiente para adaptar."}

        tamanos, cubiertas, alphas = [], [], []
        for i in range(n):
            k = int(np.ceil((s.size + 1) * (1.0 - self.alpha_t)))
            q = float(s[min(k, s.size) - 1])
            arriba, abajo = _in_set(float(p[i]), q)
            cubierta = bool(arriba if y[i] >= 0.5 else abajo)
            tamanos.append(int(arriba) + int(abajo))
            cubiertas.append(cubierta)
            alphas.append(self.alpha_t)
            self.update(cubierta)

        return {
            "available": True,
            "n": int(n),
            "target_error_pct": round(self.alpha_target * 100, 2),
            "empirical_error_pct": round(float(1.0 - np.mean(cubiertas)) * 100, 2),
            "avg_set_size": round(float(np.mean(tamanos)), 3),
            "alpha_final": round(self.alpha_t, 4),
            "alpha_drift": round(float(alphas[-1] - alphas[0]), 4),
            "gamma": self.gamma,
            "note": (
                "Error empírico frente al objetivo con nivel adaptativo. La "
                "garantía es de LARGO PLAZO, no de muestra finita: la clásica "
                "exige intercambiabilidad y las series financieras no la cumplen. "
                "Un `alpha_drift` grande y negativo significa que el mercado se "
                "volvió más difícil y el método lo absorbió ensanchando conjuntos."
            ),
        }
