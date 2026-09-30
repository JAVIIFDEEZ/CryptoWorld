"""
event_study.py — ¿Mueve el precio un evento programado, o es que se mira mucho?

El problema, y por qué casi todos los estudios de eventos están mal
──────────────────────────────────────────────────────────────────
Coger las velas alrededor de doce nóminas no agrícolas, ver que el precio se movió
y concluir que la nómina mueve el precio es el error más común de este campo, y
tiene tres causas que se acumulan:

1. **El precio siempre se mueve.** Hace falta una referencia de cuánto se mueve
   en un rato cualquiera, no la impresión de que «se movió bastante».
2. **La referencia ingenua está contaminada por la estructura del calendario.**
   Las nóminas caen todas en viernes por la mañana. Si se comparan con instantes
   sorteados uniformemente, cualquier efecto de «viernes por la mañana» —que
   existe: se cierran posiciones antes del fin de semana— aparecerá como efecto
   del evento. El nulo tiene que conservar la hora y el día de la semana.
3. **La potencia es minúscula y nadie la reporta.** Con doce eventos al año, el
   efecto más pequeño detectable es enorme. Un estudio sobre 36 eventos que no
   encuentra nada no ha demostrado que no haya nada: ha demostrado que con 36
   eventos no se puede saber.

Este módulo responde a los tres: referencia por desplazamiento de semanas
enteras, potencia declarada en cada salida, y detección automática de cuándo ese
nulo es degenerado.

La pregunta correcta es la volatilidad, no la dirección
──────────────────────────────────────────────────────
El mismo hallazgo que gobierna `edge_test` vale aquí. El efecto de un evento sobre
el RETORNO es de signo impredecible —si fuera predecible, se descontaría antes— y
para detectarlo harían falta cientos de eventos. El efecto sobre la VOLATILIDAD es
de otro orden de magnitud y se detecta con decenas. Así que se miden las dos cosas
y se dice cuál de ellas la muestra puede responder, en vez de enseñar la que sale
más bonita.

Dos referencias, y cuándo cada una
──────────────────────────────────
· **`week`** (por defecto): cada evento se desplaza un número entero y no nulo de
  semanas. Conserva exactamente el día de la semana y la hora UTC, así que el
  nulo lleva dentro cualquier efecto de calendario y solo destruye la afirmación
  bajo prueba: que fue ESE día concreto.
· **`offset`**: todos los eventos se desplazan un número fijo de horas. Es la
  referencia para las familias densas y periódicas —las liquidaciones de
  financiación caen cada ocho horas, así que desplazarlas semanas enteras las
  deja encima de otra liquidación y el nulo contiene la señal—. Con un
  desplazamiento de cuatro horas, las 04:00/12:00/20:00 son un control con la
  misma estructura de tres al día y sin liquidación.

Y la degeneración no se supone: se mide. `null_overlap_pct` dice qué fracción de
los instantes de la referencia cayó pegada a un evento real, y por encima de
`MAX_NULL_OVERLAP` no se emite veredicto.

Capa de dominio: NumPy puro, sin acceso a datos ni a red.
"""

from __future__ import annotations

import numpy as np

# Ventana de reacción por defecto, en velas desde la que contiene el evento.
DEFAULT_POST = 6

# Velas previas que se inspeccionan para ver si el mercado se posiciona antes.
DEFAULT_PRE = 6

# Ventana de estimación: de dónde sale «lo normal» para este activo.
DEFAULT_ESTIMATION = 120

# Hueco entre la ventana de estimación y la de evento. No es cosmético: sin él,
# el posicionamiento previo al evento entra en la referencia, sube su volatilidad
# y el efecto del evento se mide contra una referencia ya contaminada.
DEFAULT_GAP = 12

# Réplicas de la referencia.
DEFAULT_REPLICATES = 400

# Eventos mínimos para emitir veredicto. Por debajo, el efecto más pequeño
# detectable es tan grande que el resultado no informa de nada.
MIN_EVENTS = 12

# Fracción máxima de instantes de la referencia que pueden caer pegados a un
# evento real antes de declarar el nulo degenerado.
MAX_NULL_OVERLAP = 0.20

