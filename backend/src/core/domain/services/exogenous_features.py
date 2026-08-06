"""
exogenous_features.py — Variables que NO salen del gráfico, con disciplina point-in-time.

Por qué existe este módulo
──────────────────────────
Las 17 features del modelo predictivo son todas transformaciones de OHLCV: RSI,
MACD, Bollinger, ADX, estocástico, retornos y volatilidad. Ese es el espacio de
variables más minado del planeta — lo llevan explotando todas las mesas y todo
el retail desde hace quince años. El edge esperado *a priori* de un clasificador
sobre esas variables en cripto líquido es indistinguible de cero, y ninguna
cantidad de rigor metodológico lo va a crear. El rigor solo puede REVELAR que no
está.

Mientras tanto, la plataforma lleva meses recogiendo funding de perpetuos,
movimientos de ballenas, presión on-chain y métricas de cadena — y ninguna de
esas variables entraba en el modelo. Este módulo es el puente.

La regla que lo gobierna: **as-of hacia atrás, nunca hacia delante**
───────────────────────────────────────────────────────────────────
Para cada vela `t`, el valor de una variable exógena es **el último publicado en
un instante ≤ t**. Ni el siguiente, ni una interpolación entre ambos, ni la
media de la ventana centrada. Cualquiera de esas tres cosas mete en la fila `t`
información que no existía al cerrar esa vela, y el resultado es un modelo que
parece brillante y no se puede operar.

Es la fuga más fácil de cometer y la más difícil de ver: un `fillna(method=
"bfill")` puesto por comodidad basta para arruinar un estudio entero sin que
nada falle.

La antigüedad máxima, que es una decisión y no un detalle
────────────────────────────────────────────────────────
Propagar indefinidamente el último valor conocido es técnicamente point-in-time
—era lo que sabías— pero informativamente es basura: un funding de hace cuarenta
días no describe el mercado de hoy. Cada grupo declara su `max_staleness`, y más
allá el valor pasa a NaN.

Es una decisión con coste: recorta muestras. La alternativa —propagar sin
límite— no recorta nada y a cambio mete ruido con aspecto de dato, que el
estudio de importancia interpretaría como señal débil en lugar de como ausencia.

Capa de dominio: Python puro (numpy/pandas). La carga desde base de datos vive
en `application/use_cases/feature_store.py` — aquí no entra Django, para que
estos tests corran sin BD y la lógica de alineación temporal se pueda auditar
sola.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Sufijo de las columnas que declaran si un grupo de features tiene dato.
#
# Un NaN puede significar dos cosas muy distintas —«esta fuente no existe para
# este activo» y «existe pero aquí no había dato»— y el modelo no puede
# distinguirlas. La bandera lo hace explícito, y permite que el estudio de
# importancia informe sobre cuántas filas tenían realmente cada bloque en vez de
# imputar en silencio.
AVAILABLE_SUFFIX = "_available"


@dataclass(frozen=True)
class ExogenousGroup:
    """Un bloque de variables exógenas con su procedencia y su caducidad."""
    name: str
    columns: tuple[str, ...]
    max_staleness_ms: int
    source: str
    note: str


# Ocho horas: el funding de un perpetuo se liquida tres veces al día, así que
# entre liquidaciones el último valor conocido SÍ es el vigente. Se da un margen
# de una liquidación extra (16 h) por si una ingesta se retrasa.
_H = 3_600_000
FUNDING = ExogenousGroup(
    name="funding",
    columns=("funding_rate", "funding_z30", "funding_cum_3d"),
    max_staleness_ms=16 * _H,
    source="FundingRateRecord",
    note=("Tasa de financiación del perpetuo. Es la única variable exógena de "
          "esta lista que mide POSICIONAMIENTO en vez de precio: dice quién "
          "está pagando a quién por mantener la postura, no qué ha hecho la "
          "cotización."),
)

WHALE_FLOW = ExogenousGroup(
    name="whale_flow",
    columns=("whale_netflow_usd", "whale_tx_count", "whale_netflow_z"),
    max_staleness_ms=6 * _H,
    source="WhaleMovementSnapshot",
    note=("Flujo neto de grandes movimientos hacia/desde exchanges en la ventana "
          "previa. Salidas netas de exchange se leen como acumulación; entradas "
          "netas, como intención de venta."),
)

CHAIN_HEALTH = ExogenousGroup(
    name="chain_health",
    columns=("chain_metric_z", "chain_metric_pct"),
    max_staleness_ms=12 * _H,
    source="ChainMetricPoint",
    note=("Estado de la cadena subyacente (gas, utilización, hashrate) "
          "normalizado contra su propia historia."),
)

GROUPS: tuple[ExogenousGroup, ...] = (FUNDING, WHALE_FLOW, CHAIN_HEALTH)


# ═══════════════════════════════════════════════════════════════════
# Fuentes SIN historia persistida
# ═══════════════════════════════════════════════════════════════════
#
# El informe de auditoría da por hecho que la plataforma «ya posee» open
# interest, ratio long/short, taker buy/sell y profundidad de order book. Las
# sabe LEER —hay clientes y endpoints que las consultan— pero no guarda su
# historia: son llamadas en vivo que devuelven la foto de ahora.
#
# Sin historia no hay feature point-in-time, y las dos salidas fáciles son
# ambas inaceptables:
#
#   · Propagar hacia atrás el valor de hoy sobre todo el histórico. Es lookahead
#     del peor tipo: el modelo «predice» el pasado sabiendo el presente.
#   · Crear la columna llena de NaN y no decir nada. El estudio de importancia
#     la descartaría en silencio y el resultado se leería como «esta variable no
#     aporta», cuando lo cierto es «esta variable no se ha medido».
#
# Se declaran aquí para que la ausencia sea un hecho documentado y no un hueco.
# Convertirlas en features exige antes persistir su serie, igual que se hizo con
# el funding.
MISSING_HISTORY: dict[str, str] = {
    "open_interest": "Se consulta en vivo; no hay modelo que guarde su serie.",
    "long_short_ratio": "Se consulta en vivo; no hay modelo que guarde su serie.",
    "taker_buy_sell": "Se consulta en vivo; no hay modelo que guarde su serie.",
    "orderbook_depth": "Se consulta en vivo; el libro no se archiva.",
}


def as_of(timestamps, event_times, values, max_staleness_ms: int) -> np.ndarray:
    """
    Último valor conocido en cada instante, con caducidad.

    Para cada `t` de `timestamps` devuelve el `values[i]` cuyo `event_times[i]`
    es el mayor que cumple `event_times[i] <= t`. Si ese valor es más antiguo
    que `max_staleness_ms`, devuelve NaN.

    El `<=` no es un detalle de estilo. Con `<` se perdería el dato publicado
    exactamente al cierre de la vela —el caso más frecuente cuando las dos
    series comparten rejilla— y con `<` invertido (`>=`) se estaría leyendo el
    futuro. La frontera es donde vive la fuga.

    Implementado con búsqueda binaria sobre los eventos ordenados: recorrer
    linealmente sería O(n·m) y este join se hace sobre miles de velas.
    """
    ts = np.asarray(timestamps, dtype=np.int64)
    if len(event_times) == 0:
        return np.full(len(ts), np.nan)

    ev = np.asarray(event_times, dtype=np.int64)
    vals = np.asarray(values, dtype=float)
    order = np.argsort(ev, kind="stable")
    ev, vals = ev[order], vals[order]

    # `side="right"` sitúa el índice DESPUÉS de los eventos iguales a t, así que
    # `idx - 1` es el último con event_time <= t. Ahí está el `<=`.
    idx = np.searchsorted(ev, ts, side="right") - 1
    out = np.full(len(ts), np.nan)
    valid = idx >= 0
    if not valid.any():
        return out

    picked = idx[valid]
    age = ts[valid] - ev[picked]
    fresh = age <= max_staleness_ms
    out[np.where(valid)[0][fresh]] = vals[picked][fresh]
    return out


def rolling_z(series, window: int, min_periods: int | None = None) -> np.ndarray:
    """
    Z-score contra la propia historia PASADA de la serie.

    `closed="left"` excluye el valor actual de su propia ventana de referencia.
    Sin eso, el punto se estaría normalizando contra un estadístico que él mismo
    ha ayudado a formar — un sesgo pequeño con series largas y grande con
    ventanas cortas, y en cualquier caso información que en `t` no se tenía.
    """
    s = pd.Series(np.asarray(series, dtype=float))
    roll = s.rolling(window, min_periods=min_periods or max(3, window // 4), closed="left")
    mu, sd = roll.mean(), roll.std(ddof=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (s - mu) / sd
    return z.replace([np.inf, -np.inf], np.nan).to_numpy()


def windowed_sum(timestamps, event_times, values, window_ms: int) -> np.ndarray:
    """
    Suma de los eventos ocurridos en `(t − window, t]`, para cada `t`.

    Es la forma correcta de convertir un flujo de sucesos discretos —una
    transferencia de ballena, una liquidación— en una serie alineada a velas.
    Tomar «el último suceso» no serviría: lo que informa no es el evento suelto
    sino cuánto se ha movido en la ventana reciente.

    El intervalo es abierto por la izquierda y CERRADO por la derecha: un
    movimiento ocurrido exactamente al cierre de la vela ya se conocía.
    """
    ts = np.asarray(timestamps, dtype=np.int64)
    if len(event_times) == 0:
        return np.zeros(len(ts))

    ev = np.asarray(event_times, dtype=np.int64)
    vals = np.asarray(values, dtype=float)
    order = np.argsort(ev, kind="stable")
    ev, vals = ev[order], vals[order]

    cumulative = np.concatenate([[0.0], np.cumsum(vals)])
    hi = np.searchsorted(ev, ts, side="right")
    lo = np.searchsorted(ev, ts - window_ms, side="right")
    return cumulative[hi] - cumulative[lo]


def funding_features(timestamps, records) -> dict[str, np.ndarray]:
    """
    Bloque de funding: nivel, anomalía y coste acumulado.

    Las tres columnas dicen cosas distintas a propósito:

      · `funding_rate` — el nivel vigente. Positivo significa que los largos
        pagan, o sea que el posicionamiento está cargado al alza.
      · `funding_z30` — cuánto se desvía ese nivel de su propia normalidad
        reciente. Un funding de 3 bp es alto en un mercado tranquilo y bajo en
        uno eufórico; el nivel a secas no lo distingue.
      · `funding_cum_3d` — lo que ha costado mantener la postura en tres días.
        Es la variable que captura presión SOSTENIDA, que no es lo mismo que un
        pico puntual.

    `records` es una lista de `(funding_time_ms, funding_rate)`.
    """
    ts = np.asarray(timestamps, dtype=np.int64)
    if not records:
        return {
            "funding_rate": np.full(len(ts), np.nan),
            "funding_z30": np.full(len(ts), np.nan),
            "funding_cum_3d": np.full(len(ts), np.nan),
            f"funding{AVAILABLE_SUFFIX}": np.zeros(len(ts)),
        }

    times = np.array([r[0] for r in records], dtype=np.int64)
    rates = np.array([r[1] for r in records], dtype=float)

    rate = as_of(ts, times, rates, FUNDING.max_staleness_ms)
    # El z-score se calcula sobre la serie ALINEADA A VELAS, no sobre las
    # liquidaciones: así la ventana significa lo mismo en cualquier marco
    # temporal y el valor de la fila `t` solo mira a filas anteriores.
    z = rolling_z(rate, window=90)
    cum = windowed_sum(ts, times, rates, window_ms=3 * 24 * _H)
    return {
        "funding_rate": rate,
        "funding_z30": z,
        "funding_cum_3d": np.where(np.isnan(rate), np.nan, cum),
        f"funding{AVAILABLE_SUFFIX}": (~np.isnan(rate)).astype(float),
    }


def whale_flow_features(timestamps, movements) -> dict[str, np.ndarray]:
    """
    Bloque de flujo de ballenas: cuánto dinero grande entró o salió de exchanges.

    `movements` es una lista de `(moved_at_ms, signed_usd)`, con el signo ya
    resuelto por quien carga: **positivo = salida de exchange** (acumulación),
    negativo = entrada (intención de venta). Que el signo venga resuelto de
    fuera es deliberado — la clasificación de una dirección depende de etiquetas
    de direcciones que son infraestructura, no dominio.
    """
    ts = np.asarray(timestamps, dtype=np.int64)
    window = 24 * _H
    if not movements:
        return {
            "whale_netflow_usd": np.full(len(ts), np.nan),
            "whale_tx_count": np.full(len(ts), np.nan),
            "whale_netflow_z": np.full(len(ts), np.nan),
            f"whale_flow{AVAILABLE_SUFFIX}": np.zeros(len(ts)),
        }

    times = np.array([m[0] for m in movements], dtype=np.int64)
    usd = np.array([m[1] for m in movements], dtype=float)

    netflow = windowed_sum(ts, times, usd, window)
    count = windowed_sum(ts, times, np.ones_like(usd), window)
    # Un flujo neto solo es interpretable contra la escala habitual del activo:
    # 10 M$ es enorme en un token pequeño e irrelevante en bitcoin.
    z = rolling_z(netflow, window=90)

    # Antes del primer movimiento registrado no hay dato, y un cero ahí diría
    # «no hubo flujo» cuando lo cierto es «no se estaba observando».
    before = ts < times.min()
    for arr in (netflow, count, z):
        arr[before] = np.nan
    return {
        "whale_netflow_usd": netflow,
        "whale_tx_count": count,
        "whale_netflow_z": z,
        f"whale_flow{AVAILABLE_SUFFIX}": (~before).astype(float),
    }


def chain_health_features(timestamps, points) -> dict[str, np.ndarray]:
    """
    Bloque de salud de cadena, normalizado contra su propia historia.

    El valor bruto de una métrica de cadena no es comparable entre cadenas ni
    entre épocas —12 Gwei era caro en 2021 y barato hoy—, así que lo que entra
    en el modelo es la desviación respecto a su propia normalidad y su
    percentil, no la magnitud.

    `points` es una lista de `(ts_ms, value)` de UNA métrica.
    """
    ts = np.asarray(timestamps, dtype=np.int64)
    if not points:
        return {
            "chain_metric_z": np.full(len(ts), np.nan),
            "chain_metric_pct": np.full(len(ts), np.nan),
            f"chain_health{AVAILABLE_SUFFIX}": np.zeros(len(ts)),
        }

    times = np.array([p[0] for p in points], dtype=np.int64)
    vals = np.array([p[1] for p in points], dtype=float)
    level = as_of(ts, times, vals, CHAIN_HEALTH.max_staleness_ms)
    z = rolling_z(level, window=90)
    pct = (pd.Series(level).rolling(180, min_periods=30, closed="left")
           .apply(lambda w: float((w < w[-1]).mean()) if len(w) else np.nan, raw=True)
           .to_numpy())
    return {
        "chain_metric_z": z,
        "chain_metric_pct": pct,
        f"chain_health{AVAILABLE_SUFFIX}": (~np.isnan(level)).astype(float),
    }


def assemble(timestamps, funding=None, whale=None, chain=None) -> pd.DataFrame:
    """
    Ensambla los bloques disponibles en un DataFrame alineado a las velas.

    Los bloques que no reciben datos siguen apareciendo, con NaN y su bandera a
    cero. Omitirlos cambiaría el número de columnas según el activo, y entonces
    dos estudios no serían comparables entre sí.
    """
    ts = np.asarray(timestamps, dtype=np.int64)
    out: dict[str, np.ndarray] = {}
    out.update(funding_features(ts, funding or []))
    out.update(whale_flow_features(ts, whale or []))
    out.update(chain_health_features(ts, chain or []))
    return pd.DataFrame(out)


def coverage(frame: pd.DataFrame) -> dict:
    """
    Qué fracción de las filas tiene realmente cada bloque.

    Es lo que separa «esta variable no aporta» de «esta variable no se ha
    medido», y sin ello un estudio de importancia confunde las dos.
    """
    rows = len(frame)
    groups = {}
    for group in GROUPS:
        flag = f"{group.name}{AVAILABLE_SUFFIX}"
        available = float(frame[flag].mean()) if flag in frame and rows else 0.0
        groups[group.name] = {
            "coverage_pct": round(available * 100, 1),
            "columns": list(group.columns),
            "source": group.source,
            "usable": available > 0.5,
            "note": group.note,
        }
    usable = [g for g, s in groups.items() if s["usable"]]
    return {
        "rows": rows,
        "groups": groups,
        "usable_groups": usable,
        "missing_history": dict(MISSING_HISTORY),
        "note": (
            f"{len(usable)} de {len(GROUPS)} bloques exógenos tienen cobertura "
            f"suficiente. Las fuentes de `missing_history` se consultan en vivo "
            "pero no archivan su serie: sin historia no hay feature "
            "point-in-time, y rellenarla con el valor de hoy sería lookahead."
        ),
    }
