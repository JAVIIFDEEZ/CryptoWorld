"""
structural_break.py — Cuándo dejar de creerse una relación que antes se cumplía.

El problema
───────────
Todo lo que este motor mide —la correlación entre dos activos, la predictibilidad
de la volatilidad, el alfa de un factor— se estima sobre una ventana de pasado y
se usa sobre un futuro que puede haber cambiado de régimen. La pregunta no es si
la relación fue real: es si SIGUE siéndolo. Y esa pregunta tiene una respuesta
que se puede vigilar en continuo con un coste ridículo, sin más datos que los
precios que ya están archivados.

El detector es un CUSUM de dos colas: acumula desviaciones estandarizadas
respecto a un nivel de referencia y salta cuando la suma acumulada supera un
umbral. Es viejo (Page, 1954) y es el detector óptimo para un cambio de nivel
persistente, que es exactamente la forma de una ruptura de régimen: no un pico
aislado sino un desplazamiento que se queda.

Por qué el umbral NO se elige a mano
────────────────────────────────────
Aquí está el único punto que decide si esto vale algo. Un CUSUM con umbral
puesto a ojo hace una de dos cosas, y las dos son inútiles:

· **Umbral bajo**: salta cada pocas semanas sobre datos donde no ha pasado nada.
  Un detector que avisa siempre no informa nunca, y en un sistema que corta
  posiciones al avisar, destruye capital en comisiones.
· **Umbral alto**: no salta nunca, y el motor sigue operando una relación
  muerta.

La literatura da aproximaciones analíticas para el umbral (Siegmund), pero todas
suponen observaciones **independientes y gaussianas**. Una correlación móvil no
es ni lo uno ni lo otro: ventanas consecutivas comparten casi todos sus datos,
así que la serie está autocorrelacionada por construcción. Usar la fórmula sobre
ella daría un umbral demasiado bajo y un detector que salta por diseño.

Así que el umbral se **calibra contra el nulo de la propia serie**: se generan
réplicas bajo «nada ha cambiado», se recalcula el estadístico sobre cada una y se
toma el estadístico de orden ⌈(R+1)(1−α)⌉ del MÁXIMO por réplica. El umbral que
sale tiene una lectura directa y comprobable: *bajo la hipótesis de que nada ha
cambiado, la probabilidad de al menos una alarma en una ventana de esta longitud
es α.*

Cómo se genera esa réplica depende de lo que se vigile, y no es un detalle:

· **`detect_break`**, para una serie escalar cualquiera, remuestrea por bloques el
  tramo de referencia. Preserva la dependencia de corto alcance y la distribución
  marginal.
· **`correlation_break`** no puede hacer eso. Remuestrear las dos patas rompía la
  correlación por las costuras de los bloques y devolvía una cola demasiado
  corta —umbral bajo, falsa alarma por encima de la prometida, que es el lado
  peligroso—. Su nulo conserva la pata A **real y completa**, impone la
  correlación del tramo de referencia por construcción y remuestrea solo el
  residuo. Así reproduce el camino de volatilidad que gobierna el ruido del
  estimador de correlación. Está en `constant_correlation_null`.

En los dos casos la réplica imita el procedimiento COMPLETO, incluida la
estimación de la media y la sigma de referencia sobre el tramo de referencia de
cada réplica. Si se calibrara con la media verdadera, el umbral ignoraría el error
de esa estimación y volvería a quedarse corto.

Cuatro cosas que este módulo declara en vez de esconder
──────────────────────────────────────────────────────
1. **La alarma no fecha la ruptura, y el punto de cambio que se informa tampoco
   es una cota.** Es el último reinicio del CUSUM —el estimador que acompaña al
   contraste— y medido contra rupturas plantadas se sitúa unas barras DESPUÉS del
   suceso. Una versión anterior devolvía una cota inferior calculada restando la
   ventana a la alarma; comprobada, acertaba 0 de 10. Vale más un estimador que
   se puede medir que una cota que suena prudente y no lo es.
2. **El retardo es el precio del control de falsas alarmas.** No hay detector que
   avise antes y se equivoque menos; solo se puede elegir dónde ponerse. El
   mando es `detect_drop`: la caída de correlación que se quiere cazar pronto, en
   unidades de correlación. De ahí sale la holgura del CUSUM, que NO es una
   constante — poner media sigma «porque parece razonable» hacía que una ruptura
   de 0,80 a 0,30 se perdiera 52 veces de cada 60.
3. **Un tramo de referencia corto invalida el resultado, no lo debilita.** Y se
   cuenta en ventanas INDEPENDIENTES: 68 correlaciones de ventana 30 son 2,3
   ventanas, el mismo dato contado treinta veces. Por debajo de
   `MIN_REFERENCE_WINDOWS` no se emite veredicto.
4. **El control de la falsa alarma es aproximado**, y `self_note` dice cuánto:
   ~7 % medido contra un 5 % nominal. El exceso no baja subiendo las réplicas —se
   comprobó a 200, 400, 1.000 y 2.000—, así que viene del nulo remuestreado y no
   del ruido de Monte Carlo.

Los retornos entran desvolatilizados
────────────────────────────────────
Antes de correlacionar, cada pata se divide por su propia volatilidad local
estimada con el pasado. Sin ese paso la falsa alarma medida sobre retornos con
volatilidad agrupada —o sea, sobre cripto— era del 12,3 % contra un 5 %
prometido: las ventanas convulsas estiman la correlación con más ruido, así que
un tramo tranquilo fijaba una sigma pequeña y cualquier racha posterior movía el
estadístico sin que la correlación hubiera cambiado. El detector avisaba de
tormentas. Y la corrección no cuesta potencia: la gana, porque es el estimador
más eficiente bajo heterocedasticidad.

La correlación entra transformada
─────────────────────────────────
Un coeficiente de correlación vive en [−1, 1] y su varianza depende de su propio
valor: pasar de 0.90 a 0.80 es un cambio mucho mayor, en unidades de error
típico, que pasar de 0.10 a 0.00. Un CUSUM sobre r crudo trataría los dos igual y
sería ciego justo donde importa, porque las correlaciones que rompen una cartera
son las altas. Con la transformada de Fisher, z = arctanh(r), la varianza pasa a
ser aproximadamente constante y el detector mide desplazamientos comparables en
todo el rango.

Capa de dominio: NumPy puro, sin acceso a datos ni a red.
"""