SEMANA_MS = 7 * 24 * 3_600_000
HORA_MS = 3_600_000

# Potencia: 1,96 para el 5 % a dos colas más 0,84 para el 80 % de potencia.
_Z_MDE = 1.959964 + 0.841621


# ──────────────────────────────────────────────────────────── alineamiento


def align_events(timestamps, event_times) -> np.ndarray:
    """Índice de la vela que CONTIENE cada evento, o −1 si cae fuera.

    Contiene, no «la más cercana». Una nómina a las 12:30 cae dentro de la vela
    que abre a las 12:00, y el retorno de esa vela no se conoce hasta que cierra a
    las 13:00. Redondear al índice más próximo colocaría la mitad de los eventos
    en la vela ANTERIOR, cuyo retorno ya estaba cerrado antes del evento: sería
    lookahead puro y produciría una reacción que empieza antes de la causa.
    """
    t = np.asarray(timestamps, dtype=np.int64)
    e = np.asarray(event_times, dtype=np.int64)
    if t.size < 2 or e.size == 0:
        return np.full(e.size, -1, dtype=np.int64)

    # `searchsorted` con 'right' da el número de velas que abren en ≤ evento, así
    # que menos uno es el índice de la última que abrió antes o justo en él.
    idx = np.searchsorted(t, e, side="right") - 1
    paso = int(np.median(np.diff(t)))
    dentro = (idx >= 0) & (idx < t.size)
    # Y que el evento caiga de verdad dentro de esa vela y no en un hueco.
    valido = np.zeros(e.size, dtype=bool)
    valido[dentro] = (e[dentro] - t[idx[dentro]]) < paso
    return np.where(valido, idx, -1).astype(np.int64)


def bar_interval_ms(timestamps) -> int:
    """Duración de la vela, por la mediana de los huecos."""
    t = np.asarray(timestamps, dtype=np.int64)
    if t.size < 2:
        return HORA_MS
    huecos = np.diff(t)
    huecos = huecos[huecos > 0]
    return int(np.median(huecos)) if huecos.size else HORA_MS


# ───────────────────────────────────────────────────────── una ventana


def window_batch(returns, indices, pre: int = DEFAULT_PRE,
                 post: int = DEFAULT_POST,
                 estimation: int = DEFAULT_ESTIMATION,
                 gap: int = DEFAULT_GAP) -> dict:
    """Todas las ventanas de golpe, con indexación avanzada.

    No es una optimización cosmética. El nulo recalcula el agregado en cada
    réplica, así que una familia de 3.285 liquidaciones con 400 réplicas son 1,3
    millones de ventanas: con una llamada por evento el estudio costaba minutos y
    aquí cuesta segundos. Como el camino rápido es el único que se usa, la versión
    de un solo evento (`window_stats`) es un envoltorio de esta y no una segunda
    implementación que pudiera desviarse.

    Los eventos sin sitio —sin ventana de estimación completa por delante o sin
    ventana de reacción completa por detrás— se DESCARTAN, no se recortan.
    Recortarlos haría que los eventos de los extremos se midieran con menos datos
    y pesaran distinto en la media sin que nada lo dijera.
    """
    r = np.asarray(returns, dtype=float)
    idx = np.asarray(indices, dtype=np.int64).ravel()
    n = r.size
    g, est, po, pr = int(gap), int(estimation), int(post), int(pre)

    cabe = ((idx >= 0) & (idx - g - est >= 0) & (idx + po < n) & (idx - pr >= 0))
    ii = idx[cabe]
    if ii.size == 0 or est < 2:
        return {"index": np.array([], dtype=np.int64), "car": np.array([]),
                "vol_ratio": np.array([]), "pre_vol_ratio": np.array([]),
                "baseline_vol": np.array([]), "dropped": int(idx.size)}

    base = r[ii[:, None] + np.arange(-g - est, -g)]
    reaccion = r[ii[:, None] + np.arange(0, po + 1)]
    previa = (r[ii[:, None] + np.arange(-pr, 0)] if pr > 0
              else np.zeros((ii.size, 0)))

    mu = base.mean(axis=1)
    rv_base = np.sqrt((base ** 2).mean(axis=1))
    vivo = np.isfinite(rv_base) & (rv_base > 0)

    car = (reaccion - mu[:, None]).sum(axis=1)
    rv_evento = np.sqrt((reaccion ** 2).mean(axis=1))
    rv_previa = (np.sqrt((previa ** 2).mean(axis=1)) if pr > 0
                 else np.full(ii.size, np.nan))

    # Se divide solo donde la referencia es válida. Dividir el vector entero y
    # filtrar después daría el mismo resultado pero emitiendo avisos de división
    # por cero en cada llamada, y un aviso que siempre aparece deja de leerse.
    base_viva = rv_base[vivo]
    return {
        "index": ii[vivo],
        # Retorno anormal acumulado: lo que no explica el nivel medio.
        "car": car[vivo],
        # Razón de volatilidad: cuántas veces más se movió que en su referencia.
        "vol_ratio": rv_evento[vivo] / base_viva,
        "pre_vol_ratio": rv_previa[vivo] / base_viva,
        "baseline_vol": base_viva,
        "dropped": int(idx.size - int(vivo.sum())),
    }


