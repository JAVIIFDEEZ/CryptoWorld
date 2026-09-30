"""
correlation_heatmap.py — Un mapa de calor que no invita a leer lo que no hay.

Por qué un mapa de calor de correlaciones suele ser un adorno peligroso
─────────────────────────────────────────────────────────────────────
Casi todos tienen los mismos tres defectos, y los tres empujan a la misma
conclusión equivocada:

1. **Ordenados alfabéticamente.** El orden esconde la estructura. Una cartera con
   dos bloques claros —los que siguen a Bitcoin y los que no— parece ruido
   uniforme si ADA va antes que BTC por el abecedario. El orden correcto es el
   que deja juntos a los parecidos, y ya existe en este motor: es el mismo
   recorrido de hojas que usa la paridad de riesgo jerárquica.
2. **Sin error de estimación.** Una correlación calculada sobre 30 velas tiene un
   error típico de 1/√27 ≈ 0,19 en el espacio de Fisher. Pintar 0,62 y 0,58 con
   colores distintos, cuando el ruido es tres veces esa diferencia, es mentir con
   un degradado. Aquí el error se calcula, se publica, y cada celda dice si su
   CAMBIO respecto a la referencia supera lo que el ruido explica.
3. **Solo el nivel, nunca el cambio.** El nivel de la correlación es lo que se
   miró al construir la cartera; lo que rompe la cartera es que ese nivel se
   mueva. Así que se devuelven las dos capas.

El número que resume el mapa
────────────────────────────
Una matriz entera no se lee de un vistazo, así que se reduce a dos cifras del
espectro de autovalores, que es donde vive la diversificación de verdad:

  · **Cuota del primer autovalor** — qué fracción de la varianza total explica un
    único factor común. En cripto suele ser alta, y decirlo con un número es más
    honesto que pintar quince casillas rojas: si el primer factor explica el 75 %,
    la cartera es una posición apalancada en ese factor con adornos.
  · **Número efectivo de apuestas** — la exponencial de la entropía del espectro
    normalizado. Con n activos independientes vale n; con n activos que se mueven
    igual, vale 1. Es la traducción de «cuántos riesgos distintos tengo de verdad»
    y no depende de ninguna elección de umbral.

Los retornos entran desvolatilizados, igual que en el detector de rupturas: la
correlación de una ventana convulsa se estima con más ruido, y sin corregirlo el
mapa cambia de color cuando cambia la volatilidad y no la relación.

Capa de dominio: NumPy puro, sin acceso a datos ni a red.
"""

from __future__ import annotations

import numpy as np

from core.domain.services import hrp
from core.domain.services import structural_break as sb

# Ventana de la correlación que se pinta, en velas.
DEFAULT_WINDOW = 90

# Activos mínimos y máximos. El máximo no es capricho: la ordenación por
# aglomeración es O(n³) y un mapa de 60×60 no se lee de todas formas.
MIN_ASSETS = 2
MAX_ASSETS = 40

# Múltiplo del error típico a partir del cual un cambio se considera mayor que el
# ruido. 2 es el equivalente aproximado de un contraste al 5 % por celda, y se
# declara como tal: son n(n−1)/2 celdas y no lleva corrección por multiplicidad,
# así que sirve para mirar y no para afirmar.
NOISE_SIGMAS = 2.0

# Umbrales del veredicto sobre la cuota del primer factor.
CONCENTRADO = 0.65
REPARTIDO = 0.40


def _clean_matrix(returns_by_symbol: dict, devol: bool = True):
    """Retornos alineados en matriz, desvolatilizados y con los símbolos usables.

    Alinea por POSICIÓN y exige la misma longitud: quien llame tiene que haber
    unido las series por marca temporal antes. Es el mismo error que en el
    vigilante de correlaciones —dos series desfasadas una barra no dan una
    correlación mal estimada, dan otra cantidad— y aquí se corta rechazando lo que
    no cuadre en vez de recortando en silencio.
    """
    usables, series = [], []
    largos = {len(v) for v in returns_by_symbol.values()}
    if len(largos) > 1:
        return [], np.empty((0, 0))

    for simbolo in sorted(returns_by_symbol):
        v = np.asarray(returns_by_symbol[simbolo], dtype=float)
        v = np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0)
        d = sb.devolatilize(v) if devol else v
        if d.size == 0 or not np.isfinite(d).all() or float(np.std(d)) <= 0:
            continue
        usables.append(simbolo)
        series.append(d)

    if len(usables) < MIN_ASSETS:
        return [], np.empty((0, 0))
    return usables[:MAX_ASSETS], np.vstack(series[:MAX_ASSETS])