from __future__ import annotations

import numpy as np

# Desplazamiento que se quiere detectar pronto, en sigmas del tramo tranquilo.
# 1.0 es el ajuste estándar del CUSUM: k = δ/2 minimiza el retardo para ese
# tamaño de cambio. Cambios mayores se detectan igual y antes; más pequeños
# tardan más, que es la única forma honesta de que esto funcione.
DEFAULT_SHIFT_SIGMA = 1.0

# Caída de correlación que se quiere cazar pronto, en unidades de correlación.
# 0.30 no es un número redondo elegido por comodidad: por debajo de ~0.15 el
# retardo medido se va a varios cientos de barras y el aviso llega cuando la
# pérdida ya está tomada; por encima de ~0.50 el detector solo ve catástrofes.
DEFAULT_DETECT_DROP = 0.30

# Semivida de la EWMA con la que se estima la volatilidad local, en barras, y
# observaciones que se descartan mientras la estimación se ceba.
EWMA_HALFLIFE = 30.0
DEVOL_WARMUP = 100

# Falsa alarma FAMILIAR: probabilidad de al menos una alarma en toda la ventana
# vigilada bajo el nulo. No es una tasa por observación.
DEFAULT_ALPHA = 0.05

# Réplicas del nulo. 400 y no más, y eso está medido: la tasa de falsa alarma se
# queda plana al subirlas —6,0 % a 200, 6,0 % a 400, 6,5 % a 1.000 y 7,0 % a
# 2.000 sobre el mismo nulo—, así que el exceso sobre el 5 % nominal no viene del
# ruido de Monte Carlo del cuantil sino del propio nulo remuestreado. Subirlas
# cuesta tiempo lineal y no compra exactitud.
DEFAULT_REPLICATES = 400

# Longitud media de bloque del remuestreo estacionario de retornos. Corta a
# propósito: los retornos son casi independientes y lo único que hay que
# preservar es el agrupamiento de volatilidad.
DEFAULT_BLOCK_MEAN = 5.0

# Mínimos para emitir veredicto. El de referencia domina: es de donde salen la
# media, la sigma y el nulo entero.
MIN_REFERENCE = 60
MIN_MONITOR = 20

# …y el mínimo que de verdad manda cuando la serie vigilada viene de ventanas
# solapadas. Contar 68 correlaciones de ventana 30 como 68 observaciones es
# contarse 30 veces el mismo dato: son 2,3 ventanas INDEPENDIENTES, y la sigma de
# referencia que sale de ahí no vale nada. Con 12, el error relativo de esa sigma
# ronda el 20 %: justo, pero utilizable, y declarado.
MIN_REFERENCE_WINDOWS = 12

# Ventana por defecto de la correlación móvil y mínimo admisible.
DEFAULT_CORR_WINDOW = 30
MIN_CORR_WINDOW = 12

# Tope de |r| antes de la transformada. arctanh(1) es infinito y una correlación
# de exactamente 1 aparece en cuanto dos series son la misma o la ventana es
# degenerada; recortar evita que un inf se propague a todo el estadístico.
MAX_ABS_R = 0.9999


# ---------------------------------------------------------------- transformada


def fisher_z(r) -> np.ndarray:
    """Transformada de Fisher, con los extremos recortados.

    Estabiliza la varianza: el error típico de z es ~1/√(n−3) con independencia
    del valor de r, mientras que el de r se encoge cerca de ±1.
    """
    x = np.clip(np.asarray(r, dtype=float), -MAX_ABS_R, MAX_ABS_R)
    return np.arctanh(x)


