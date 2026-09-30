"""
economic_calendar.py — Los instantes en que el mercado SABE que va a pasar algo.

Por qué esto no es una tabla de fechas
──────────────────────────────────────
Un calendario económico es, en casi todas las plataformas, un adorno: una lista
de banderitas con «importancia alta» que nadie cruza con los precios. Aquí
existe por una razón concreta y comprobable: **el instante de un evento
programado es la única variable exógena que se conoce con antelación.** El
funding se conoce cuando se liquida, el flujo de ballenas cuando ocurre, la
métrica de cadena cuando se publica. La fecha de la próxima nómina no agrícola
se sabe con un año de adelanto.

Eso la convierte en la única familia de variables que se puede usar mirando
hacia DELANTE sin cometer lookahead — y precisamente por eso es la más
peligrosa de todas, porque la frontera entre lo legítimo y la trampa es fina y
se cruza sin darse cuenta.

La distinción que lo gobierna todo: programado vs sorpresa
─────────────────────────────────────────────────────────
Cada evento tiene tres instantes distintos y confundirlos es el error:

  · `announced_at` — cuándo se SUPO que el evento ocurriría. Es el único que
    autoriza a usar el evento como variable en la vela `t`: si el calendario se
    publicó después de `t`, esa fila no podía saberlo.
  · `scheduled_at` — cuándo está previsto. Conocido desde `announced_at`, así
    que «faltan seis horas para la nómina» es una feature LEGÍTIMA en la vela
    `t`, aunque hable del futuro.
  · `actual_at` — cuándo se publicó de verdad, y **el CONTENIDO** (el dato, la
    sorpresa frente al consenso). Esto no existe hasta que ocurre. Meterlo en la
    fila `t` con `t` anterior al evento es lookahead del peor tipo, y produce un
    modelo espectacular e inoperable.

Por eso este módulo construye features solo con `scheduled_at` filtrado por
`announced_at ≤ t`, y la magnitud de la sorpresa se declara como lo que es: una
variable que solo se puede usar DESPUÉS, con su retardo, y que vive en otro sitio.

Qué se puede derivar sin red, y qué no
──────────────────────────────────────
Aquí hay una línea que no se cruza: **no se inventan fechas.** Un calendario con
reuniones del FOMC puestas a ojo produciría un estudio de eventos sobre días en
los que no pasó nada, y el resultado —ruido— se leería como «los eventos macro
no mueven cripto», que es una conclusión falsa obtenida de datos falsos.

Así que se separan dos mundos:

**Derivable por regla** (lo que genera este módulo, sin red y sin fabricar nada):

  · Liquidaciones de financiación: 00:00, 08:00 y 16:00 UTC, todos los días. Tres
    al día, más de mil al año: es la familia con más potencia estadística de
    todas, y es específica de cripto.
  · Vencimiento de opciones de Deribit: viernes a las 08:00 UTC, con el último
    viernes del mes como vencimiento mensual y los de marzo, junio, septiembre y
    diciembre como trimestrales.
  · Cierre de mes y de trimestre, en UTC.
  · Nómina no agrícola (NFP): primer viernes de cada mes a las 08:30 de Nueva
    York. La hora de Nueva York importa: con horario de verano son las 12:30 UTC
    y con horario de invierno las 13:30, y equivocarse desplaza el evento
    exactamente una vela horaria.
  · Halvings de Bitcoin pasados: son hechos históricos con fecha conocida, no una
    estimación. Se listan los cuatro ocurridos y nada más.

**No derivable** (exige un calendario ingerido, y sin él se declara ausente):
el FOMC, el IPC, el PCE, el PIB, el BCE y las decisiones regulatorias. Sus fechas
las publica cada organismo y no salen de ninguna regla; `UNDERIVABLE` las nombra
para que la ausencia sea un hecho documentado y no un hueco silencioso, igual que
`MISSING_HISTORY` hace en `exogenous_features`.

Capa de dominio: calendario y aritmética, sin Django ni red.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as _tz
from zoneinfo import ZoneInfo

UTC = _tz.utc
NY = ZoneInfo("America/New_York")

# Importancia declarada. No es una opinión sobre el evento: es cuánta atención
# concentra, que es lo que determina si mueve precio.
ALTA, MEDIA, BAJA = "alta", "media", "baja"

# Horas UTC de liquidación de financiación en los perpetuos USDⓈ-M.
FUNDING_HOURS_UTC: tuple[int, ...] = (0, 8, 16)

# Vencimiento de opciones de Deribit: viernes a las 08:00 UTC.
EXPIRY_WEEKDAY = 4          # 0 = lunes
EXPIRY_HOUR_UTC = 8

# Nómina no agrícola: primer viernes del mes, 08:30 en Nueva York.
NFP_WEEKDAY = 4
NFP_HOUR_NY, NFP_MINUTE_NY = 8, 30

# Halvings de Bitcoin ya ocurridos, en UTC. Son hechos con fecha, no estimaciones;
# el quinto no se lista porque su fecha depende de la altura de bloque futura y
# poner una estimación aquí sería exactamente lo que este módulo no hace.
BITCOIN_HALVINGS: tuple[str, ...] = (
    "2012-11-28T15:24:00+00:00",
    "2016-07-09T16:46:00+00:00",
    "2020-05-11T19:23:00+00:00",
    "2024-04-20T00:09:00+00:00",
)

# Lo que NO se puede derivar por regla y por tanto exige calendario ingerido.
UNDERIVABLE: dict[str, str] = {
    "FOMC": ("Ocho reuniones al año con fechas que publica la Reserva Federal; no "
             "salen de ninguna regla de calendario."),
    "CPI": ("El día exacto lo fija el calendario de publicaciones del BLS y varía "
            "cada mes."),
    "PCE": "Calendario del BEA.",
    "GDP": "Calendario del BEA, con tres estimaciones por trimestre.",
    "ECB": "Calendario del Banco Central Europeo.",
    "REGULATORY": ("Decisiones de la SEC y equivalentes: por definición no tienen "
                   "fecha previa fiable."),
}


@dataclass(frozen=True)
class CalendarEvent:
    """Un instante en que el mercado espera información.

    Los tres sellos temporales son el contenido real de esta clase. `announced_at`
    es el que decide si el evento puede entrar en la fila `t` de un modelo;
    `scheduled_at` es lo que se puede usar; `actual_at` solo existe a posteriori.
    """
    key: str
    scheduled_at: int                 # epoch ms UTC
    announced_at: int                 # epoch ms UTC
    importance: str = MEDIA
    region: str = "GLOBAL"
    actual_at: int | None = None
    derived: bool = True              # ¿lo generó una regla de este módulo?
    note: str = ""

    @property
    def scheduled_iso(self) -> str:
        return datetime.fromtimestamp(self.scheduled_at / 1000, UTC).isoformat()


# ────────────────────────────────────────────────────────────── utilidades


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _iter_months(desde: datetime, hasta: datetime):
    """Primer día de cada mes tocado por el intervalo, en UTC."""
    cursor = datetime(desde.year, desde.month, 1, tzinfo=UTC)
    while cursor <= hasta:
        yield cursor
        cursor = (datetime(cursor.year + 1, 1, 1, tzinfo=UTC) if cursor.month == 12
                  else datetime(cursor.year, cursor.month + 1, 1, tzinfo=UTC))


def nth_weekday(year: int, month: int, weekday: int, n: int = 1) -> datetime:
    """Fecha del n-ésimo `weekday` del mes, en UTC y a medianoche."""
    primero = datetime(year, month, 1, tzinfo=UTC)
    desplazamiento = (weekday - primero.weekday()) % 7
    return primero + timedelta(days=desplazamiento + 7 * (n - 1))


def last_weekday(year: int, month: int, weekday: int) -> datetime:
    """Último `weekday` del mes, en UTC y a medianoche."""
    siguiente = (datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12
                 else datetime(year, month + 1, 1, tzinfo=UTC))
    ultimo = siguiente - timedelta(days=1)
    return ultimo - timedelta(days=(ultimo.weekday() - weekday) % 7)


# ──────────────────────────────────────────────── generadores por regla


def funding_settlements(start_ms: int, end_ms: int,
                        hours: tuple[int, ...] = FUNDING_HOURS_UTC
                        ) -> list[CalendarEvent]:
    """Liquidaciones de financiación: la familia con más potencia de todas.

    Tres al día y más de mil al año, con hora fija y conocida desde siempre. Eso
    la convierte en el único evento de este módulo con el que se puede medir un
    efecto pequeño: con 36 nóminas no agrícolas al año no hay potencia para
    detectar nada por debajo de un movimiento grande, y con 1.095 liquidaciones sí.

    `announced_at` es 0: la hora de liquidación es parte del contrato del
    perpetuo, así que se conoce desde antes de que existiera cualquier vela.
    """
    eventos = []
    desde = datetime.fromtimestamp(start_ms / 1000, UTC)
    hasta = datetime.fromtimestamp(end_ms / 1000, UTC)
    dia = datetime(desde.year, desde.month, desde.day, tzinfo=UTC)
    while dia <= hasta:
        for h in hours:
            t = dia.replace(hour=h)
            if start_ms <= _ms(t) <= end_ms:
                eventos.append(CalendarEvent(
                    key="FUNDING_SETTLEMENT", scheduled_at=_ms(t), announced_at=0,
                    importance=BAJA, region="CRYPTO",
                    note=("Liquidación de financiación del perpetuo: hora fija por "
                          "contrato."),
                ))
        dia += timedelta(days=1)
    return eventos


def option_expiries(start_ms: int, end_ms: int) -> list[CalendarEvent]:
    """Vencimientos de opciones: viernes 08:00 UTC, con mensual y trimestral.

    La importancia sube con el tamaño del vencimiento, y el tamaño se concentra en
    el último viernes del mes y sobre todo en los trimestrales. Un vencimiento
    semanal y uno trimestral no son el mismo evento y meterlos en la misma bolsa
    diluiría el efecto del segundo hasta hacerlo invisible.
    """
    eventos = []
    desde = datetime.fromtimestamp(start_ms / 1000, UTC)
    hasta = datetime.fromtimestamp(end_ms / 1000, UTC)

    mensuales, trimestrales = set(), set()
    for mes in _iter_months(desde, hasta):
        ultimo = last_weekday(mes.year, mes.month, EXPIRY_WEEKDAY)
        mensuales.add(ultimo.date())
        if mes.month in (3, 6, 9, 12):
            trimestrales.add(ultimo.date())

    dia = datetime(desde.year, desde.month, desde.day, tzinfo=UTC)
    while dia <= hasta:
        if dia.weekday() == EXPIRY_WEEKDAY:
            t = dia.replace(hour=EXPIRY_HOUR_UTC)
            if start_ms <= _ms(t) <= end_ms:
                if dia.date() in trimestrales:
                    clave, imp = "OPTION_EXPIRY_QUARTERLY", ALTA
                elif dia.date() in mensuales:
                    clave, imp = "OPTION_EXPIRY_MONTHLY", MEDIA
                else:
                    clave, imp = "OPTION_EXPIRY_WEEKLY", BAJA
                eventos.append(CalendarEvent(
                    key=clave, scheduled_at=_ms(t), announced_at=0,
                    importance=imp, region="CRYPTO",
                    note="Vencimiento de opciones: viernes 08:00 UTC.",
                ))
        dia += timedelta(days=1)
    return eventos


def period_ends(start_ms: int, end_ms: int) -> list[CalendarEvent]:
    """Cierre de mes y de trimestre, a las 00:00 UTC del último día."""
    eventos = []
    desde = datetime.fromtimestamp(start_ms / 1000, UTC)
    hasta = datetime.fromtimestamp(end_ms / 1000, UTC)
    for mes in _iter_months(desde, hasta):
        siguiente = (datetime(mes.year + 1, 1, 1, tzinfo=UTC) if mes.month == 12
                     else datetime(mes.year, mes.month + 1, 1, tzinfo=UTC))
        cierre = siguiente - timedelta(days=1)
        if not (start_ms <= _ms(cierre) <= end_ms):
            continue
        trimestral = mes.month in (3, 6, 9, 12)
        eventos.append(CalendarEvent(
            key="QUARTER_END" if trimestral else "MONTH_END",
            scheduled_at=_ms(cierre), announced_at=0,
            importance=MEDIA if trimestral else BAJA, region="GLOBAL",
            note="Cierre de periodo en UTC: rebalanceo y marcado de carteras.",
        ))
    return eventos


def nonfarm_payrolls(start_ms: int, end_ms: int) -> list[CalendarEvent]:
    """Nómina no agrícola: primer viernes del mes, 08:30 de Nueva York.

    La única publicación macro que sale de una regla de calendario, y aun así hay
    una trampa: la hora es de Nueva York, no UTC. Con horario de verano el evento
    cae a las 12:30 UTC y con horario de invierno a las 13:30, así que tratarlo
    como una hora UTC fija lo desplaza una vela horaria durante ocho meses al año.
    Se resuelve construyendo la hora en Nueva York y convirtiendo.

    `announced_at` es un año antes: el BLS publica el calendario con esa
    antelación. Se pone un año exacto en vez de la fecha real de publicación
    porque es una cota conservadora y no requiere inventarse nada.
    """
    eventos = []
    desde = datetime.fromtimestamp(start_ms / 1000, UTC)
    hasta = datetime.fromtimestamp(end_ms / 1000, UTC)
    for mes in _iter_months(desde, hasta):
        dia = nth_weekday(mes.year, mes.month, NFP_WEEKDAY, 1)
        local = datetime(dia.year, dia.month, dia.day, NFP_HOUR_NY, NFP_MINUTE_NY,
                         tzinfo=NY)
        t = _ms(local.astimezone(UTC))
        if start_ms <= t <= end_ms:
            eventos.append(CalendarEvent(
                key="NFP", scheduled_at=t,
                announced_at=t - 365 * 24 * 3_600_000,
                importance=ALTA, region="US",
                note=("Nómina no agrícola: primer viernes, 08:30 de Nueva York "
                      "(12:30 UTC en verano, 13:30 en invierno)."),
            ))
    return eventos


def bitcoin_halvings(start_ms: int, end_ms: int) -> list[CalendarEvent]:
    """Los halvings ya ocurridos. El siguiente NO se estima."""
    eventos = []
    for iso in BITCOIN_HALVINGS:
        t = _ms(datetime.fromisoformat(iso))
        if start_ms <= t <= end_ms:
            eventos.append(CalendarEvent(
                key="BTC_HALVING", scheduled_at=t,
                announced_at=0, importance=ALTA, region="CRYPTO",
                note=("Reducción a la mitad de la emisión. La fecha exacta depende "
                      "de la altura de bloque, así que esta es la ocurrida y no "
                      "una previsión."),
            ))
    return eventos


# Cómo hay que estudiar cada familia, y por qué. No es configuración: es una
# propiedad de la estructura temporal de cada una, y equivocarla invalida el
# estudio. Se declara aquí, junto al generador que produce los eventos, en vez de
# dejarla a criterio de quien lanza el comando.
FAMILY_STUDY_HINTS: dict[str, dict] = {
    "FUNDING_SETTLEMENT": {
        "null_mode": "offset", "post": 2, "offset_hours": 4.0,
        "why": ("Cada ocho horas. Con una ventana de reacción de seis velas las "
                "ventanas tejen todo el histórico y no queda ningún instante "
                "normal contra el que comparar, así que la reacción se acorta a "
                "dos y el control son las 04:00/12:00/20:00, con la misma "
                "estructura de tres al día y sin liquidación."),
    },
    "OPTION_EXPIRY_WEEKLY": {
        "null_mode": "matched", "post": 6,
        "why": ("Todos los viernes a las 08:00. Su único control posible son los "
                "viernes que llevan vencimiento mensual, así que lo que se "
                "contrasta es «semanal frente a mensual» y no «vencimiento frente "
                "a nada»."),
    },
    "OPTION_EXPIRY_MONTHLY": {
        "null_mode": "matched", "post": 6,
        "why": ("Último viernes del mes. El control son los demás viernes a las "
                "08:00, que es lo que hace identificable el efecto del tamaño del "
                "vencimiento por encima del efecto de ser viernes."),
    },
    "OPTION_EXPIRY_QUARTERLY": {"null_mode": "matched", "post": 6,
                                "why": "Como el mensual, con menos eventos."},
    "MONTH_END": {"null_mode": "matched", "post": 6,
                  "why": "Un día de cada mes a las 00:00 UTC."},
    "QUARTER_END": {"null_mode": "matched", "post": 6,
                    "why": "Cuatro al año: la potencia es mínima y hay que decirlo."},
    "NFP": {
        "null_mode": "matched", "post": 6,
        "why": ("Primer viernes a las 08:30 de Nueva York. El control son los "
                "demás viernes a esa misma hora UTC, que con el horario de verano "
                "son dos casillas distintas — 12:00 y 13:00 — y el emparejado las "
                "respeta por separado."),
    },
    "BTC_HALVING": {
        "null_mode": "matched", "post": 6,
        "why": ("Cuatro en toda la historia. No hay potencia para ningún "
                "contraste y el estudio lo dirá; se incluye para que la ausencia "
                "de conclusión sea explícita."),
    },
}

DEFAULT_STUDY_HINT = {"null_mode": "matched", "post": 6,
                      "why": "Familia sin indicación propia."}


def study_hint(key: str) -> dict:
    """Ajustes con los que se debe estudiar esta familia."""
    return dict(FAMILY_STUDY_HINTS.get(key, DEFAULT_STUDY_HINT))


DERIVED_GENERATORS = {
    "funding": funding_settlements,
    "expiry": option_expiries,
    "period": period_ends,
    "nfp": nonfarm_payrolls,
    "halving": bitcoin_halvings,
}


def derived_calendar(start_ms: int, end_ms: int,
                     families: tuple[str, ...] | None = None) -> list[CalendarEvent]:
    """Todos los eventos derivables por regla en el intervalo, ordenados."""
    elegidas = families or tuple(DERIVED_GENERATORS)
    eventos: list[CalendarEvent] = []
    for nombre in elegidas:
        generador = DERIVED_GENERATORS.get(nombre)
        if generador:
            eventos.extend(generador(int(start_ms), int(end_ms)))
    return sorted(eventos, key=lambda e: (e.scheduled_at, e.key))


def describe(eventos: list[CalendarEvent]) -> dict:
    """Recuento por clave, con lo que falta declarado.

    El recuento no es decorativo: es lo que dice si un estudio de eventos sobre
    esa familia tiene alguna potencia. Doce nóminas al año no detectan un efecto
    pequeño ni con la mejor metodología del mundo.
    """
    por_clave: dict[str, int] = {}
    for e in eventos:
        por_clave[e.key] = por_clave.get(e.key, 0) + 1
    return {
        "total": len(eventos),
        "by_key": dict(sorted(por_clave.items(), key=lambda kv: -kv[1])),
        "first": eventos[0].scheduled_iso if eventos else None,
        "last": eventos[-1].scheduled_iso if eventos else None,
        "underivable": dict(UNDERIVABLE),
        "note": (
            "Solo eventos derivables por regla. Las publicaciones macro con fecha "
            "irregular —FOMC, IPC, PCE, PIB, BCE— no están porque sus fechas no "
            "salen de ninguna regla y ponerlas a ojo produciría un estudio sobre "
            "días en los que no pasó nada."),
    }


# ───────────────────────────────────────────── features point-in-time

# Tope del horizonte, en velas. Sin tope, «faltan 900 velas para el próximo
# halving» domina la escala de la variable y el modelo aprende la tendencia del
# reloj en vez del efecto del evento. Con tope, la variable dice «lejos» y ya.
FEATURE_HORIZON_BARS = 168

# Velas que se consideran «dentro» de un evento una vez ocurrido.
FEATURE_ACTIVE_BARS = 6

# Eventos por delante que se exploran buscando el primero VISIBLE. Casi siempre
# es el inmediato; el tope existe para que el coste sea lineal y está declarado.
_LOOKAHEAD_CAP = 24


def _visible_next(marcas, programados, anunciados):
    """Velas hasta el próximo evento YA ANUNCIADO en cada instante.

    Aquí vive la única regla que hace legítimas estas variables. Un evento
    programado se puede usar mirando hacia delante —«faltan seis velas para la
    nómina» es sabido en la vela `t`— pero solo si en `t` ya se había ANUNCIADO
    que ocurriría. Si el calendario se publicó después, esa fila no podía
    saberlo, y usarla es lookahead con aspecto de feature legítima.

    Por eso no basta con buscar el siguiente evento por fecha: hay que buscar el
    siguiente cuyo anuncio sea anterior o igual a la vela.
    """
    import numpy as np

    t = np.asarray(marcas, dtype=np.int64)
    s = np.asarray(programados, dtype=np.int64)
    a = np.asarray(anunciados, dtype=np.int64)
    if s.size == 0:
        return np.full(t.size, np.iinfo(np.int64).max, dtype=np.int64)

    orden = np.argsort(s)
    s, a = s[orden], a[orden]
    pos = np.searchsorted(s, t, side="right")       # primer evento con sched > t

    salida = np.full(t.size, np.iinfo(np.int64).max, dtype=np.int64)
    pendiente = np.ones(t.size, dtype=bool)
    for k in range(_LOOKAHEAD_CAP):
        cand = pos + k
        dentro = pendiente & (cand < s.size)
        if not dentro.any():
            break
        idx = np.where(dentro)[0]
        visible = a[cand[idx]] <= t[idx]
        elegidos = idx[visible]
        salida[elegidos] = s[cand[elegidos]] - t[elegidos]
        pendiente[elegidos] = False
    return salida


def _last_seen(marcas, programados):
    """Milisegundos desde el último evento ocurrido en cada instante.

    Aquí no hace falta filtrar por anuncio: un evento que ya ocurrió es
    observable, se hubiera anunciado antes o no.
    """
    import numpy as np

    t = np.asarray(marcas, dtype=np.int64)
    s = np.sort(np.asarray(programados, dtype=np.int64))
    if s.size == 0:
        return np.full(t.size, np.iinfo(np.int64).max, dtype=np.int64)
    pos = np.searchsorted(s, t, side="right") - 1
    salida = np.full(t.size, np.iinfo(np.int64).max, dtype=np.int64)
    hay = pos >= 0
    salida[hay] = t[hay] - s[pos[hay]]
    return salida


def calendar_features(timestamps, events: list[CalendarEvent],
                      horizon_bars: int = FEATURE_HORIZON_BARS,
                      active_bars: int = FEATURE_ACTIVE_BARS,
                      bar_ms: int | None = None) -> dict:
    """Variables de calendario para cada vela, sin lookahead.

    Tres por familia, y cada una responde a una pregunta distinta:

      · `cal_<fam>_to_next` — cuánto falta, normalizado por el horizonte y con
        tope en 1. Es la que puede anticipar el posicionamiento previo.
      · `cal_<fam>_since` — cuánto ha pasado. Es la que capta la resaca del
        evento.
      · `cal_<fam>_active` — si la vela está dentro de la ventana de reacción.

    Todas usan `scheduled_at` filtrado por `announced_at ≤ t`, nunca el contenido
    del evento. La sorpresa frente al consenso no aparece aquí y no es un olvido:
    es que no existe hasta que el evento ocurre, así que como variable de la vela
    `t` con `t` anterior al evento sería lookahead. Cuando haya sorpresas
    ingeridas, su sitio es una variable con retardo y otro bloque.
    """
    import numpy as np

    t = np.asarray(timestamps, dtype=np.int64)
    if t.size == 0:
        return {}
    paso = int(bar_ms) if bar_ms else (
        int(np.median(np.diff(t))) if t.size > 1 else 3_600_000)
    paso = max(paso, 1)
    tope = max(int(horizon_bars), 1)
    limite_ms = tope * paso

    por_familia: dict[str, list[CalendarEvent]] = {}
    for e in events:
        por_familia.setdefault(e.key, []).append(e)

    salida: dict[str, np.ndarray] = {}
    for clave, grupo in sorted(por_familia.items()):
        fam = clave.lower()
        sched = np.array([g.scheduled_at for g in grupo], dtype=np.int64)
        ann = np.array([g.announced_at for g in grupo], dtype=np.int64)

        falta = _visible_next(t, sched, ann).astype(float)
        desde = _last_seen(t, sched).astype(float)

        salida[f"cal_{fam}_to_next"] = np.clip(falta / limite_ms, 0.0, 1.0)
        salida[f"cal_{fam}_since"] = np.clip(desde / limite_ms, 0.0, 1.0)
        salida[f"cal_{fam}_active"] = (
            desde <= max(int(active_bars), 0) * paso).astype(float)
    return salida


CALENDAR_GROUP_NOTE = (
    "Instantes de eventos programados. Es la ÚNICA familia de variables exógenas "
    "que se puede mirar hacia delante sin cometer lookahead, porque la fecha se "
    "publica con antelación — y justo por eso es la más fácil de contaminar: solo "
    "entran eventos cuyo anuncio es anterior a la vela, y nunca el contenido del "
    "evento, que no existe hasta que ocurre."
)


def self_note() -> str:
    """Lo que este calendario no es."""
    return (
        "Este calendario da INSTANTES, no contenido. Sabe cuándo se publica la "
        "nómina no agrícola; no sabe el dato ni la sorpresa frente al consenso, y "
        "esa distinción es la que separa una feature legítima de un lookahead: la "
        "hora está programada y se puede usar antes, el dato no existe hasta que "
        "sale.\n"
        "Las familias derivadas son de cripto y de infraestructura —liquidaciones "
        "de financiación, vencimientos, cierres de periodo—, más la nómina no "
        "agrícola y los halvings ocurridos. El resto del calendario macro exige "
        "ingestión externa y su ausencia está declarada en `UNDERIVABLE`, no "
        "rellenada con estimaciones.\n"
        "Y un recuento alto no es potencia por sí solo: las liquidaciones de "
        "financiación son más de mil al año pero caen siempre a la misma hora, así "
        "que cualquier efecto de hora del día se confundiría con el evento si el "
        "nulo no conserva esa estructura horaria."
    )