def _corr(matriz: np.ndarray) -> np.ndarray:
    """Correlación de Pearson por filas, con la diagonal exacta."""
    if matriz.shape[0] == 0 or matriz.shape[1] < 2:
        return np.empty((0, 0))
    c = np.corrcoef(matriz)
    c = np.atleast_2d(np.nan_to_num(c, nan=0.0))
    np.fill_diagonal(c, 1.0)
    return np.clip(c, -1.0, 1.0)


def eigen_summary(corr: np.ndarray) -> dict:
    """Cuota del primer factor y número efectivo de apuestas.

    El número efectivo es `exp(−Σ pᵢ·ln pᵢ)` sobre el espectro normalizado. Con n
    activos independientes la matriz es la identidad, todos los autovalores valen
    1, la entropía es ln n y el número efectivo vale n. Con n activos que se mueven
    igual, un autovalor se lleva todo y vale 1. No depende de ningún umbral, que
    es lo que lo hace comparable entre carteras de tamaños distintos.
    """
    if corr.size == 0:
        return {"top_share": None, "effective_bets": None, "n": 0}
    valores = np.linalg.eigvalsh(corr)
    valores = np.clip(valores, 0.0, None)
    total = float(valores.sum())
    if total <= 0:
        return {"top_share": None, "effective_bets": None, "n": int(corr.shape[0])}
    p = valores / total
    p = p[p > 0]
    entropia = float(-(p * np.log(p)).sum())
    return {
        "n": int(corr.shape[0]),
        "top_share": float(valores.max() / total),
        "effective_bets": float(np.exp(entropia)),
        "eigenvalues": [round(float(v), 4) for v in np.sort(valores)[::-1]],
    }


def average_offdiagonal(corr: np.ndarray) -> float | None:
    """Correlación media fuera de la diagonal."""
    n = corr.shape[0] if corr.size else 0
    if n < 2:
        return None
    fuera = ~np.eye(n, dtype=bool)
    return float(corr[fuera].mean())