def fisher_z_se(n: int) -> float:
    """Error típico de la z de Fisher para una muestra de tamaño `n`."""
    return float("inf") if n <= 3 else 1.0 / np.sqrt(n - 3)


def devolatilize(x, halflife: float = EWMA_HALFLIFE,
                 warmup: int = DEVOL_WARMUP) -> np.ndarray:
    """Retornos divididos por su volatilidad local, estimada solo con el pasado.

    Sin este paso el detector no cumple lo que promete, y se midió: con
    volatilidad agrupada en los retornos, la tasa de falsa alarma se iba al 20 %
    contra un 5 % prometido. El motivo no es sutil. La correlación de una ventana
    se estima con más ruido cuando la ventana es convulsa, así que un tramo de
    referencia tranquilo fija una sigma pequeña y cualquier racha de volatilidad
    posterior mueve el estadístico sin que la correlación haya cambiado. El
    detector avisaba de tormentas, no de rupturas.

    Dividir cada pata por su propia volatilidad local deja las dos series
    homocedásticas y el estimador de correlación con ruido estable en el tiempo.
    Es además el estimador MÁS eficiente bajo heterocedasticidad —el mismo primer
    paso en dos etapas de los modelos de correlación condicional dinámica—, así
    que no se paga potencia por la corrección: se gana.

    La EWMA usa `x[t-1]` y anteriores, nunca `x[t]`. Si usara el retorno del
    propio instante, una barra grande se dividiría por su propia magnitud y el
    detector se volvería ciego justo en las barras que importan. Las primeras
    `warmup` observaciones se descartan porque su varianza sembrada mira datos
    que en ese instante no existían; el llamador recibe cuántas se fueron para
    poder volver a fechar los índices.
    """
    v = np.asarray(x, dtype=float)
    w = int(warmup)
    if v.size <= w + 1:
        return np.array([], dtype=float)

    lam = 0.5 ** (1.0 / max(float(halflife), 1.0))
    var = float(np.var(v[:w]))
    if not np.isfinite(var) or var <= 0:
        return np.array([], dtype=float)

    salida = np.empty(v.size - w, dtype=float)
    for t in range(w, v.size):
        var = lam * var + (1.0 - lam) * v[t - 1] ** 2
        salida[t - w] = v[t] / np.sqrt(var) if var > 0 else 0.0
    return salida


def _rolling_sum(v: np.ndarray, w: int) -> np.ndarray:
    """Sumas de ventana móvil por suma acumulada: O(n) en vez de O(n·w)."""
    c = np.concatenate(([0.0], np.cumsum(v)))
    return c[w:] - c[:-w]


def rolling_correlation(a, b, window: int = DEFAULT_CORR_WINDOW) -> np.ndarray:
    """Correlación de Pearson en ventana móvil, alineada al final de la ventana.

    Devuelve un vector de longitud `n − window + 1`: el elemento i resume las
    observaciones [i, i+window). Alineado al final porque es lo que se puede
    saber en ese instante sin mirar al futuro.

    Calculada con sumas acumuladas y no con una ventana por iteración. No es un
    adorno: la calibración del umbral recalcula esta serie cientos de veces, y con
    el bucle en Python el detector costaba minutos por par en vez de segundos.
    La contrapartida es la fórmula «de un paso» (E[xy]−E[x]E[y]), que pierde
    precisión cuando la media al cuadrado domina la varianza. Sobre retornos —de
    media casi nula— no se da ese caso; las varianzas se recortan a cero de todas
    formas para que un residuo negativo por redondeo no produzca un NaN.
    """
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    w = int(window)
    if x.size != y.size:
        raise ValueError("las dos series tienen que tener la misma longitud")
    if w < MIN_CORR_WINDOW or x.size < w:
        return np.array([], dtype=float)

    sx = _rolling_sum(x, w) / w
    sy = _rolling_sum(y, w) / w
    cov = _rolling_sum(x * y, w) / w - sx * sy
    vx = np.maximum(_rolling_sum(x * x, w) / w - sx * sx, 0.0)
    vy = np.maximum(_rolling_sum(y * y, w) / w - sy * sy, 0.0)

    denom = np.sqrt(vx * vy)
    salida = np.zeros(cov.size, dtype=float)   # pata plana: no correlaciona
    vivo = denom > 0
    salida[vivo] = cov[vivo] / denom[vivo]
    return np.clip(salida, -1.0, 1.0)


# ---------------------------------------------------------------------- núcleo


