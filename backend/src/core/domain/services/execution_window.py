"""
execution_window.py — ¿Ejecuto ahora o espero, y hasta cuándo?

La pregunta que nadie le responde al que opera con su dinero
───────────────────────────────────────────────────────────
Todo el motor de esta plataforma trabaja sobre la pregunta de QUÉ comprar. Esta es
la otra mitad, la que decide cuánto de ese edge llega a la cuenta: **CUÁNDO pulsar
el botón**. Una ventaja de 30 puntos básicos se la come un diferencial abierto y un
libro fino, y el diferencial y la profundidad no son constantes a lo largo de la
semana.

Las mesas institucionales tienen herramientas de pre-trade para esto —estiman el
impacto esperado antes de mandar la orden— y el retail no tiene ninguna. Aquí se
construye con lo que ya hay archivado, sin pedir nada a ningún exchange.

Las tres cosas que entran, y por qué esas
─────────────────────────────────────────
1. **La casilla horaria** (`seasonality`). Si esta hora de esta semana es
   sistemáticamente más convulsa, el deslizamiento esperado es mayor y los stops
   saltan más por ruido. Es información del propio histórico, no una creencia.
2. **Los eventos programados** (`economic_calendar`). Una liquidación de
   financiación o un vencimiento de opciones a dos horas vista es un momento
   conocido de actividad, y se conoce de antemano: es la única familia de variables
   que se puede mirar hacia delante sin cometer lookahead.
3. **El coste a tu tamaño** (`market_impact`). Lo mismo cuesta distinto a 1.000 y a
   1.000.000 USD, y el veredicto no significa nada sin el tamaño.

La regla que gobierna la salida: esto es un FILTRO, no una señal
──────────────────────────────────────────────────────────────
Una hora activa no es una oportunidad: es lo contrario. Más movimiento con
dirección impredecible significa más deslizamiento, no más beneficio esperado. Así
que este módulo **nunca dice qué hacer ni hacia dónde**; dice si el momento es malo
para ejecutar y cuándo sería menos malo. Si alguien lo lee como «ahora sube», está
leyendo lo contrario de lo que mide.

Y el veredicto no se inventa cuando no hay base. Si el estudio de estacionalidad
dijo que NO hay estructura de hora de la semana, el componente horario no aporta
nada al veredicto y la salida lo declara, en vez de pintar un semáforo con un
número que no significa nada.

Capa de dominio: aritmética y calendario, sin Django ni red.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as _tz

import numpy as np

from core.domain.services import economic_calendar as cal
from core.domain.services import seasonality as sn

HORA_MS = 3_600_000

# Horizonte que se explora buscando una ventana mejor.
DEFAULT_HORIZON_HOURS = 48

# Duración por defecto de la ventana que se busca. Dos horas es el tramo en el que
# cabe partir una orden mediana sin que la primera mitad mueva el precio de la
# segunda.
DEFAULT_WINDOW_HOURS = 2

# Actividad relativa por encima de la cual una hora se considera cara. 1.25 no es
# redondo por gusto: es el punto en el que el movimiento extra empieza a notarse
# sobre el diferencial típico de un par líquido.
ACTIVIDAD_ALTA = 1.25
ACTIVIDAD_BAJA = 0.85

# Horas antes y después de un evento de importancia alta que se consideran su
# ventana de contagio. Sale del retardo medido en el estudio de eventos: la
# reacción a un vencimiento se agota en unas pocas velas.
CONTAGIO_ALTA_H = 2
CONTAGIO_MEDIA_H = 1

# Coste de ejecución, en puntos básicos, por encima del cual el tamaño manda sobre
# cualquier consideración horaria: si mover ese nocional cuesta 50 bps, la hora del
# día es el menor de los problemas.
COSTE_DOMINA_BPS = 50.0


def _cell_relative(seasonality: dict) -> tuple[np.ndarray, bool]:
    """Actividad de cada casilla relativa a la media, y si hay base para usarla.

    Devuelve un vector de 168 con la actividad relativa, y un booleano que dice si
    el estudio encontró estructura. Cuando no la encontró, el vector se devuelve
    igualmente —para poder enseñar la rejilla— pero el segundo valor es `False` y
    el veredicto no debe usarlo.
    """
    medias = (seasonality or {}).get("mean_abs_return") or []
    if len(medias) != sn.CASILLAS:
        return np.ones(sn.CASILLAS), False

    v = np.array([np.nan if m is None else float(m) for m in medias], dtype=float)
    centro = float(np.nanmean(v)) if np.isfinite(v).any() else 0.0
    rel = np.ones(sn.CASILLAS)
    if centro > 0:
        rel = np.where(np.isfinite(v), v / centro, 1.0)

    con_base = (seasonality or {}).get("verdict") in ("CON_ESTRUCTURA",
                                                     "ESTRUCTURA_DIFUSA")
    return rel, bool(con_base)


def _significant_cells(seasonality: dict) -> set[int]:
    """Casillas que sobrevivieron a la corrección por multiplicidad.

    Se distinguen de las demás porque son las únicas sobre las que se puede
    afirmar algo. Una casilla con actividad alta que NO sobrevivió es una pista,
    y el veredicto lo dice con otras palabras.
    """
    detalle = (seasonality or {}).get("cell_detail") or {}
    return {int(c["cell"]) for c in detalle.get("significant", [])}


def upcoming_events(events: list, now_ms: int, horizon_hours: int) -> list[dict]:
    """Eventos programados dentro del horizonte, ordenados y con su cercanía."""
    fin = int(now_ms) + int(horizon_hours) * HORA_MS
    salida = []
    for e in events:
        if not (now_ms <= e.scheduled_at <= fin):
            continue
        salida.append({
            "key": e.key,
            "at": e.scheduled_iso,
            "at_ms": int(e.scheduled_at),
            "in_hours": round((e.scheduled_at - now_ms) / HORA_MS, 1),
            "importance": e.importance,
            "note": e.note,
        })
    return sorted(salida, key=lambda x: x["at_ms"])


def _event_pressure(events: list, inicio_ms: int, fin_ms: int) -> list[dict]:
    """Eventos cuya ventana de contagio solapa con el tramo dado."""
    tocan = []
    for e in events:
        margen = (CONTAGIO_ALTA_H if e.importance == cal.ALTA
                  else CONTAGIO_MEDIA_H if e.importance == cal.MEDIA else 0)
        desde = e.scheduled_at - margen * HORA_MS
        hasta = e.scheduled_at + margen * HORA_MS
        if desde <= fin_ms and hasta >= inicio_ms:
            tocan.append(e)
    return tocan


def score_hours(now_ms: int, seasonality: dict, events: list,
                horizon_hours: int = DEFAULT_HORIZON_HOURS) -> list[dict]:
    """Una puntuación de «lo caro que sale ejecutar» para cada hora del horizonte.

    La puntuación es deliberadamente simple y legible: la actividad relativa de la
    casilla, penalizada por los eventos que tocan esa hora. No se calibra contra
    nada porque no es un contraste estadístico —no afirma que una hora sea
    significativamente peor que otra— sino una ORDENACIÓN para decidir cuándo
    mirar. Presentarla como un p-valor sería prestarle un rigor que no tiene.
    """
    rel, con_base = _cell_relative(seasonality)
    significativas = _significant_cells(seasonality)

    filas = []
    base = int(now_ms) - (int(now_ms) % HORA_MS)
    for h in range(int(horizon_hours)):
        inicio = base + h * HORA_MS
        casilla = int(sn.week_hour_index([inicio])[0])
        actividad = float(rel[casilla])
        tocan = _event_pressure(events, inicio, inicio + HORA_MS - 1)

        # El recargo por evento se suma a la actividad en lugar de multiplicarla:
        # los dos efectos son aditivos en la práctica y multiplicarlos haría que
        # una hora ya activa con un evento pareciera catastrófica.
        recargo = sum(0.35 if e.importance == cal.ALTA
                      else 0.15 if e.importance == cal.MEDIA else 0.05
                      for e in tocan)

        filas.append({
            "hour_ms": inicio,
            "at": datetime.fromtimestamp(inicio / 1000, _tz.utc).isoformat(),
            "cell": casilla,
            "day": sn.DAY_NAMES[casilla // 24],
            "hour_utc": casilla % 24,
            "activity": round(actividad, 3) if con_base else None,
            "established": casilla in significativas,
            "events": [e.key for e in tocan],
            "event_importance": ([cal.ALTA] if any(e.importance == cal.ALTA for e in tocan)
                                 else [cal.MEDIA] if any(e.importance == cal.MEDIA for e in tocan)
                                 else []),
            "score": round((actividad if con_base else 1.0) + recargo, 3),
        })
    return filas


def find_window(horas: list[dict], length_hours: int = DEFAULT_WINDOW_HOURS,
                skip_first: int = 1) -> dict | None:
    """El tramo contiguo más barato del horizonte.

    `skip_first` salta la hora en curso: la ventana que se propone tiene que ser
    una a la que se pueda LLEGAR, y la actual ya está empezada. Sin esto, la
    herramienta recomendaría esperar hasta un momento que ya ha pasado.
    """
    L = max(int(length_hours), 1)
    inicio_min = max(int(skip_first), 0)
    if len(horas) < inicio_min + L:
        return None

    mejor = None
    for i in range(inicio_min, len(horas) - L + 1):
        tramo = horas[i:i + L]
        coste = float(np.mean([h["score"] for h in tramo]))
        if mejor is None or coste < mejor["score"]:
            mejor = {
                "from": tramo[0]["at"],
                "to": datetime.fromtimestamp(
                    (tramo[-1]["hour_ms"] + HORA_MS) / 1000, _tz.utc).isoformat(),
                "in_hours": round((tramo[0]["hour_ms"] - horas[0]["hour_ms"]) / HORA_MS, 1),
                "length_hours": L,
                "score": round(coste, 3),
                "events": sorted({k for h in tramo for k in h["events"]}),
                "day": tramo[0]["day"],
                "hour_utc": tramo[0]["hour_utc"],
            }
    return mejor


def assess(now_ms: int, seasonality: dict, events: list, cost: dict | None = None,
           horizon_hours: int = DEFAULT_HORIZON_HOURS,
           window_hours: int = DEFAULT_WINDOW_HOURS) -> dict:
    """Veredicto sobre el momento actual, con sus razones y una alternativa.

    El veredicto se construye con razones explícitas y nunca sin base: si el
    estudio de estacionalidad no encontró estructura de hora de la semana, el
    componente horario no entra, y la salida lo dice en vez de pintar un semáforo
    sobre un número que no significa nada.
    """
    rel, con_base = _cell_relative(seasonality)
    significativas = _significant_cells(seasonality)

    horas = score_hours(now_ms, seasonality, events, horizon_hours)
    ahora = horas[0] if horas else None
    ventana = find_window(horas, window_hours)
    proximos = upcoming_events(events, now_ms, horizon_hours)

    razones: list[str] = []
    señales: list[str] = []

    # ── el componente horario
    if not con_base:
        razones.append(
            "La hora del día NO entra en el veredicto: el estudio de "
            "estacionalidad no encontró estructura de hora de la semana en este "
            "activo, así que cualquier semáforo basado en la hora sería un adorno.")
    elif ahora is not None and ahora["activity"] is not None:
        act = ahora["activity"]
        establecida = ahora["cell"] in significativas
        matiz = ("y esa casilla sobrevive a la corrección por multiplicidad"
                 if establecida else
                 "aunque esa casilla NO sobrevive a la corrección por "
                 "multiplicidad, así que es una pista y no un hecho")
        if act >= ACTIVIDAD_ALTA:
            señales.append("hora_activa")
            razones.append(
                f"Ahora es {ahora['day']} {ahora['hour_utc']:02d}:00 UTC, con "
                f"{act:.2f}× el movimiento medio de este activo — {matiz}. Más "
                f"movimiento con dirección impredecible es más deslizamiento, no "
                f"más beneficio esperado.")
        elif act <= ACTIVIDAD_BAJA:
            señales.append("hora_tranquila")
            razones.append(
                f"Ahora es {ahora['day']} {ahora['hour_utc']:02d}:00 UTC, con "
                f"{act:.2f}× el movimiento medio — una de las horas tranquilas, "
                f"{matiz}.")
        else:
            razones.append(
                f"La hora actual ({ahora['day']} {ahora['hour_utc']:02d}:00 UTC) "
                f"está en la media de actividad del activo ({act:.2f}×).")

    # ── los eventos
    inminente = next((e for e in proximos
                      if e["importance"] == cal.ALTA
                      and e["in_hours"] <= CONTAGIO_ALTA_H), None)
    # Los de importancia media también cuentan, con su propia ventana y con menos
    # peso. Un vencimiento mensual a una hora vista mueve el libro de verdad, y la
    # primera versión de esto no lo señalaba porque solo miraba los de importancia
    # alta: salía NEUTRAL a sesenta minutos de un vencimiento.
    cercano = next((e for e in proximos
                    if e["importance"] == cal.MEDIA
                    and e["in_hours"] <= CONTAGIO_MEDIA_H), None)

    if inminente:
        señales.append("evento_inminente")
        razones.append(
            f"Hay un evento de importancia alta ({inminente['key']}) dentro de "
            f"{inminente['in_hours']:.1f} h. Es un momento conocido de actividad y "
            f"se sabía de antemano: el libro se estrecha antes y se mueve después.")
    elif cercano:
        señales.append("evento_cercano")
        razones.append(
            f"Hay un evento de importancia media ({cercano['key']}) dentro de "
            f"{cercano['in_hours']:.1f} h. No concentra tanta atención como los "
            f"grandes, pero sí basta para ensanchar el diferencial.")
    elif proximos and proximos[0]["in_hours"] <= CONTAGIO_ALTA_H:
        razones.append(
            f"El próximo evento ({proximos[0]['key']}, importancia "
            f"{proximos[0]['importance']}) está a {proximos[0]['in_hours']:.1f} h, "
            f"pero no es de los que concentran atención.")

    # ── el coste a tamaño
    coste_bps = None
    if cost and cost.get("available") is not False:
        pasos = cost.get("steps") or []
        if pasos:
            coste_bps = pasos[0].get("impact_bps")
    if coste_bps is not None and coste_bps >= COSTE_DOMINA_BPS:
        señales.append("coste_domina")
        razones.append(
            f"A este tamaño, el impacto estimado es de {coste_bps:.0f} puntos "
            f"básicos. Por encima de {COSTE_DOMINA_BPS:.0f} bps el tamaño manda "
            f"sobre cualquier consideración horaria: lo que hay que cambiar es el "
            f"tamaño o trocear la orden, no la hora.")

    veredicto = _verdict(señales, con_base)
    return {
        "verdict": veredicto,
        "signals": señales,
        "reasons": razones,
        "now": ahora,
        "hours": horas,
        "best_window": ventana,
        "upcoming_events": proximos[:12],
        "seasonality_usable": con_base,
        "cost_bps_first_step": coste_bps,
        "horizon_hours": int(horizon_hours),
        "protocol": (
            "La puntuación por hora es la actividad relativa de su casilla de la "
            "rejilla semanal más un recargo por los eventos programados que la "
            "tocan. Es una ORDENACIÓN para decidir cuándo mirar, no un contraste: "
            "no afirma que una hora sea significativamente peor que otra. Lo que "
            "sí lleva contraste es la rejilla —con su corrección por "
            "multiplicidad— y el campo `established` dice si la casilla actual "
            "sobrevivió a ella."),
        "note": _note(veredicto, señales, ventana, con_base),
        "limits": self_note(),
    }


def _verdict(señales: list[str], con_base: bool) -> str:
    if "coste_domina" in señales:
        return "EL_TAMANO_MANDA"
    if "evento_inminente" in señales:
        return "ESPERAR"
    if "hora_activa" in señales or "evento_cercano" in señales:
        return "DESFAVORABLE"
    if not con_base:
        return "SIN_BASE_HORARIA"
    if "hora_tranquila" in señales:
        return "FAVORABLE"
    return "NEUTRAL"


def _note(veredicto: str, señales: list[str], ventana: dict | None,
          con_base: bool) -> str:
    alternativa = ""
    if ventana:
        alternativa = (f" La ventana más barata del horizonte empieza en "
                       f"{ventana['in_hours']:.0f} h ({ventana['day']} "
                       f"{ventana['hour_utc']:02d}:00 UTC, {ventana['length_hours']} h).")

    if veredicto == "EL_TAMANO_MANDA":
        return ("El coste de mover este nocional domina cualquier efecto de la hora. "
                "Trocear la orden o reducir el tamaño cambia el resultado mucho más "
                "que esperar." + alternativa)
    if veredicto == "ESPERAR":
        return ("Hay un evento programado de importancia alta encima. No es una "
                "predicción de dirección: es que el diferencial se abre y la "
                "profundidad desaparece justo entonces." + alternativa)
    if veredicto == "DESFAVORABLE":
        causa = ("Hay un evento de importancia media encima"
                 if "evento_cercano" in señales and "hora_activa" not in señales
                 else "Esta hora es de las activas para este activo")
        return (f"{causa}, así que el deslizamiento esperado es mayor de lo normal."
                + alternativa)
    if veredicto == "SIN_BASE_HORARIA":
        return ("No hay evidencia de estructura de hora de la semana en este activo, "
                "así que no se emite veredicto horario. Eso NO significa que todas "
                "las horas sean iguales: significa que con este histórico no se "
                "puede saber.")
    if veredicto == "FAVORABLE":
        return ("Hora tranquila y sin eventos encima: de las condiciones menos malas "
                "del horizonte para ejecutar." + alternativa)
    return ("Nada destacable en la hora actual ni en el calendario inmediato."
            + alternativa)


def self_note() -> str:
    """Lo que esta herramienta no es."""
    return (
        "Esto es un FILTRO DE EJECUCIÓN, no una señal. No dice qué comprar ni hacia "
        "dónde va el precio, y una hora tranquila no es una hora en la que suba: es "
        "una en la que cuesta menos entrar. Leerlo como un indicador de dirección es "
        "leer lo contrario de lo que mide.\n"
        "La rejilla horaria supone que el patrón semanal del pasado sigue vigente. "
        "La estructura de sesiones cambia cuando cambia quién opera —la entrada de "
        "instituciones movió actividad hacia el horario de Nueva York—, así que una "
        "rejilla estimada sobre tres años describe un promedio y no el mes que "
        "viene.\n"
        "El calendario solo cubre lo derivable por regla: liquidaciones de "
        "financiación, vencimientos, cierres de periodo, nómina no agrícola y "
        "halvings ocurridos. El FOMC, el IPC y las decisiones regulatorias NO están, "
        "así que la ausencia de eventos en la lista no significa que no haya nada "
        "previsto — significa que no hay nada de lo que este motor sabe derivar.\n"
        "Y el coste es de un modelo calibrado con volumen y volatilidad, no una "
        "lectura del libro de órdenes. En el momento de un evento, el libro real es "
        "peor que el que el modelo supone."
    )
