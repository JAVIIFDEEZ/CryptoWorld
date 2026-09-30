"""
seasonality.py — ¿Hay horas del mercado que no son como las demás?

De dónde sale esta pregunta
───────────────────────────
Del estudio de eventos. Allí el hallazgo incómodo fue que un efecto de «viernes
por la mañana» se disfraza de efecto del vencimiento si el grupo de control no
conserva la casilla del calendario: la volatilidad observada salía 2,5 veces la
normal y no había ningún efecto del evento. Ese confusor quedó controlado, pero
nunca se midió. Este módulo lo mide.

No es un detalle de metodología. Si hay horas sistemáticamente más convulsas, eso
cambia tres cosas concretas: cuándo NO colocar una orden grande, cuándo un stop
tiene más probabilidad de saltar por ruido, y qué variables tienen sentido en el
modelo. Cripto opera 24/7, lo cual se suele leer como «no hay sesiones» — y es
justo lo contrario de lo que pasa: los solapes de Asia, Europa y Estados Unidos
siguen ahí, solo que nadie cierra.

El problema: 168 casillas
─────────────────────────
Una rejilla de 7 días × 24 horas son 168 contrastes. Al 5 % por casilla, **ocho
saldrán significativas sin que haya nada**, y con 168 números delante es
psicológicamente imposible no encontrarles una historia. Es el mismo defecto que
el mapa de correlaciones, multiplicado.

Se responde en dos pasos y en este orden, que es el que impide contar cuentos:

1. **Un contraste global primero.** ¿Hay ALGUNA estructura de hora de la semana?
   Se mide con la dispersión entre casillas comparada con la que produce el nulo.
   Si el global no pasa, las casillas individuales no se miran: cualquier cosa que
   se encontrara ahí sería una de las ocho.
2. **Si el global pasa, las casillas con Benjamini-Hochberg.** Se controla la
   proporción de falsos hallazgos entre las que se anuncian, y se dice cuántas
   sobreviven de cuántas se probaron.

El nulo: permutación por bloques, y por qué NO una rotación
──────────────────────────────────────────────────────────
Para preguntar «¿están los retornos alineados con la rejilla horaria?» hay que
romper esa alineación sin romper nada más. Un remuestreo suelto de los retornos
destruiría también el agrupamiento de volatilidad; conservarlo importa porque la
dependencia entre casillas vecinas afecta a la distribución del estadístico
global.

La primera versión de esto usaba una **rotación circular** —desplazar la serie
entera y volver a cruzarla con las mismas etiquetas— con el argumento de que
conserva exactamente toda la dependencia temporal. El argumento es correcto y el
nulo es inservible, y hizo falta calibrarlo para verlo: la rejilla tiene periodo
168 y un histórico de semanas completas tiene una longitud **múltiplo de 168**, así
que desplazar la serie mapea cada casilla entera sobre otra casilla. El conjunto de
medias por casilla es idéntico, la dispersión y el máximo no cambian, y el nulo
ES la observación. Medido: con la actividad duplicada en cuatro casillas, el
contraste del máximo daba p=0,57 y no se detectaba nada.

La permutación por bloques sí rompe la fase. Se parte la serie en bloques de
longitud **coprima con 168** y se permuta su orden: cada bloque aterriza en un
desfase distinto, así que las etiquetas que le toca cruzar cambian, mientras que
dentro del bloque el agrupamiento de volatilidad sigue intacto. Con bloques de 25
horas, `gcd(25, 168) = 1` y ningún bloque vuelve a su misma casilla de forma
sistemática.

Capa de dominio: NumPy puro, sin acceso a datos ni a red.
"""

from __future__ import annotations

import numpy as np

HORA_MS = 3_600_000
DIAS, HORAS = 7, 24
CASILLAS = DIAS * HORAS

# Réplicas del nulo.
DEFAULT_ROTATIONS = 500

# Longitud del bloque de la permutación, en velas. 25 y no 24: tiene que ser
# COPRIMA con 168 para que al permutar los bloques cambie el desfase de las
# etiquetas. Con 24 —o con cualquier divisor de 168— cada bloque cae siempre en la
# misma hora del día y el nulo conservaría parte de la estructura que quiere
# destruir.
DEFAULT_BLOCK = 25

# Observaciones mínimas por casilla para que su estadístico signifique algo. Con
# 20 semanas de histórico cada casilla tiene 20 observaciones; por debajo de 12 el
# ruido de la casilla domina cualquier efecto.
MIN_PER_CELL = 12