def cusum_path(values, mu0: float, sigma0: float, k: float) -> dict:
    """Camino del CUSUM de dos colas sobre `values`.

    S⁺ acumula desviaciones por arriba y S⁻ por abajo, cada una con una holgura
    `k` que las devuelve a cero mientras no pase nada. El estadístico vigilado es
    el máximo de las dos: se avisa igual de una ruptura al alza que a la baja,
    porque una correlación que se dispara rompe la diversificación tanto como una
    que se hunde.
    """
    x = np.asarray(values, dtype=float)
    if x.size == 0:
        return {"pos": np.array([]), "neg": np.array([]), "stat": np.array([])}
    if not np.isfinite(sigma0) or sigma0 <= 0:
        raise ValueError("sigma0 tiene que ser finita y positiva")

    u = (x - float(mu0)) / float(sigma0)
    pos = np.zeros(x.size, dtype=float)
    neg = np.zeros(x.size, dtype=float)
    sp = sn = 0.0
    for t in range(x.size):
        sp = max(0.0, sp + u[t] - k)
        sn = max(0.0, sn - u[t] - k)
        pos[t] = sp
        neg[t] = sn
    return {"pos": pos, "neg": neg, "stat": np.maximum(pos, neg)}


def slack_for_drop(rho_reference: float, drop: float, sigma0_z: float) -> dict:
    """Holgura `k` derivada de la caída de correlación que se quiere cazar.

    Aquí está el parámetro que decide si el detector sirve, y el que más fácil es
    equivocar. El CUSUM tiene su retardo mínimo cuando `k` es la MITAD del
    desplazamiento objetivo medido en sigmas del tramo tranquilo. Poner `k = 0.5`
    porque «media sigma parece razonable» es lo que mató la primera versión de
    esto: sobre el producto cruzado por barra, pasar de 0.80 a 0.30 —una ruptura
    brutal— es un desplazamiento de solo 0.42 sigmas, así que una holgura de 0.5
    se lo comía entero y el estadístico bajaba en vez de subir. Detectaba 8 de 60
    rupturas evidentes.

    Así que no se pide una sigma: se pide una CAÍDA DE CORRELACIÓN, que es lo que
    el que decide sabe expresar, y la sigma se mira en el dato.
    """
    r0 = float(np.clip(rho_reference, -MAX_ABS_R, MAX_ABS_R))
    r1 = float(np.clip(r0 - abs(float(drop)), -MAX_ABS_R, MAX_ABS_R))
    salto_z = abs(np.arctanh(r0) - np.arctanh(r1))
    s = float(sigma0_z)
    if not np.isfinite(s) or s <= 0 or salto_z <= 0:
        return {"k": DEFAULT_SHIFT_SIGMA / 2.0, "shift_sigma": DEFAULT_SHIFT_SIGMA,
                "shift_z": salto_z, "derived": False}
    desplazamiento = salto_z / s
    return {"k": desplazamiento / 2.0, "shift_sigma": desplazamiento,
            "shift_z": salto_z, "derived": True}


def scan(series, n_reference: int, shift_sigma: float = DEFAULT_SHIFT_SIGMA,
         k: float | None = None) -> dict:
    """Estadístico CUSUM del tramo vigilado, con la referencia estimada aparte.

    La media y la sigma salen SOLO del tramo de referencia. Estimarlas sobre la
    serie completa sería el error que mata al detector: una ruptura grande infla
    la sigma, el desplazamiento cabe dentro de la nueva desviación típica y el
    CUSUM no se mueve. El detector se quedaría ciego justo en el caso que
    justifica su existencia.
    """
    x = np.asarray(series, dtype=float)
    r = int(n_reference)
    if r <= 1 or r >= x.size:
        raise ValueError("el tramo de referencia tiene que dejar algo que vigilar")

    ref = x[:r]
    mon = x[r:]
    mu0 = float(ref.mean())
    sigma0 = float(ref.std(ddof=1))
    if not np.isfinite(sigma0) or sigma0 <= 0:
        return {"degenerate": True, "mu0": mu0, "sigma0": sigma0,
                "stat": np.array([]), "peak": 0.0,
                "note": ("El tramo de referencia no tiene variación: no hay escala "
                         "con la que medir un desplazamiento.")}

    kk = float(k) if k is not None else float(shift_sigma) / 2.0
    camino = cusum_path(mon, mu0, sigma0, kk)
    return {"degenerate": False, "mu0": mu0, "sigma0": sigma0, "k": kk,
            "stat": camino["stat"], "pos": camino["pos"], "neg": camino["neg"],
            "peak": float(camino["stat"].max()) if camino["stat"].size else 0.0}


# ------------------------------------------------------------------ remuestreo