def window_stats(returns, idx: int, pre: int = DEFAULT_PRE,
                 post: int = DEFAULT_POST,
                 estimation: int = DEFAULT_ESTIMATION,
                 gap: int = DEFAULT_GAP) -> dict | None:
    """Reacción de UN evento. Envoltorio de `window_batch`, nunca una copia."""
    lote = window_batch(returns, [idx], pre, post, estimation, gap)
    if lote["index"].size == 0:
        return None
    previa = float(lote["pre_vol_ratio"][0])
    return {
        "index": int(lote["index"][0]),
        "car": float(lote["car"][0]),
        "car_abs": float(abs(lote["car"][0])),
        "vol_ratio": float(lote["vol_ratio"][0]),
        "pre_vol_ratio": previa if np.isfinite(previa) else None,
        "baseline_vol": float(lote["baseline_vol"][0]),
    }


# ────────────────────────────────────────────────────────────── el nulo


def weekday_hour_key(times) -> np.ndarray:
    """Clave día-de-la-semana × hora UTC, vectorizada.

    El 1 de enero de 1970 fue jueves, que en el convenio de Python —lunes 0— es el
    3, así que el día de la semana es `(días + 3) % 7`.
    """
    t = np.asarray(times, dtype=np.int64)
    dias = t // 86_400_000
    dow = (dias + 3) % 7
    hora = (t // HORA_MS) % 24
    return (dow * 24 + hora).astype(np.int64)


def matched_pool(timestamps, event_times, tolerance_ms: int) -> np.ndarray:
    """Instantes con el MISMO día de la semana y hora que los eventos, sin evento.

    Es la referencia que hace identificable una familia mensual dentro de una
    rejilla semanal, y sin ella media biblioteca de este módulo no serviría. El
    vencimiento mensual cae el último viernes a las 08:00 UTC, pero TODOS los
    viernes hay vencimiento semanal a esa hora: desplazar semanas enteras aterriza
    sobre otro vencimiento y el nulo se come la señal. La pregunta bien planteada
    no es «¿se mueve el mercado los viernes a las ocho?» sino «¿se mueve MÁS el
    último viernes del mes que los demás viernes a la misma hora?», y eso se
    contesta con este conjunto.

    Lo mismo con la nómina no agrícola: el control son los otros viernes a las
    12:30 o 13:30 UTC, no un instante cualquiera.
    """
    t = np.asarray(timestamps, dtype=np.int64)
    e = np.asarray(event_times, dtype=np.int64)
    if t.size == 0 or e.size == 0:
        return np.array([], dtype=np.int64)

    claves = np.unique(weekday_hour_key(e))
    candidato = np.isin(weekday_hour_key(t), claves)
    if not candidato.any():
        return np.array([], dtype=np.int64)

    orden = np.sort(e)
    pos = np.searchsorted(orden, t)
    izq = orden[np.clip(pos - 1, 0, orden.size - 1)]
    der = orden[np.clip(pos, 0, orden.size - 1)]
    dist = np.minimum(np.abs(t - izq), np.abs(t - der))
    return t[candidato & (dist > int(tolerance_ms))]


def _distance_to_nearest(candidatos, event_times) -> np.ndarray:
    """Distancia de cada candidato al evento real más próximo."""
    c = np.asarray(candidatos, dtype=np.int64)
    e = np.sort(np.asarray(event_times, dtype=np.int64))
    if c.size == 0 or e.size == 0:
        return np.full(c.size, np.iinfo(np.int64).max, dtype=np.int64)
    pos = np.searchsorted(e, c)
    izq = e[np.clip(pos - 1, 0, e.size - 1)]
    der = e[np.clip(pos, 0, e.size - 1)]
    return np.minimum(np.abs(c - izq), np.abs(c - der))


def control_times(timestamps, event_times, mode: str = "matched",
                  tolerance_ms: int = 0, max_weeks: int = 26,
                  offset_hours: float = 4.0) -> np.ndarray:
    """Instantes de CONTROL: cuándo sería «un rato normal» para esta familia.

    Tres formas de construirlo y elegir mal invalida el estudio entero:

    · `matched` — instantes con la misma hora y el mismo día de la semana que los
      eventos, sin evento. El único válido cuando la familia vive dentro de una
      rejilla más densa a la misma hora: el vencimiento mensual entre los
      semanales, la nómina no agrícola entre los demás viernes.
    · `week` — los eventos desplazados un número entero de semanas, con lo que se
      conservan día de la semana y hora UTC. Válido para familias que NO son
      semanalmente periódicas; con una que sí lo sea, todos los candidatos caen
      sobre otro evento, el conjunto queda vacío y el estudio lo dice.
    · `offset` — los eventos desplazados unas horas fijas. Para familias densas y
      periódicas, como las liquidaciones de financiación.

    En los tres casos se descarta todo candidato cuya ventana de reacción pise un
    evento real, y ese filtro es el que hace emerger la no identificabilidad sin
    necesidad de una comprobación aparte: si no queda ningún control, es que el
    efecto del evento no se puede separar del efecto de su hora.
    """
    t = np.asarray(timestamps, dtype=np.int64)
    e = np.asarray(event_times, dtype=np.int64)
    if t.size == 0 or e.size == 0:
        return np.array([], dtype=np.int64)

    if mode == "matched":
        claves = np.unique(weekday_hour_key(e))
        cand = t[np.isin(weekday_hour_key(t), claves)]
    elif mode == "offset":
        cand = e + np.int64(round(float(offset_hours) * HORA_MS))
    else:
        desplazamientos = np.array([k for k in range(-int(max_weeks),
                                                     int(max_weeks) + 1) if k != 0],
                                   dtype=np.int64)
        cand = (e[:, None] + desplazamientos[None, :] * SEMANA_MS).ravel()

    cand = np.unique(cand)
    dentro = (cand >= t[0]) & (cand <= t[-1])
    lejos = _distance_to_nearest(cand, e) > int(tolerance_ms)
    return cand[dentro & lejos]


def matched_pool(timestamps, event_times, tolerance_ms: int) -> np.ndarray:
    """Alias histórico de `control_times` en modo emparejado."""
    return control_times(timestamps, event_times, "matched", tolerance_ms)


def permutation_p(observado: float, evento: np.ndarray, control: np.ndarray,
                  replicates: int, rng) -> float:
    """p-valor por PERMUTACIÓN de etiquetas entre eventos y controles.

    Aquí está la corrección que hizo falta medir para encontrar. La versión
    anterior remuestreaba el conjunto de control y comparaba la media de los
    eventos contra esa distribución. Parece correcto y no lo es: el nulo queda
    centrado en la media del CONTROL, no en la de la población, y esa media
    tiene su propio error de orden σ/√n_control. Con 36 eventos y 120 controles,
    el descentramiento es de media desviación típica del estadístico observado,
    en una dirección u otra según la muestra — y la tasa de falso positivo medida
    se fue al 17 % contra un 5 % prometido.

    La permutación no tiene ese problema porque no privilegia a ninguno de los
    dos grupos: junta las dos muestras, reparte al azar las etiquetas y mira
    cuántas veces el grupo «evento» sale tan extremo como el de verdad. Bajo la
    hipótesis de que eventos y controles vienen de la misma distribución —que es
    exactamente la hipótesis nula— está exactamente calibrada, no
    aproximadamente.
    """
    ev = np.asarray(evento, dtype=float)
    ct = np.asarray(control, dtype=float)
    if ev.size == 0 or ct.size == 0:
        return float("nan")
    juntos = np.concatenate([ev, ct])
    n = ev.size
    extremos = 0
    for _ in range(int(replicates)):
        muestra = rng.choice(juntos, size=n, replace=False)
        if float(muestra.mean()) >= observado:
            extremos += 1
    # Corrección de muestra finita: sin el +1, cero réplicas por encima daría
    # p = 0, y 400 réplicas no sostienen esa afirmación.
    return float((1 + extremos) / (int(replicates) + 1))


# ──────────────────────────────────────────────────────────── el estudio


def _aggregate(lote: dict) -> dict:
    """Agregado de un lote de ventanas. Es el agregado lo que se afirma."""
    if not lote or lote["index"].size == 0:
        return {"n": 0}
    car = np.asarray(lote["car"], dtype=float)
    vol = np.asarray(lote["vol_ratio"], dtype=float)
    previa = np.asarray(lote["pre_vol_ratio"], dtype=float)
    previa = previa[np.isfinite(previa)]
    return {
        "n": int(car.size),
        "car_mean": float(car.mean()),
        "car_sd": float(car.std(ddof=1)) if car.size > 1 else 0.0,
        "car_abs_mean": float(np.abs(car).mean()),
        "vol_ratio_mean": float(vol.mean()),
        "vol_ratio_median": float(np.median(vol)),
        "pre_vol_ratio_mean": float(previa.mean()) if previa.size else None,
    }


def minimum_detectable_car(car_sd: float, n: int) -> float:
    """Efecto más pequeño detectable sobre el retorno acumulado.

    Se publica siempre, y sobre todo cuando el estudio no encuentra nada: es la
    diferencia entre «este evento no mueve el precio» y «con estos eventos no se
    puede saber si lo mueve». La segunda es casi siempre la verdad y casi nunca
    se dice.
    """
    if n <= 1 or not np.isfinite(car_sd) or car_sd <= 0:
        return float("nan")
    return float(_Z_MDE * car_sd / np.sqrt(n))


def study(timestamps, returns, event_times, pre: int = DEFAULT_PRE,
          post: int = DEFAULT_POST, estimation: int = DEFAULT_ESTIMATION,
          gap: int = DEFAULT_GAP, replicates: int = DEFAULT_REPLICATES,
          null_mode: str = "matched", offset_hours: float = 4.0,
          seed: int = 11) -> dict:
    """¿Se mueve este activo alrededor de estos eventos más que en un rato normal?

    Devuelve las dos respuestas —volatilidad y dirección— con su contraste contra
    la referencia y con la potencia declarada, y se niega a emitir veredicto
    cuando la referencia es degenerada o los eventos son demasiado pocos.
    """
    t = np.asarray(timestamps, dtype=np.int64)
    r = np.asarray(returns, dtype=float)
    e = np.asarray(event_times, dtype=np.int64)
    if t.size != r.size:
        return {"verdict": "SIN_DATOS",
                "note": "Marcas temporales y retornos tienen que ir alineados."}

    paso = bar_interval_ms(t)
    idx = align_events(t, e)
    lote = window_batch(r, idx[idx >= 0], pre, post, estimation, gap)
    usables = int(lote["index"].size)

    salida = {
        "events_given": int(e.size),
        "events_aligned": int(np.sum(idx >= 0)),
        "events_usable": usables,
        "bar_interval_ms": paso,
        "pre": pre, "post": post, "estimation": estimation, "gap": gap,
        "null_mode": null_mode,
    }

    if usables < MIN_EVENTS:
        # Se publican los estadísticos aunque no haya potencia. Son ruidosos y no
        # sostienen un contraste, pero esconderlos obligaría a quien lee el informe
        # a suponer que no se midió nada; el veredicto ya dice que no se puede
        # concluir.
        salida.update({
            "verdict": "SIN_POTENCIA", "significant": False,
            "observed": _aggregate(lote),
            "note": (f"Solo {usables} eventos con ventana completa y hacen falta "
                     f"{MIN_EVENTS}. De {e.size} dados, {int(np.sum(idx >= 0))} "
                     f"caen dentro del histórico; el resto se pierde en los bordes "
                     f"o en huecos de velas. No es que no haya efecto: es que no "
                     f"se puede medir."),
        })
        return salida

    observado = _aggregate(lote)
    salida["observed"] = observado
    salida["minimum_detectable_car"] = minimum_detectable_car(
        observado["car_sd"], observado["n"])

    # La tolerancia es la ventana de REACCIÓN y no el máximo de las dos. Lo que
    # contamina el control es que su ventana de reacción pise un evento real; que
    # su ventana previa lo pise es menos grave, y exigir las dos cosas dejaba sin
    # control válido a cualquier familia mínimamente densa.
    tol = max(int(post), 1) * paso
    control = control_times(t, e, null_mode, tol, offset_hours=offset_hours)
    cidx = align_events(t, control)
    clote = window_batch(r, cidx[cidx >= 0], pre, post, estimation, gap)
    salida["control_candidates"] = int(control.size)
    salida["control_usable"] = int(clote["index"].size)

    if clote["index"].size < MIN_EVENTS:
        if control.size == 0:
            salida.update({
                "verdict": "NO_IDENTIFICABLE", "significant": False,
                "note": (f"No queda ni un instante de control: con el modo "
                         f"«{null_mode}», todos los candidatos caen dentro de la "
                         f"ventana de reacción de un evento real. El efecto del "
                         f"evento NO se puede separar del efecto de su hora — "
                         f"«¿mueve el evento?» y «¿se mueve el mercado a esa hora de "
                         f"ese día?» son la misma pregunta y ninguna metodología las "
                         f"separa. Ocurre con cualquier familia que ocupe TODAS las "
                         f"casillas de su hora; la salida es estudiar la subfamilia "
                         f"más rara —la mensual dentro de la semanal—, cuyo control "
                         f"son las casillas restantes, o acortar `post` hasta que "
                         f"quepa un hueco entre eventos."),
            })
            return salida
        salida.update({
            "verdict": "SIN_DATOS", "significant": False,
            "note": (f"Solo {clote['index'].size} instantes de control con ventana "
                     f"completa, de {control.size} candidatos, y hacen falta "
                     f"{MIN_EVENTS}."),
        })
        return salida

    controlado = _aggregate(clote)
    salida["control"] = {
        "n": controlado["n"],
        "vol_ratio_mean": controlado["vol_ratio_mean"],
        "car_abs_mean": controlado["car_abs_mean"],
        "note": {
            "matched": ("Instantes de la misma hora y día de la semana que los "
                        "eventos, pero sin evento: el control lleva dentro "
                        "cualquier efecto de esa casilla del calendario, así que "
                        "solo queda en juego el evento."),
            "week": ("Los eventos desplazados semanas enteras: se conservan día de "
                     "la semana y hora UTC."),
            "offset": (f"Los eventos desplazados {offset_hours:g} horas: control con "
                       f"la misma estructura periódica y sin evento."),
        }.get(null_mode, ""),
    }

    # Permutación de etiquetas entre los dos grupos. No se remuestrea el control
    # ni se relocalizan los eventos: se juntan las dos muestras y se reparte al
    # azar quién es evento, que es el nulo exacto de «vienen de la misma
    # distribución».
    rng = np.random.default_rng(seed)
    p_vol = permutation_p(observado["vol_ratio_mean"], lote["vol_ratio"],
                          clote["vol_ratio"], replicates, rng)
    p_car = permutation_p(observado["car_abs_mean"], np.abs(lote["car"]),
                          np.abs(clote["car"]), replicates, rng)

    salida["p_volatility"] = p_vol
    salida["p_direction"] = p_car
    # Dos contrastes sobre los mismos datos, así que el umbral se reparte.
    umbral = 0.05 / 2
    salida["alpha_per_question"] = umbral
    salida["significant"] = bool(p_vol < umbral or p_car < umbral)
    salida["verdict"] = _verdict(p_vol, p_car, umbral, observado)
    salida["note"] = _note(salida)
    salida["protocol"] = (
        "Retorno anormal contra la media de una ventana de estimación separada por "
        "un hueco, y razón de volatilidad realizada contra esa misma ventana. El "
        "contraste es una PERMUTACIÓN de etiquetas entre los eventos y un grupo de "
        "control que conserva la casilla del calendario, con corrección de muestra "
        "finita en el p-valor. Se contrastan DOS preguntas —volatilidad y "
        "dirección— así que el umbral se reparte entre ellas.")
    return salida


def _verdict(p_vol: float, p_car: float, umbral: float, obs: dict) -> str:
    vol = p_vol < umbral
    dire = p_car < umbral
    if vol and dire:
        return "MUEVE_AMBOS"
    if vol:
        return "MUEVE_VOLATILIDAD"
    if dire:
        return "MUEVE_DIRECCION"
    return "SIN_EFECTO_DETECTABLE"


def _note(s: dict) -> str:
    obs = s["observed"]
    mde = s.get("minimum_detectable_car")
    base = (f"{obs['n']} eventos. La volatilidad en la ventana de reacción fue "
            f"{obs['vol_ratio_mean']:.2f}× su referencia "
            f"(p={s['p_volatility']:.3f}) y el movimiento absoluto acumulado "
            f"{obs['car_abs_mean'] * 100:.2f} % (p={s['p_direction']:.3f}). ")
    if s["verdict"] == "SIN_EFECTO_DETECTABLE":
        cola = ("No se detecta efecto, y eso NO es lo mismo que no haberlo: con "
                f"{obs['n']} eventos el retorno acumulado más pequeño detectable "
                f"es de {mde * 100:.2f} % si `mde` es finito. Por debajo de ahí, "
                "este estudio no distingue un efecto de cero.")
        return base + cola.replace(" si `mde` es finito", "")
    if s["verdict"] == "MUEVE_VOLATILIDAD":
        return base + ("Mueve la volatilidad y no la dirección, que es lo esperable "
                       "en un evento programado: si el signo fuera previsible se "
                       "descontaría antes de que ocurriera.")
    if s["verdict"] == "MUEVE_DIRECCION":
        return base + ("Mueve la dirección de forma sistemática, que es un hallazgo "
                       "fuerte y raro. Antes de operarlo hay que descartar que el "
                       "signo venga de un único episodio grande.")
    return base + ("Mueve las dos cosas. Revisar si el efecto direccional sobrevive "
                   "al quitar el evento más extremo.")


def self_note() -> str:
    """Lo que este estudio no puede afirmar."""
    return (
        "Un efecto detectado aquí NO es una estrategia. Dice que alrededor del "
        "evento pasa algo medible; no dice que se pueda capturar después de "
        "comisiones y deslizamiento, y los eventos son justo los momentos en que "
        "el diferencial se abre y la profundidad desaparece. El coste de ejecución "
        "en la ventana de un evento es varias veces el normal, así que un efecto "
        "de volatilidad del 1,5× puede ser rentable o ruinoso según a qué precio "
        "se entre.\n"
        "La referencia conserva día de la semana y hora UTC, pero no conserva el "
        "RÉGIMEN: si los eventos de la muestra se concentran en un tramo volátil "
        "del histórico, parte del efecto medido es del tramo y no del evento. Se ve "
        "comparando la razón de volatilidad previa al evento con 1: si ya era alta "
        "antes, el evento no lo explica todo.\n"
        "Y los eventos macro afectan a todos los activos a la vez, así que promediar "
        "entre activos NO reduce la varianza como si fueran independientes. Un "
        "estudio sobre diez activos y el mismo calendario tiene la potencia de un "
        "estudio sobre un activo, no la de diez."
    )