# Tasa de falsos descubrimientos de la corrección entre casillas.
DEFAULT_FDR = 0.10

# Nivel del contraste global. Se reparte entre CUATRO contrastes: dos estadísticos
# —dispersión para lo difuso, máximo para lo concentrado— por cada una de las dos
# preguntas —actividad y dirección—. Sin repartirlo, el «global» sería cuatro
# oportunidades de disparar al 5 % y la tasa real rondaría el 20 %.
GLOBAL_ALPHA = 0.05
GLOBAL_TESTS = 4

# Nombres de los días, empezando en lunes como el convenio de Python.
DAY_NAMES = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")


def week_hour_index(timestamps) -> np.ndarray:
    """Índice de casilla 0–167 de cada instante: día de la semana × 24 + hora UTC.

    El 1 de enero de 1970 fue jueves, que en el convenio de Python —lunes 0— es el
    3, así que el día de la semana es `(días + 3) % 7`.
    """
    t = np.asarray(timestamps, dtype=np.int64)
    dow = ((t // 86_400_000) + 3) % 7
    hora = (t // HORA_MS) % 24
    return (dow * HORAS + hora).astype(np.int64)


def _grid(indices: np.ndarray, valores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Media y recuento por casilla, con `bincount`.

    Vectorizado porque el nulo repite esto quinientas veces: con un `groupby` por
    rotación el módulo costaría minutos.
    """
    n = np.bincount(indices, minlength=CASILLAS).astype(float)
    suma = np.bincount(indices, weights=valores, minlength=CASILLAS)
    with np.errstate(invalid="ignore", divide="ignore"):
        media = np.where(n > 0, suma / np.maximum(n, 1), np.nan)
    return media, n


def _max_deviation(media: np.ndarray, n: np.ndarray) -> float:
    """Desviación máxima de una casilla respecto al centro ponderado.

    El compañero obligatorio de la dispersión, y está aquí porque la calibración
    demostró que sin él el módulo era ciego al caso que importa. La dispersión
    promedia sobre las 168 casillas, así que tiene potencia contra una estructura
    REPARTIDA —muchas casillas algo distintas— y casi ninguna contra una
    CONCENTRADA: con la actividad duplicada en solo cuatro casillas, el contraste
    por dispersión daba p=0,04, al borde de no detectar un efecto del doble.

    El máximo es lo contrario: ciego a lo difuso y sensible a lo concentrado. Se
    usan los dos y se reparte el nivel entre ellos.
    """
    vivo = np.isfinite(media) & (n > 0)
    if vivo.sum() < 2:
        return float("nan")
    peso = n[vivo]
    centro = float(np.average(media[vivo], weights=peso))
    return float(np.max(np.abs(media[vivo] - centro)))


def _dispersion(media: np.ndarray, n: np.ndarray) -> float:
    """Dispersión entre casillas, ponderada por su recuento.

    Es el estadístico del contraste global. Se pondera por recuento para que una
    casilla con tres observaciones no pese lo mismo que una con cincuenta; sin
    ponderar, el estadístico lo dominarían las casillas peor estimadas, que son
    justo las que menos informan.
    """
    vivo = np.isfinite(media) & (n > 0)
    if vivo.sum() < 2:
        return float("nan")
    peso = n[vivo]
    centro = float(np.average(media[vivo], weights=peso))
    return float(np.average((media[vivo] - centro) ** 2, weights=peso))


def block_permutation(values: np.ndarray, block: int, rng) -> np.ndarray:
    """La serie con sus bloques en otro orden.

    Rompe la fase respecto a la rejilla horaria y conserva el agrupamiento de
    volatilidad dentro de cada bloque. La longitud del bloque tiene que ser coprima
    con 168; si no, los bloques vuelven a caer en las mismas casillas y el nulo
    conserva justo lo que debía destruir.

    Son los mismos retornos en otro orden, exactamente: el último bloque se queda
    CORTO en vez de rellenarse dando la vuelta. Rellenar y recortar después
    duplicaba unos retornos y perdía otros, así que la distribución marginal del
    nulo no era la de la serie — pequeño, pero es justo lo que un nulo por
    permutación tiene que garantizar.
    """
    v = np.asarray(values, dtype=float)
    b = max(int(block), 1)
    if v.size == 0:
        return v.copy()
    cortes = list(range(0, v.size, b))
    bloques = [v[i:i + b] for i in cortes]
    orden = rng.permutation(len(bloques))
    return np.concatenate([bloques[i] for i in orden])


def analyse(timestamps, returns, rotations: int = DEFAULT_ROTATIONS,
            fdr: float = DEFAULT_FDR, block: int = DEFAULT_BLOCK,
            seed: int = 13) -> dict:
    """Rejilla de 7×24 con contraste global primero y casillas después.

    Mide dos cosas por casilla, y la segunda es la que suele tener señal:

      · **retorno medio** — la dirección. Si fuera sistemática y grande sería
        explotable, así que casi seguro no lo es.
      · **movimiento absoluto medio** — la actividad. Es donde está el efecto de
        sesión, y el que sirve para decidir cuándo no ejecutar.
    """
    t = np.asarray(timestamps, dtype=np.int64)
    r = np.asarray(returns, dtype=float)
    if t.size != r.size:
        return {"verdict": "SIN_DATOS",
                "note": "Marcas temporales y retornos tienen que ir alineados."}

    finito = np.isfinite(r)
    t, r = t[finito], r[finito]
    if t.size < CASILLAS * MIN_PER_CELL:
        return {
            "verdict": "SIN_DATOS", "n": int(t.size),
            "note": (f"Hacen falta al menos {CASILLAS * MIN_PER_CELL} retornos "
                     f"—{MIN_PER_CELL} por casilla de las {CASILLAS}— y hay "
                     f"{t.size}. Con menos, cada casilla es ruido y la rejilla "
                     f"entera invita a contar cuentos."),
        }

    idx = week_hour_index(t)
    abs_r = np.abs(r)

    media_ret, n = _grid(idx, r)
    media_abs, _ = _grid(idx, abs_r)
    disp_ret = _dispersion(media_ret, n)
    disp_abs = _dispersion(media_abs, n)
    max_ret = _max_deviation(media_ret, n)
    max_abs = _max_deviation(media_abs, n)

    # Nulo por permutación de bloques contra las MISMAS etiquetas de casilla.
    rng = np.random.default_rng(seed)
    nd_ret, nd_abs, nm_ret, nm_abs = [], [], [], []
    nulo_media_abs = np.empty((int(rotations), CASILLAS), dtype=float)

    validas = 0
    for _ in range(int(rotations)):
        rr = block_permutation(r, block, rng)
        m_ret, nn = _grid(idx, rr)
        m_abs, _ = _grid(idx, np.abs(rr))
        nd_ret.append(_dispersion(m_ret, nn))
        nd_abs.append(_dispersion(m_abs, nn))
        nm_ret.append(_max_deviation(m_ret, nn))
        nm_abs.append(_max_deviation(m_abs, nn))
        nulo_media_abs[validas] = m_abs
        validas += 1

    nulo_media_abs = nulo_media_abs[:validas]

    def _p(observado: float, nulo) -> float:
        v = np.asarray(nulo, dtype=float)
        v = v[np.isfinite(v)]
        if not np.isfinite(observado) or v.size < 20:
            return float("nan")
        return float((1 + np.sum(v >= observado)) / (v.size + 1))

    # Dos estadísticos globales por pregunta —dispersión para lo difuso, máximo
    # para lo concentrado— así que el nivel se reparte entre los dos.
    p_disp_ret, p_disp_abs = _p(disp_ret, nd_ret), _p(disp_abs, nd_abs)
    p_max_ret, p_max_abs = _p(max_ret, nm_ret), _p(max_abs, nm_abs)
    p_global_ret = min(v for v in (p_disp_ret, p_max_ret) if np.isfinite(v)) \
        if any(np.isfinite(v) for v in (p_disp_ret, p_max_ret)) else float("nan")
    p_global_abs = min(v for v in (p_disp_abs, p_max_abs) if np.isfinite(v)) \
        if any(np.isfinite(v) for v in (p_disp_abs, p_max_abs)) else float("nan")

    salida = {
        "n": int(t.size),
        "cells": CASILLAS,
        "rotations": validas,
        "per_cell": [int(v) for v in n],
        "min_per_cell": int(n.min()) if n.size else 0,
        "mean_return": [None if not np.isfinite(v) else float(v) for v in media_ret],
        "mean_abs_return": [None if not np.isfinite(v) else float(v)
                            for v in media_abs],
        "global": {
            "p_return": p_global_ret,
            "p_activity": p_global_abs,
            "p_dispersion_activity": p_disp_abs,
            "p_max_activity": p_max_abs,
            "p_dispersion_return": p_disp_ret,
            "p_max_return": p_max_ret,
            # El nivel se reparte entre los dos estadísticos de cada pregunta.
            "alpha": GLOBAL_ALPHA / GLOBAL_TESTS,
            "tests": GLOBAL_TESTS,
            "note": ("Contraste global antes que las casillas. Son 168 casillas: al "
                     "5 % por casilla, ocho saldrían significativas sin que haya "
                     "nada, y con 168 números delante es imposible no encontrarles "
                     "una historia. Si el global no pasa, las casillas no se miran. "
                     "Se usan DOS estadísticos: la dispersión tiene potencia contra "
                     "una estructura repartida y el máximo contra una concentrada en "
                     "pocas casillas, y con solo el primero el módulo era casi ciego "
                     "a un efecto del doble confinado en cuatro."),
        },
        "block": int(block),
        "protocol": (
            f"Nulo por PERMUTACIÓN DE BLOQUES de {block} velas contra las mismas "
            f"etiquetas de hora de la semana. Conserva el agrupamiento de "
            f"volatilidad dentro de cada bloque y destruye la alineación con la "
            f"rejilla, que es la afirmación bajo prueba. La longitud del bloque es "
            f"coprima con 168 a propósito: con un divisor de 168 —24 horas, por "
            f"ejemplo— cada bloque volvería siempre a la misma hora del día y el "
            f"nulo conservaría parte de lo que debe destruir. Por el mismo motivo NO "
            f"se usa una rotación circular: la longitud de un histórico de semanas "
            f"completas es múltiplo de 168, así que rotar solo permuta las casillas "
            f"y deja el nulo idéntico a la observación."),
    }

    umbral_global = GLOBAL_ALPHA / GLOBAL_TESTS
    hay_global = ((np.isfinite(p_global_abs) and p_global_abs < umbral_global)
                  or (np.isfinite(p_global_ret) and p_global_ret < umbral_global))
    if not hay_global:
        salida.update({
            "verdict": "SIN_ESTRUCTURA", "cells_significant": 0,
            "note": (f"El contraste global no detecta estructura de hora de la "
                     f"semana (actividad p={p_global_abs:.3f}, dirección "
                     f"p={p_global_ret:.3f}). Las casillas NO se miran: con 168 "
                     f"contrastes siempre habría alguna pequeña, y sería una de las "
                     f"ocho que regala el azar."),
        })
        return salida

    # El global pasó: ahora sí las casillas, con corrección por multiplicidad.
    salida["cell_detail"] = _cells(media_abs, nulo_media_abs, n, fdr)
    salida["fdr"] = fdr
    salida["cells_significant"] = salida["cell_detail"]["n_significant"]
    salida["verdict"] = ("CON_ESTRUCTURA" if salida["cells_significant"]
                         else "ESTRUCTURA_DIFUSA")
    salida["note"] = _note(salida)
    return salida


def _cells(media: np.ndarray, nulo: np.ndarray, n: np.ndarray, fdr: float) -> dict:
    """p-valor por casilla y luego Benjamini-Hochberg.

    Los MOMENTOS del nulo salen de las rotaciones —que es lo que captura la
    dependencia temporal de la serie— y la COLA de la normal. La mezcla no es
    pereza: es que un p-valor contado sobre R rotaciones no puede valer menos de
    1/(R+1), y con 168 casillas el umbral de Benjamini-Hochberg para la primera es
    `fdr/168`. Con 300 rotaciones el p-valor más pequeño posible es 0,0033 y el
    umbral que tiene que cruzar es 0,0006: **ninguna casilla podría pasar nunca**,
    por grande que fuera el efecto. Se midió — con la actividad duplicada en cuatro
    casillas, cero sobrevivían.

    Las dos salidas eran subir las rotaciones por encima de 168/fdr = 1.680, que
    multiplica el coste por seis para ganar solo resolución en la cola, o estimar
    la cola. La media de una casilla es la media de decenas de observaciones, así
    que el teorema central del límite la hace aproximadamente normal y la
    aproximación es defendible; queda declarada como tal en la salida.

    A dos colas: una casilla anormalmente TRANQUILA también es un hallazgo.
    """
    from math import erfc, sqrt

    from core.domain.services import significance as sig

    usable = np.isfinite(media) & (n >= MIN_PER_CELL)
    p = np.full(CASILLAS, np.nan)
    z = np.full(CASILLAS, np.nan)
    for c in np.flatnonzero(usable):
        columna = nulo[:, c]
        columna = columna[np.isfinite(columna)]
        if columna.size < 20:
            continue
        centro = float(columna.mean())
        escala = float(columna.std(ddof=1))
        if not np.isfinite(escala) or escala <= 0:
            continue
        z[c] = (media[c] - centro) / escala
        p[c] = erfc(abs(z[c]) / sqrt(2.0))      # normal a dos colas

    con_p = np.flatnonzero(np.isfinite(p))
    if con_p.size == 0:
        return {"n_significant": 0, "significant": [], "p_values": p.tolist(),
                "note": "Ninguna casilla con observaciones suficientes."}

    salida = sig.benjamini_hochberg([float(p[c]) for c in con_p], fdr=fdr)
    significativas = []
    for pos, c in enumerate(con_p):
        if salida["results"][pos]["significant"]:
            significativas.append({
                "cell": int(c),
                "day": DAY_NAMES[int(c) // HORAS],
                "hour_utc": int(c) % HORAS,
                "mean_abs_return": float(media[c]),
                "relative": float(media[c] / np.nanmean(media)) if np.nanmean(media) else None,
                "n": int(n[c]),
                "p": float(p[c]),
                "z": float(z[c]),
            })

    significativas.sort(key=lambda s: -s["mean_abs_return"])
    return {
        "n_tested": int(con_p.size),
        "n_significant": len(significativas),
        "significant": significativas,
        "p_values": [None if not np.isfinite(v) else float(v) for v in p],
        "z_scores": [None if not np.isfinite(v) else float(v) for v in z],
        "threshold": salida.get("threshold"),
        "note": (f"{len(significativas)} de {con_p.size} casillas sobreviven a "
                 f"Benjamini-Hochberg con una tasa de falsos descubrimientos del "
                 f"{fdr:.0%}. Sin la corrección, al 5 % por casilla se esperarían "
                 f"{con_p.size * 0.05:.0f} falsas."),
        "tail_note": (
            "Los momentos del nulo salen de las rotaciones y la cola de la normal. "
            "Un p-valor contado sobre R rotaciones no baja de 1/(R+1), y el umbral "
            f"de Benjamini-Hochberg para la primera de {con_p.size} casillas es "
            f"{fdr / max(con_p.size, 1):.5f}: con un recuento empírico haría falta "
            f"pasar de {int(con_p.size / max(fdr, 1e-9))} rotaciones para que alguna "
            "pudiera cruzarlo. La media de una casilla es la de decenas de "
            "observaciones, así que la normal es una aproximación defendible — pero "
            "es una aproximación."),
    }


def _note(salida: dict) -> str:
    detalle = salida.get("cell_detail") or {}
    n_sig = detalle.get("n_significant", 0)
    g = salida["global"]
    base = (f"El contraste global detecta estructura de hora de la semana "
            f"(actividad p={g['p_activity']:.3f}). ")
    if not n_sig:
        return base + ("Pero ninguna casilla concreta sobrevive a la corrección por "
                       "multiplicidad: la estructura es difusa y está repartida, no "
                       "concentrada en horas señalables. Sirve para el modelo, no "
                       "para una regla del tipo «no operar a las tres».")
    top = detalle["significant"][0]
    return base + (f"{n_sig} de {detalle['n_tested']} casillas sobreviven a la "
                   f"corrección. La más activa es {top['day']} {top['hour_utc']:02d}:00 "
                   f"UTC, con {top['relative']:.2f}× el movimiento medio. Son las "
                   f"ventanas en las que una orden grande cuesta más y un stop salta "
                   f"por ruido con más facilidad.")


def self_note() -> str:
    """Lo que esta rejilla no dice."""
    return (
        "Una casilla activa NO es una oportunidad: es lo contrario. Más movimiento "
        "con dirección impredecible significa más deslizamiento y más stops "
        "saltados por ruido, así que el uso correcto es evitarla, no buscarla. La "
        "dirección se mide aparte y casi nunca sale: si una hora subiera de forma "
        "sistemática, se descontaría.\n"
        "La rejilla es en UTC y fija. No se mueve con el horario de verano, así que "
        "una casilla que corresponda a la apertura de un mercado concreto se reparte "
        "entre dos casillas contiguas durante ocho meses al año, y el efecto "
        "aparece diluido en las dos. Es una limitación conocida y no un error: "
        "corregirla exigiría elegir a qué mercado se ancla la rejilla.\n"
        "Y el efecto medido es del histórico disponible. La estructura de sesiones "
        "cambia cuando cambia quién opera —la entrada de instituciones movió "
        "actividad hacia el horario de Nueva York—, así que una rejilla de hace tres "
        "años no describe la de ahora. El contraste global sobre tramos separados "
        "es lo que diría si ha cambiado."
    )