def stationary_indices(n_source: int, size: int, block_mean: float,
                       rng) -> np.ndarray:
    """Índices de un remuestreo estacionario (Politis y Romano).

    Bloques de longitud geométrica con media `block_mean` y envoltura circular.
    La longitud aleatoria es lo que hace la serie remuestreada estacionaria: con
    bloques de longitud fija, la dependencia depende de la posición dentro del
    bloque y el nulo queda sesgado.

    Construido sin bucle. Cada posición sortea si abre bloque nuevo; el índice de
    la apertura se propaga hacia delante con un máximo acumulado y el desfase
    dentro del bloque se suma aparte. Da lo mismo que la recursión y deja de ser
    el coste dominante de la calibración.
    """
    n = int(n_source)
    m = int(size)
    if n <= 0 or m <= 0:
        return np.array([], dtype=int)

    p = 1.0 / max(float(block_mean), 1.0)
    abre = rng.random(m) < p
    abre[0] = True                       # la primera posición siempre abre
    origen = rng.integers(n, size=m)     # de dónde arranca cada bloque
    t = np.arange(m)
    apertura = np.maximum.accumulate(np.where(abre, t, 0))
    return (origen[apertura] + (t - apertura)) % n


def calibrate_threshold(replicates, alpha: float = DEFAULT_ALPHA) -> dict:
    """Umbral como cuantil 1−α del máximo por réplica.

    `replicates` es un iterable de picos: un número por réplica del nulo, el
    máximo que alcanzó el estadístico en toda la ventana vigilada. Tomar el
    máximo y no el valor puntual es lo que convierte el umbral en un control
    FAMILIAR: se paga por mirar la ventana entera, no por mirar una observación.
    """
    picos = np.asarray([p for p in replicates if np.isfinite(p)], dtype=float)
    if picos.size < 20:
        return {"threshold": None, "replicates": int(picos.size),
                "note": ("Menos de 20 réplicas utilizables: el cuantil sería más "
                         "ruidoso que el estadístico que tiene que juzgar.")}
    a = min(max(float(alpha), 1e-4), 0.5)
    # Estadístico de orden ⌈(R+1)(1−α)⌉ y no el cuantil interpolado. Con un número
    # finito de réplicas el cuantil interpolado se queda por debajo del que
    # controla la tasa, y el error va en la dirección mala: umbral bajo, falsas
    # alarmas por encima de lo prometido. Es la misma corrección de muestra finita
    # que usa la predicción conforme de este mismo motor.
    orden = int(np.ceil((picos.size + 1) * (1.0 - a)))
    orden = min(max(orden, 1), picos.size)
    h = float(np.sort(picos)[orden - 1])
    return {"threshold": h,
            "alpha": a,
            "replicates": int(picos.size),
            "order_statistic": orden,
            "null_median_peak": float(np.median(picos)),
            "note": (f"Bajo el nulo, la probabilidad de al menos una alarma en "
                     f"toda la ventana vigilada es aproximadamente {a:.0%}: es el "
                     f"estadístico de orden {orden} de {picos.size} réplicas, así "
                     f"que hereda el ruido de esas réplicas.")}


# ------------------------------------------------------------------- veredicto


def _change_point(resultado: dict, alarma: int) -> tuple[int, str]:
    """Último reinicio a cero del brazo que disparó, antes de la alarma.

    Es el estimador de punto de cambio que acompaña al CUSUM, y no una heurística:
    el brazo vale cero mientras la evidencia acumulada no apunta en su dirección,
    así que el instante en que dejó de valer cero por última vez es el momento a
    partir del cual TODA la evidencia empuja hacia el mismo lado — que es la
    definición del punto de cambio por máxima verosimilitud para un
    desplazamiento de nivel.

    La versión anterior de esto restaba la ventana a la alarma y llamaba «cota» al
    resultado. Se comprobó contra rupturas plantadas y acertaba 0 de 10: la cota
    era falsa. Se prefiere un estimador que se puede medir a una cota que suena
    prudente y no lo es.
    """
    pos = resultado.get("pos", np.array([]))
    neg = resultado.get("neg", np.array([]))
    if pos.size == 0 or alarma >= pos.size:
        return alarma, "arriba"
    brazo, sentido = ((pos, "arriba") if pos[alarma] >= neg[alarma]
                      else (neg, "abajo"))
    ceros = np.flatnonzero(brazo[:alarma + 1] <= 0.0)
    return (int(ceros[-1]) if ceros.size else 0), sentido