def heatmap(returns_by_symbol: dict, window: int = DEFAULT_WINDOW,
            reference_window: int | None = None, devol: bool = True,
            noise_sigmas: float = NOISE_SIGMAS) -> dict:
    """Mapa de calor ordenado por conglomerados, con su error y su cambio.

    `window` son las velas finales con las que se calcula la matriz que se pinta.
    `reference_window` son las velas ANTERIORES a esa ventana con las que se
    calcula la referencia: no se solapan a propósito, porque dos matrices que
    comparten datos tendrían un cambio artificialmente pequeño y el mapa diría que
    nada se mueve.
    """
    simbolos, matriz = _clean_matrix(returns_by_symbol, devol)
    if not simbolos:
        return {"verdict": "SIN_DATOS", "labels": [], "matrix": [],
                "note": (f"Hacen falta al menos {MIN_ASSETS} activos con series de "
                         f"la misma longitud y más de {sb.DEVOL_WARMUP} retornos "
                         f"cada una.")}

    w = max(int(window), sb.MIN_CORR_WINDOW)
    n_ret = matriz.shape[1]
    if n_ret < w:
        return {"verdict": "SIN_DATOS", "labels": simbolos, "matrix": [],
                "note": (f"Con {n_ret} retornos utilizables no se puede calcular "
                         f"una correlación de ventana {w}.")}

    actual = _corr(matriz[:, -w:])
    orden = hrp.seriation_order(actual)
    etiquetas = [simbolos[i] for i in orden]
    actual_ord = actual[np.ix_(orden, orden)]

    # Error típico de cada celda, en el espacio de Fisher y traído de vuelta. Es
    # la cifra que impide leer un degradado como si fuera exacto.
    se_z = sb.fisher_z_se(w)

    salida = {
        "labels": etiquetas,
        "matrix": [[round(float(v), 4) for v in fila] for fila in actual_ord],
        "window": w,
        "devolatilized": bool(devol),
        "returns_used": int(n_ret),
        "warmup_returns_dropped": int(
            (len(next(iter(returns_by_symbol.values()))) - n_ret) if devol else 0),
        "cell_se_z": round(float(se_z), 4),
        "average_correlation": average_offdiagonal(actual_ord),
        "eigen": eigen_summary(actual_ord),
        "ordering": ("Conglomerados por enlace simple sobre la distancia "
                     "√(0.5·(1−ρ)), el mismo recorrido que usa la paridad de riesgo "
                     "jerárquica. Alfabético esconde los bloques."),
    }

    ref = int(reference_window) if reference_window else w
    if n_ret >= w + ref:
        # Referencia SIN solape con la ventana pintada.
        anterior = _corr(matriz[:, -(w + ref):-w])
        anterior_ord = anterior[np.ix_(orden, orden)]
        delta = actual_ord - anterior_ord
        # El cambio se juzga en el espacio de Fisher, donde el error típico no
        # depende del nivel: caer de 0,90 a 0,80 es un cambio mucho mayor, en
        # unidades de error, que caer de 0,10 a 0,00.
        dz = sb.fisher_z(actual_ord) - sb.fisher_z(anterior_ord)
        umbral = float(noise_sigmas) * se_z * np.sqrt(2.0)
        notable = np.abs(dz) > umbral
        np.fill_diagonal(notable, False)

        salida.update({
            "reference_window": ref,
            "reference_matrix": [[round(float(v), 4) for v in f]
                                 for f in anterior_ord],
            "delta": [[round(float(v), 4) for v in f] for f in delta],
            "delta_beyond_noise": [[bool(v) for v in f] for f in notable],
            "delta_threshold_z": round(umbral, 4),
            "pairs_beyond_noise": int(notable.sum() // 2),
            "reference_average_correlation": average_offdiagonal(anterior_ord),
            "reference_eigen": eigen_summary(anterior_ord),
            "delta_note": (
                f"El cambio se marca cuando supera {noise_sigmas:g} errores típicos "
                f"de la diferencia en el espacio de Fisher (umbral {umbral:.3f}). Son "
                f"{len(etiquetas) * (len(etiquetas) - 1) // 2} celdas sin corrección "
                f"por multiplicidad: la marca sirve para mirar, no para afirmar. Para "
                f"afirmar está el detector de rupturas, que calibra su umbral."),
        })
    else:
        salida["reference_note"] = (
            f"Sin referencia: harían falta {w + ref} retornos y hay {n_ret}. La "
            f"referencia NO se solapa con la ventana pintada a propósito, porque dos "
            f"matrices que comparten datos darían un cambio artificialmente pequeño.")

    salida["verdict"] = _verdict(salida["eigen"])
    salida["note"] = _note(salida)
    return salida


def _verdict(eigen: dict) -> str:
    cuota = eigen.get("top_share")
    if cuota is None:
        return "SIN_DATOS"
    if cuota >= CONCENTRADO:
        return "CONCENTRADO"
    if cuota <= REPARTIDO:
        return "REPARTIDO"
    return "INTERMEDIO"


def _note(salida: dict) -> str:
    eigen = salida.get("eigen") or {}
    cuota = eigen.get("top_share")
    apuestas = eigen.get("effective_bets")
    n = eigen.get("n") or 0
    if cuota is None:
        return "No hay matriz que resumir."

    base = (f"Un único factor común explica el {cuota:.0%} de la varianza de los "
            f"{n} activos, y el número efectivo de apuestas es {apuestas:.1f} de "
            f"{n}. ")
    if salida["verdict"] == "CONCENTRADO":
        base += ("La cartera es, en la práctica, una posición apalancada en ese "
                 "factor con adornos: repartirla entre más de estos activos no "
                 "reduce el riesgo, lo multiplica por el número de comisiones. ")
    elif salida["verdict"] == "REPARTIDO":
        base += "Hay riesgos distintos de verdad dentro de la cartera. "

    cambios = salida.get("pairs_beyond_noise")
    if cambios is not None:
        base += (f"{cambios} parejas cambiaron más de lo que explica el ruido de "
                 f"estimación desde la ventana de referencia.")
    else:
        base += salida.get("reference_note", "")
    return base


def self_note() -> str:
    """Lo que este mapa no dice."""
    return (
        "Cada celda es una ESTIMACIÓN con error, no un número. Con ventana 90 el "
        "error típico en el espacio de Fisher es de 0,11, así que dos celdas que "
        "difieren en menos de eso son la misma celda pintada distinta. Por eso el "
        "error viaja en la salida y el cambio se marca solo cuando lo supera.\n"
        "Las marcas de cambio NO llevan corrección por multiplicidad: son "
        "n(n−1)/2 comparaciones y con veinte activos son 190, así que unas diez "
        "aparecerán marcadas sin que nada haya cambiado. Sirven para dirigir la "
        "mirada; para afirmar que una correlación se ha roto está el detector de "
        "rupturas, que calibra su umbral contra el nulo de cada pareja.\n"
        "Y la correlación es lineal y contemporánea: no ve una relación que se "
        "vuelve no lineal, ni una que actúa con retardo. Dos activos con "
        "correlación cero a la misma vela pueden tener una relación fuerte con un "
        "desfase de una hora, y eso lo mide el estudio de adelanto-retardo, no "
        "este mapa."
    )