def _verdict(resultado: dict, umbral: dict, window_lag: int = 0) -> dict:
    """Primera superación del umbral, con lo que se puede y no se puede afirmar."""
    h = umbral.get("threshold")
    stat = resultado.get("stat", np.array([]))
    if h is None or stat.size == 0:
        return {"verdict": "SIN_DATOS", "broken": False, "threshold": h,
                "note": umbral.get("note") or resultado.get("note") or
                        "No hay tramo vigilado."}

    supera = np.flatnonzero(stat > h)
    if supera.size == 0:
        return {"verdict": "ESTABLE", "broken": False, "threshold": h,
                "peak": float(stat.max()),
                "headroom": float(h - stat.max()),
                "note": (f"El estadístico llegó a {stat.max():.2f} y el umbral está "
                         f"en {h:.2f}. No es prueba de que la relación aguante: es "
                         f"que no hay evidencia de que haya dejado de aguantar.")}

    i = int(supera[0])
    cambio, sentido = _change_point(resultado, i)
    w = max(int(window_lag), 1)
    return {
        "verdict": "ROTO",
        "broken": True,
        "threshold": h,
        "peak": float(stat.max()),
        "alarm_index": i,
        "direction": sentido,
        # Índices en la serie VIGILADA. El de la correlación `j` resume los
        # retornos [j, j+w), así que la ventana que disparó acaba en el retorno
        # `alarm_index + reference + w − 1`: la alarma no es la fecha del suceso y
        # el que la lea necesita las dos cosas para fecharla.
        "change_point_index": cambio,
        "detection_delay": i - cambio,
        "window_lag": int(window_lag),
        "note": (f"Primera superación en la observación {i} del tramo vigilado, con "
                 f"el brazo de {sentido}. El punto de cambio estimado —último "
                 f"reinicio del CUSUM— está en {cambio}, o sea {i - cambio} barras "
                 f"antes de la alarma. Cada observación resume una ventana de {w} "
                 f"barras, que hay que sumar para fechar el suceso en el mercado."),
    }


def detect_break(series, reference: int | None = None,
                 shift_sigma: float = DEFAULT_SHIFT_SIGMA,
                 alpha: float = DEFAULT_ALPHA,
                 replicates: int = DEFAULT_REPLICATES,
                 block_mean: float = DEFAULT_BLOCK_MEAN,
                 window_lag: int = 0,
                 seed: int = 7) -> dict:
    """CUSUM sobre una serie cualquiera, con el umbral calibrado sobre su nulo.

    El nulo remuestrea por bloques el TRAMO DE REFERENCIA, no la serie completa:
    si entrara el tramo vigilado, la ruptura que se busca estaría dentro del nulo
    contra el que se compara y el umbral subiría hasta taparla.
    """
    x = np.asarray(series, dtype=float)
    x = x[np.isfinite(x)]
    r = int(reference) if reference else int(x.size * 0.4)
    if x.size < MIN_REFERENCE + MIN_MONITOR or r < MIN_REFERENCE or x.size - r < MIN_MONITOR:
        return {"verdict": "SIN_DATOS", "broken": False, "n": int(x.size),
                "reference": r,
                "note": (f"Hacen falta al menos {MIN_REFERENCE} observaciones de "
                         f"referencia y {MIN_MONITOR} vigiladas; hay {r} y "
                         f"{max(x.size - r, 0)}.")}

    resultado = scan(x, r, shift_sigma)
    if resultado.get("degenerate"):
        return {"verdict": "SIN_DATOS", "broken": False, **resultado}

    rng = np.random.default_rng(seed)
    ref = x[:r]
    picos = []
    for _ in range(int(replicates)):
        idx = stationary_indices(ref.size, x.size, block_mean, rng)
        replica = ref[idx]
        try:
            picos.append(scan(replica, r, shift_sigma)["peak"])
        except ValueError:
            continue

    umbral = calibrate_threshold(picos, alpha)
    salida = {"n": int(x.size), "reference": r, "monitored": int(x.size - r),
              "shift_sigma": float(shift_sigma), "mu0": resultado["mu0"],
              "sigma0": resultado["sigma0"], "calibration": umbral}
    salida.update(_verdict(resultado, umbral, window_lag))
    return salida


def constant_correlation_null(a, b, n_reference: int, rng,
                              block_mean: float = DEFAULT_BLOCK_MEAN) -> np.ndarray:
    """Una réplica de la pata B bajo «la correlación no ha cambiado».

    Construcción, y el motivo de cada pieza:

        b̃ = ρ₀·â  +  √(1−ρ₀²)·ẽ

    donde `â` es la pata A **real y completa** —no remuestreada— y `ẽ` es un
    remuestreo por bloques del residuo del tramo de referencia.

    · **La pata A entra tal cual.** Es lo que hace que este nulo valga. El ruido
      del estimador de correlación depende del camino de volatilidad: ventanas
      tranquilas dan correlaciones estables y ventanas convulsas dan
      correlaciones que bailan. Conservando la pata A real, el nulo reproduce ese
      camino exactamente, incluida la dependencia que introduce el solape de
      ventanas. Un remuestreo de las DOS patas lo rompía por las costuras y
      devolvía una cola demasiado corta: el umbral salía bajo y la falsa alarma
      real quedaba por encima de la prometida, que es el lado peligroso.
    · **ρ₀ es la correlación del tramo de referencia**, impuesta por
      construcción sobre toda la longitud. Eso es la hipótesis nula, no una
      aproximación a ella.
    · **El residuo se remuestrea por bloques y no se sortea gaussiano.** Las
      colas del residuo son las que producen los picos del estadístico; ponerlas
      normales adelgazaría el nulo justo donde se lee el cuantil.

    Que la pata A del tramo vigilado entre en el nulo no es una fuga: la
    hipótesis versa sobre la RELACIÓN, así que condicionar en el camino realizado
    de A hace la prueba condicional, y más exigente.
    """
    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    r = int(n_reference)

    ma, sa = x[:r].mean(), x[:r].std(ddof=1)
    mb, sb_ = y[:r].mean(), y[:r].std(ddof=1)
    if sa <= 0 or sb_ <= 0:
        return y.copy()

    xa = (x - ma) / sa                      # pata A entera, estandarizada
    yb = (y[:r] - mb) / sb_                 # pata B solo en la referencia
    rho = float(np.clip(np.corrcoef(xa[:r], yb)[0, 1], -MAX_ABS_R, MAX_ABS_R))

    resid = yb - rho * xa[:r]
    sr = resid.std(ddof=1)
    resid = resid / sr if sr > 0 else resid

    idx = stationary_indices(r, x.size, block_mean, rng)
    e = resid[idx]
    return mb + sb_ * (rho * xa + np.sqrt(max(1.0 - rho ** 2, 0.0)) * e)


def correlation_break(a, b, window: int = DEFAULT_CORR_WINDOW,
                      reference: int | None = None,
                      detect_drop: float = DEFAULT_DETECT_DROP,
                      alpha: float = DEFAULT_ALPHA,
                      replicates: int = DEFAULT_REPLICATES,
                      block_mean: float = DEFAULT_BLOCK_MEAN,
                      devol: bool = True,
                      seed: int = 7) -> dict:
    """¿Ha cambiado la correlación entre dos activos, o es el ruido de la ventana?

    `detect_drop` es el único mando: el tamaño de la caída de correlación que se
    quiere cazar pronto, en unidades de correlación. De ahí sale la holgura del
    CUSUM. Caídas mayores se detectan antes; menores, más tarde. No hay un ajuste
    que las cace todas rápido y esa es una propiedad del problema, no del código.

    `devol` divide cada pata por su volatilidad local antes de correlacionar. Está
    activo por defecto porque sin él la falsa alarma medida sobre retornos con
    volatilidad agrupada —o sea, sobre cripto— se va muy por encima de la
    prometida. Se deja desactivable solo para poder volver a medir esa diferencia.
    """
    x0 = np.asarray(a, dtype=float)
    y0 = np.asarray(b, dtype=float)
    if x0.size != y0.size:
        return {"verdict": "SIN_DATOS", "broken": False,
                "note": "Las dos series tienen que tener la misma longitud."}
    w = max(int(window), MIN_CORR_WINDOW)

    if devol:
        x = devolatilize(x0)
        y = devolatilize(y0)
        descartados = x0.size - x.size
    else:
        x, y = x0, y0
        descartados = 0
    if x.size == 0 or y.size == 0:
        return {"verdict": "SIN_DATOS", "broken": False, "window": w,
                "note": (f"No queda serie tras el cebado de la volatilidad local: "
                         f"hacen falta más de {DEVOL_WARMUP} retornos.")}

    r_serie = rolling_correlation(x, y, w)
    z = fisher_z(r_serie)
    # El tramo de referencia se cuenta en observaciones de la serie de
    # correlación, no en retornos: es la serie que vigila el CUSUM.
    r = int(reference) if reference else int(z.size * 0.4)
    # El mínimo se cuenta en ventanas INDEPENDIENTES, no en observaciones: las
    # correlaciones consecutivas comparten casi todos sus datos.
    ref_minima = max(MIN_REFERENCE, MIN_REFERENCE_WINDOWS * w)
    if z.size < ref_minima + MIN_MONITOR or r < ref_minima or z.size - r < MIN_MONITOR:
        return {"verdict": "SIN_DATOS", "broken": False, "window": w,
                "n_correlations": int(z.size), "reference": r,
                "reference_required": int(ref_minima),
                "independent_windows": round(r / w, 1),
                "note": (f"Con ventana {w} hacen falta {ref_minima} correlaciones de "
                         f"referencia —{MIN_REFERENCE_WINDOWS} ventanas "
                         f"independientes— y {MIN_MONITOR} vigiladas; hay {r} y "
                         f"{max(z.size - r, 0)}. De {x.size} retornos utilizables "
                         f"salen {z.size} correlaciones: o la ventana es demasiado "
                         f"larga o el histórico demasiado corto.")}

    base = scan(z, r)
    if base.get("degenerate"):
        return {"verdict": "SIN_DATOS", "broken": False, "window": w, **base}

    holgura = slack_for_drop(float(np.tanh(base["mu0"])), detect_drop, base["sigma0"])
    resultado = scan(z, r, k=holgura["k"])

    # Retornos que producen el tramo de referencia de la correlación: la ventana
    # `r-1` acaba en el retorno `r + w - 2`.
    n_ret_ref = r + w - 1
    rng = np.random.default_rng(seed)
    picos = []
    for _ in range(int(replicates)):
        yb = constant_correlation_null(x, y, n_ret_ref, rng, block_mean)
        zr = fisher_z(rolling_correlation(x, yb, w))
        if zr.size <= r:
            continue
        try:
            picos.append(scan(zr, r, k=holgura["k"])["peak"])
        except ValueError:
            continue

    umbral = calibrate_threshold(picos, alpha)
    salida = {
        "window": w,
        "n_correlations": int(z.size),
        "reference": r,
        "monitored": int(z.size - r),
        "devolatilized": bool(devol),
        # Lo que de verdad sostiene la sigma de referencia. Si está cerca del
        # mínimo, el umbral hereda el ruido de esa estimación.
        "independent_windows": round(r / w, 1),
        # Retornos consumidos por el cebado de la volatilidad local. Sin este
        # número, los índices que devuelve el detector no se pueden volver a
        # fechar contra las velas de entrada.
        "warmup_returns_dropped": int(descartados),
        "detect_drop": float(detect_drop),
        "slack": holgura,
        "reference_corr": float(np.tanh(resultado["mu0"])),
        "recent_corr": float(r_serie[-1]) if r_serie.size else None,
        "mu0_z": resultado["mu0"],
        "sigma0_z": resultado["sigma0"],
        "sigma0_z_expected": fisher_z_se(w),
        "calibration": umbral,
        "protocol": (
            "CUSUM de dos colas sobre la z de Fisher de la correlación móvil, con "
            "la holgura derivada de la caída objetivo y no elegida. El umbral "
            "tampoco se elige: es el cuantil 1−α del máximo del estadístico bajo "
            "un nulo de correlación CONSTANTE que conserva el camino real de "
            "volatilidad de la primera pata, así que controla la falsa alarma en "
            "la ventana completa y no por observación."),
    }
    salida.update(_verdict(resultado, umbral, window_lag=w))
    return salida


# ------------------------------------------------------------------------ nota


def self_note() -> str:
    """Lo que este detector no puede hacer, dicho antes de que se le pida.

    Las cifras que aparecen aquí están medidas sobre series sintéticas con la
    respuesta conocida, no estimadas de memoria. El guion de laboratorio que las
    produce vive fuera del repositorio; lo que queda dentro son los tests que
    fijan el orden de magnitud de cada una.
    """
    return (
        "Lo medido, sobre series sintéticas con la respuesta conocida: con la "
        "correlación CONSTANTE el detector avisa alrededor del 7 % de las veces "
        "—6,7 % sobre retornos homocedásticos, 6–8 % con volatilidad agrupada, que "
        "es el caso realista— contra un 5 % nominal. Sin desvolatilizar era del "
        "12,3 %. Así que el control de falsa alarma es APROXIMADO y se queda del "
        "lado generoso; quien necesite un 5 % efectivo tiene que pedir α≈0,035.\n"
        "Y ese exceso NO se arregla con más réplicas: medido a 200, 400, 1.000 y "
        "2.000 réplicas la tasa se queda plana (6,0 %, 6,0 %, 6,5 %, 7,0 %), así "
        "que no viene del ruido de Monte Carlo del cuantil sino del nulo "
        "remuestreado, "
        "que se queda algo corto de cola. Subir las réplicas cuesta tiempo y no "
        "compra exactitud.\n"
        "Una caída de correlación de 0,80 a 0,30 se detecta en unas 33 barras y "
        "una de 0,80 a 0,65 en unas 121, con el 90 % de detección. Ningún umbral "
        "fijo consigue las dos cosas: sobre los mismos datos, uno de 5 daba el "
        "96 % de falsas alarmas y uno de 50 dejaba escapar rupturas reales.\n"
        "El CUSUM detecta un DESPLAZAMIENTO DE NIVEL persistente. No detecta un "
        "cambio de varianza con la misma media, ni una relación que se vuelve no "
        "lineal conservando su correlación, ni un cambio que dura menos que el "
        "retardo de detección: para ese último, el estadístico sube, la holgura k "
        "lo devuelve a cero y no queda rastro. Es una elección, no una carencia — "
        "un detector sensible a picos aislados avisaría de cada noticia.\n"
        "El umbral calibrado controla la falsa alarma bajo un nulo de nivel "
        "CONSTANTE. Si la correlación de referencia ya derivaba despacio, esa "
        "deriva está dentro del tramo de referencia, infla la sigma y el detector "
        "pierde potencia. Se ve en `sigma0_z`: una sigma muy por encima de "
        "1/√(ventana−3) dice que el tramo tranquilo no estaba tranquilo.\n"
        "Y la alarma no fecha la ruptura. El punto de cambio que se informa es el "
        "último reinicio del CUSUM, que es un ESTIMADOR y no una cota: medido "
        "contra rupturas plantadas se sitúa unas cinco barras DESPUÉS del suceso "
        "para una caída grande y unas treinta para una pequeña. Leerlo como «la "
        "ruptura no fue antes de esta fecha» es exactamente lo contrario de lo "
        "que dice."
    )
