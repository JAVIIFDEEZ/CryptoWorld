"""
strategy_spec.py — Representación componible de estrategias (Módulo 0).

Una estrategia es un StrategySpec: bloques de condiciones de entrada y de
salida sobre el catálogo de indicadores (osciladores: RSI, StochRSI, Stoch,
CCI, Williams %R, ADX, MFI, CMF, ROC, ATR%, Aroon, TRIX, ratio de volumen;
series de precio: SMA/EMA/WMA/Hull/KAMA, Bollinger, MACD, Ichimoku, PSAR,
canales Donchian/Keltner y retrocesos de Fibonacci) con CINCO tipos de
condición al estilo de los generadores profesionales (StrategyQuant y afines):
umbral, cruce, estado (A por encima/debajo de B), pendiente (al alza/baja en
n velas) y **patrón de acción del precio**.

El quinto tipo existe porque los otros cuatro describen el mercado con NIVELES,
y hay información que no es un nivel sino un suceso con estructura: una vela que
se traga a la anterior, un mínimo perforado que se recupera, un hueco sin
negociar entre dos velas. Ese vocabulario vive en `price_patterns` (velas
japonesas, FVG, order blocks, barridas de liquidez, CRT, AMD/Power of Three,
ORB y zonas de Fibonacci) y sin él el generador no puede descubrir esas
estrategias por mucho que evolucione — no están en su idioma.

El compilador traduce un spec a un array de señales (1/-1/0) que el
motor de backtest existente (backtest_signals) puede ejecutar — de modo que el
generador genético produce estrategias NUEVAS sin tocar el motor ni la
matemática de robustez.

Esquema de un spec (JSON-serializable, así se persiste tal cual):
    {
      "entry": {"combine": "AND"|"OR", "conditions": [cond, ...]},  # 1-3
      "exit":  {"combine": "AND"|"OR", "conditions": [cond, ...]},  # 1-3
    }
Condición de umbral (oscilador op valor):
    {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
     "op": "lt"|"gt", "threshold": 30}
Condición de cruce (dos indicadores tipo precio):
    {"type": "cross",
     "a": {"indicator": "EMA", "params": {"window": 12}},
     "b": {"indicator": "EMA", "params": {"window": 26}},
     "op": "cross_above"|"cross_below"}
Condición de patrón (suceso de acción del precio, con ventana de vigencia):
    {"type": "pattern", "pattern": "SWEEP_LOW", "params": {"window": 20},
     "lookback": 4}   # «ocurrió en alguna de las últimas 4 velas»

Capa de dominio: Python puro, sin BD ni framework.
"""

import copy as copy_module
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
import ta as ta_lib

from core.domain.services import price_patterns

# ═══════════════════════════════════════════════════════════════════
# Catálogo de indicadores (espacio de búsqueda)
# ═══════════════════════════════════════════════════════════════════

# Cada parámetro: (tipo, low, high). Los osciladores añaden su rango de umbral.

def _rsi(df, p):
    return ta_lib.momentum.RSIIndicator(df["close"], window=int(p["window"])).rsi().values

def _stochrsi(df, p):
    return (ta_lib.momentum.StochRSIIndicator(df["close"], window=int(p["window"])).stochrsi() * 100).values

def _cci(df, p):
    return ta_lib.trend.CCIIndicator(df["high"], df["low"], df["close"], window=int(p["window"])).cci().values

def _willr(df, p):
    return ta_lib.momentum.WilliamsRIndicator(df["high"], df["low"], df["close"], lbp=int(p["window"])).williams_r().values

def _adx(df, p):
    return ta_lib.trend.ADXIndicator(df["high"], df["low"], df["close"], window=int(p["window"])).adx().values

def _price(df, p):
    return df["close"].values

def _sma(df, p):
    return ta_lib.trend.SMAIndicator(df["close"], window=int(p["window"])).sma_indicator().values

def _ema(df, p):
    return ta_lib.trend.EMAIndicator(df["close"], window=int(p["window"])).ema_indicator().values

def _bb_upper(df, p):
    return ta_lib.volatility.BollingerBands(df["close"], window=int(p["window"]), window_dev=float(p["dev"])).bollinger_hband().values

def _bb_lower(df, p):
    return ta_lib.volatility.BollingerBands(df["close"], window=int(p["window"]), window_dev=float(p["dev"])).bollinger_lband().values

def _macd_line(df, p):
    return ta_lib.trend.MACD(df["close"], window_slow=int(p["slow"]), window_fast=int(p["fast"]), window_sign=int(p["signal"])).macd().values

def _macd_signal(df, p):
    return ta_lib.trend.MACD(df["close"], window_slow=int(p["slow"]), window_fast=int(p["fast"]), window_sign=int(p["signal"])).macd_signal().values

def _mfi(df, p):
    # Money Flow Index: RSI ponderado por volumen (0-100). Filtro de momentum con volumen.
    return ta_lib.volume.MFIIndicator(df["high"], df["low"], df["close"], df["volume"], window=int(p["window"])).money_flow_index().values

def _cmf(df, p):
    # Chaikin Money Flow (-1..1): presión compradora/vendedora ponderada por volumen.
    return ta_lib.volume.ChaikinMoneyFlowIndicator(df["high"], df["low"], df["close"], df["volume"], window=int(p["window"])).chaikin_money_flow().values

def _vol_ratio(df, p):
    # Volumen relativo a su media móvil: >1 = más actividad de lo normal (surge).
    vol = df["volume"].astype(float)
    sma = vol.rolling(int(p["window"])).mean()
    return (vol / sma.replace(0, np.nan)).values

def _stoch(df, p):
    return ta_lib.momentum.StochasticOscillator(df["high"], df["low"], df["close"], window=int(p["window"])).stoch().values

def _roc(df, p):
    # Rate of Change (%): momentum puro a n velas.
    return ta_lib.momentum.ROCIndicator(df["close"], window=int(p["window"])).roc().values

def _atr_pct(df, p):
    # ATR normalizado por el precio (%): filtro de volatilidad comparable entre activos.
    atr = ta_lib.volatility.AverageTrueRange(df["high"], df["low"], df["close"], window=int(p["window"])).average_true_range()
    return (atr / df["close"] * 100.0).values

def _aroon_osc(df, p):
    # Oscilador de Aroon (-100..100): fuerza y dirección de la tendencia reciente.
    return ta_lib.trend.AroonIndicator(high=df["high"], low=df["low"], window=int(p["window"])).aroon_indicator().values

def _trix(df, p):
    # TRIX (%): pendiente de una EMA triple — momentum suavizado con poco ruido.
    return ta_lib.trend.TRIXIndicator(df["close"], window=int(p["window"])).trix().values

def _wma(df, p):
    return ta_lib.trend.WMAIndicator(df["close"], window=int(p["window"])).wma().values

def _hma(df, p):
    # Hull MA: WMA(2·WMA(n/2) − WMA(n), √n) — media rápida con poco retardo.
    n = int(p["window"])
    half = max(2, n // 2)
    sqrt_n = max(2, int(round(math.sqrt(n))))
    wma_half = ta_lib.trend.WMAIndicator(df["close"], window=half).wma()
    wma_full = ta_lib.trend.WMAIndicator(df["close"], window=n).wma()
    raw = 2.0 * wma_half - wma_full
    return ta_lib.trend.WMAIndicator(raw, window=sqrt_n).wma().values

def _kama(df, p):
    # Kaufman Adaptive MA: rápida en tendencia, lenta en rango.
    return ta_lib.momentum.KAMAIndicator(df["close"], window=int(p["window"])).kama().values

def _ichi_conv(df, p):
    # Línea de conversión Ichimoku (tenkan-sen): (max+min)/2 de w velas.
    return ta_lib.trend.IchimokuIndicator(df["high"], df["low"], window1=int(p["window"]), window2=26).ichimoku_conversion_line().values

def _ichi_base(df, p):
    # Línea base Ichimoku (kijun-sen): (max+min)/2 de w velas (más lenta).
    return ta_lib.trend.IchimokuIndicator(df["high"], df["low"], window1=9, window2=int(p["window"])).ichimoku_base_line().values

def _psar(df, p):
    # Parabolic SAR: nivel de stop-and-reverse que sigue a la tendencia.
    # PSARIndicator de `ta` corrompe la longitud con índices no reseteados
    # (los tramos del walk-forward llegan como slices): índice limpio SIEMPRE.
    high = df["high"].reset_index(drop=True)
    low = df["low"].reset_index(drop=True)
    close = df["close"].reset_index(drop=True)
    return ta_lib.trend.PSARIndicator(high, low, close, step=float(p["step"]), max_step=float(p["max_step"])).psar().values

def _shift1(arr: np.ndarray) -> np.ndarray:
    """Serie desplazada 1 vela: canales construidos con máx/mín que INCLUYEN la
    vela actual no pueden 'cruzarse' con el cierre de esa misma vela; comparar
    contra el canal de la vela anterior sí define una ruptura real (y causal)."""
    out = np.empty_like(arr)
    out[0] = np.nan
    out[1:] = arr[:-1]
    return out

def _donch_upper(df, p):
    return _shift1(ta_lib.volatility.DonchianChannel(df["high"], df["low"], df["close"], window=int(p["window"])).donchian_channel_hband().values)

def _donch_lower(df, p):
    return _shift1(ta_lib.volatility.DonchianChannel(df["high"], df["low"], df["close"], window=int(p["window"])).donchian_channel_lband().values)

def _kelt_upper(df, p):
    return ta_lib.volatility.KeltnerChannel(df["high"], df["low"], df["close"], window=int(p["window"])).keltner_channel_hband().values

def _kelt_lower(df, p):
    return ta_lib.volatility.KeltnerChannel(df["high"], df["low"], df["close"], window=int(p["window"])).keltner_channel_lband().values

def _fib_retr(df, p):
    # Retroceso de Fibonacci sobre el swing de las últimas `window` velas:
    # nivel = máximo − ratio·(máximo − mínimo). Con ratio 0.382/0.5/0.618 cubre
    # los niveles clásicos; desplazado 1 vela para que la ruptura sea causal.
    w = int(p["window"])
    hi = df["high"].rolling(w).max()
    lo = df["low"].rolling(w).min()
    level = hi - float(p["ratio"]) * (hi - lo)
    return _shift1(level.values)


# Osciladores: se comparan contra un umbral numérico.
OSCILLATORS: dict[str, dict] = {
    "RSI": {"compute": _rsi, "params": {"window": ("int", 7, 21)}, "threshold": (15.0, 85.0)},
    "STOCHRSI": {"compute": _stochrsi, "params": {"window": ("int", 7, 21)}, "threshold": (10.0, 90.0)},
    "CCI": {"compute": _cci, "params": {"window": ("int", 14, 30)}, "threshold": (-150.0, 150.0)},
    "WILLR": {"compute": _willr, "params": {"window": ("int", 10, 21)}, "threshold": (-90.0, -10.0)},
    "ADX": {"compute": _adx, "params": {"window": ("int", 10, 30)}, "threshold": (15.0, 40.0)},
    # Indicadores con volumen: filtros de actividad y de presión compradora/vendedora.
    "MFI": {"compute": _mfi, "params": {"window": ("int", 10, 21)}, "threshold": (15.0, 85.0)},
    "CMF": {"compute": _cmf, "params": {"window": ("int", 14, 30)}, "threshold": (-0.3, 0.3)},
    "VOLRATIO": {"compute": _vol_ratio, "params": {"window": ("int", 10, 30)}, "threshold": (0.7, 2.5)},
    # Momentum y régimen clásicos (estilo StrategyQuant).
    "STOCH": {"compute": _stoch, "params": {"window": ("int", 10, 21)}, "threshold": (10.0, 90.0)},
    "ROC": {"compute": _roc, "params": {"window": ("int", 5, 30)}, "threshold": (-10.0, 10.0)},
    "ATR_PCT": {"compute": _atr_pct, "params": {"window": ("int", 7, 30)}, "threshold": (0.5, 8.0)},
    "AROON": {"compute": _aroon_osc, "params": {"window": ("int", 14, 30)}, "threshold": (-80.0, 80.0)},
    "TRIX": {"compute": _trix, "params": {"window": ("int", 9, 20)}, "threshold": (-0.3, 0.3)},
}

# Tipo precio: se cruzan entre sí (o contra el precio) y se comparan como estado.
PRICE_LIKE: dict[str, dict] = {
    "PRICE": {"compute": _price, "params": {}},
    "SMA": {"compute": _sma, "params": {"window": ("int", 5, 200)}},
    "EMA": {"compute": _ema, "params": {"window": ("int", 5, 200)}},
    "WMA": {"compute": _wma, "params": {"window": ("int", 5, 100)}},
    "HMA": {"compute": _hma, "params": {"window": ("int", 8, 80)}},
    "KAMA": {"compute": _kama, "params": {"window": ("int", 8, 30)}},
    "BB_UPPER": {"compute": _bb_upper, "params": {"window": ("int", 10, 40), "dev": ("float", 1.5, 3.0)}},
    "BB_LOWER": {"compute": _bb_lower, "params": {"window": ("int", 10, 40), "dev": ("float", 1.5, 3.0)}},
    "MACD_LINE": {"compute": _macd_line, "params": {"fast": ("int", 8, 16), "slow": ("int", 20, 34), "signal": ("int", 6, 12)}},
    "MACD_SIGNAL": {"compute": _macd_signal, "params": {"fast": ("int", 8, 16), "slow": ("int", 20, 34), "signal": ("int", 6, 12)}},
    # Canales y niveles (rupturas y soportes dinámicos).
    "ICHI_CONV": {"compute": _ichi_conv, "params": {"window": ("int", 7, 12)}},
    "ICHI_BASE": {"compute": _ichi_base, "params": {"window": ("int", 20, 34)}},
    "PSAR": {"compute": _psar, "params": {"step": ("float", 0.01, 0.05), "max_step": ("float", 0.1, 0.3)}},
    "DONCH_UPPER": {"compute": _donch_upper, "params": {"window": ("int", 10, 60)}},
    "DONCH_LOWER": {"compute": _donch_lower, "params": {"window": ("int", 10, 60)}},
    "KELT_UPPER": {"compute": _kelt_upper, "params": {"window": ("int", 10, 40)}},
    "KELT_LOWER": {"compute": _kelt_lower, "params": {"window": ("int", 10, 40)}},
    # Retroceso de Fibonacci del swing reciente (ratio 0.38–0.62 evolucionable,
    # cubre los niveles clásicos 0.382/0.5/0.618 con redondeo a 2 decimales).
    "FIB_RETR": {"compute": _fib_retr, "params": {"window": ("int", 30, 120), "ratio": ("float", 0.38, 0.62)}},
}

_ALL = {**OSCILLATORS, **PRICE_LIKE}

# ── Acción del precio: sucesos con estructura, no niveles ──────────
# Los indicadores describen el mercado con NÚMEROS que se comparan contra
# umbrales. Hay información que ese vocabulario no puede expresar porque no es
# un nivel sino un suceso: que una vela se trague a la anterior, que el precio
# perfore un mínimo y vuelva dentro, que quede un hueco sin negociar. Un
# generador que solo combina osciladores no puede descubrir esas estrategias por
# mucho que evolucione — no están en su idioma. `price_patterns` las añade y la
# condición `pattern` las conecta con la gramática.
PATTERNS = price_patterns.PATTERNS

# Ventana de vigencia del patrón. Sin ella, combinar dos patrones con Y sería
# casi siempre falso —son sucesos puntuales y no coinciden en la misma vela— y
# el generador nunca podría expresar secuencias como «hubo barrida y ahora
# envolvente», que es como se usan de verdad.
PATTERN_LOOKBACK_RANGE = (1, 8)

THRESHOLD_OPS = ("gt", "lt")
CROSS_OPS = ("cross_above", "cross_below")
COMPARE_OPS = ("above", "below")   # estado persistente: A por encima/debajo de B
SLOPE_OPS = ("rising", "falling")  # pendiente: la serie sube/baja vs hace n velas
SLOPE_BARS_RANGE = (2, 10)
COMBINES = ("AND", "OR", "K_OF_N")

# ── Dirección de la estrategia ────────────────────────────────────
# Qué lado del mercado abren los bloques del spec:
#
#   · "long"  — `entry`/`exit` abren y cierran LARGOS. Es el comportamiento
#     histórico y el valor por defecto: un spec guardado sin este campo se lee
#     como largo, así que nada de lo ya validado cambia de significado.
#   · "short" — los MISMOS bloques abren y cierran CORTOS. No hay bloques
#     muertos: la estrategia es una y opera al otro lado.
#   · "both"  — `entry`/`exit` para largos y `short_entry`/`short_exit` para
#     cortos, evolucionados POR SEPARADO.
#
# Lo de «por separado» no es un capricho de diseño. Una reversión a la media al
# alza no es la misma estrategia que a la baja, y en cripto la asimetría es
# fuerte: las subidas son lentas y las caídas violentas. Un lado corto obtenido
# por espejo del largo heredaría umbrales calibrados para una dinámica que no es
# la suya, y lo haría en silencio.
DIRECTIONS = ("long", "short", "both")
DEFAULT_DIRECTION = "long"

# Lo que una EJECUCIÓN del generador permite explorar. Los tres primeros fijan
# la dirección de toda la población; "auto" la deja evolucionar como un gen más.
DIRECTION_MODES = DIRECTIONS + ("auto",)

# Reparto de la población inicial en modo "auto".
#
# Largo y corto pesan lo mismo a propósito: el motor no tiene opinión sobre
# hacia dónde va el mercado, y meter una preferencia direccional en la semilla
# sería exactamente eso disfrazado de configuración.
#
# "both" pesa menos, y no por desconfianza en operar los dos lados: un spec
# "both" lleva el DOBLE de bloques, o sea el doble de grados de libertad sobre
# el mismo histórico. Es la familia más fácil de sobreajustar, así que entra en
# la población con menos representación y tiene que ganarse el sitio en el
# fitness, no en el sorteo inicial.
AUTO_DIRECTION_WEIGHTS = {"long": 0.375, "short": 0.375, "both": 0.25}

# Tipos de condición que admiten negación.
#
# `cross` queda fuera a propósito: un cruce es un SUCESO puntual, y su
# complemento («no hubo cruce en esta vela») es cierto el 99 % del tiempo. Sería
# una condición siempre verdadera disfrazada, que al entrar en un Y reduce en
# silencio un bloque de tres condiciones a uno de dos. Los demás tipos describen
# ESTADOS, y su negación es tan informativa como su afirmación: «el precio NO
# está en zona de premium» no se puede expresar hoy de ninguna otra forma.
NEGATABLE = ("threshold", "compare", "slope", "pattern")

# Los patrones también son sucesos: solo se admite negarlos con una ventana de
# vigencia suficiente, donde «no ha habido barrida en las últimas N velas» pasa
# a describir un régimen tranquilo en vez del complemento trivial de un suceso.
MIN_NEGATABLE_LOOKBACK = 3

_MAX_CONDITIONS = 3


def catalog_version() -> str:
    """
    Huella del espacio de búsqueda: bloques disponibles, sus rangos de
    parámetros y los operadores de condición.

    Un experimento solo es reproducible si se sabe sobre qué catálogo corrió.
    Añadir un indicador o mover el rango de una ventana cambia el espacio y
    hace que dos ejecuciones con la misma semilla dejen de ser comparables —
    esta huella lo delata en lugar de que pase inadvertido.

    Se deriva del contenido, no de un número que haya que acordarse de subir a
    mano: lo segundo se olvida siempre.
    """
    import hashlib
    import json

    blocks = {
        name: {
            "params": {p: [kind, lo, hi] for p, (kind, lo, hi) in meta.get("params", {}).items()},
            "threshold": list(meta["threshold"]) if "threshold" in meta else None,
        }
        for name, meta in sorted(_ALL.items())
    }
    # Los patrones son parte del espacio de búsqueda tanto como los
    # indicadores: añadir uno cambia lo que el generador puede descubrir, y dos
    # ejecuciones con la misma semilla dejan de ser comparables. Si no entrasen
    # en la huella, ese cambio pasaría inadvertido — que es justo lo que esta
    # función existe para impedir.
    patterns = {
        name: {p: [kind, lo, hi] for p, (kind, lo, hi) in meta.get("params", {}).items()}
        for name, meta in sorted(PATTERNS.items())
    }
    payload = {
        "blocks": blocks,
        "patterns": patterns,
        "ops": {
            "threshold": list(THRESHOLD_OPS), "cross": list(CROSS_OPS),
            "compare": list(COMPARE_OPS), "slope": list(SLOPE_OPS),
            "slope_bars": list(SLOPE_BARS_RANGE), "combines": list(COMBINES),
            "pattern_lookback": list(PATTERN_LOOKBACK_RANGE),
            "negatable": list(NEGATABLE),
            "min_negatable_lookback": MIN_NEGATABLE_LOOKBACK,
        },
        "max_conditions": _MAX_CONDITIONS,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{len(_ALL)}b{len(PATTERNS)}p-{digest[:12]}"


# ═══════════════════════════════════════════════════════════════════
# Muestreo de parámetros y condiciones
# ═══════════════════════════════════════════════════════════════════

def _sample_params(param_spec: dict, rng: np.random.Generator) -> dict:
    out = {}
    for name, (kind, lo, hi) in param_spec.items():
        if kind == "int":
            out[name] = int(rng.integers(lo, hi + 1))
        else:
            out[name] = round(float(rng.uniform(lo, hi)), 2)
    return out


def _random_threshold_condition(rng: np.random.Generator) -> dict:
    name = rng.choice(list(OSCILLATORS.keys()))
    osc = OSCILLATORS[name]
    lo, hi = osc["threshold"]
    return {
        "type": "threshold",
        "indicator": str(name),
        "params": _sample_params(osc["params"], rng),
        "op": str(rng.choice(THRESHOLD_OPS)),
        "threshold": round(float(rng.uniform(lo, hi)), 2),
    }


def _random_cross_condition(rng: np.random.Generator) -> dict:
    names = list(PRICE_LIKE.keys())
    a = str(rng.choice(names))
    b = str(rng.choice([x for x in names if x != a]))
    return {
        "type": "cross",
        "a": {"indicator": a, "params": _sample_params(PRICE_LIKE[a]["params"], rng)},
        "b": {"indicator": b, "params": _sample_params(PRICE_LIKE[b]["params"], rng)},
        "op": str(rng.choice(CROSS_OPS)),
    }


def _random_compare_condition(rng: np.random.Generator) -> dict:
    """Condición de ESTADO: A por encima/debajo de B mientras dure (no solo en el
    cruce). Permite filtros como «precio > SMA(200)» — el clásico filtro de
    tendencia de los generadores profesionales."""
    names = list(PRICE_LIKE.keys())
    a = str(rng.choice(names))
    b = str(rng.choice([x for x in names if x != a]))
    return {
        "type": "compare",
        "a": {"indicator": a, "params": _sample_params(PRICE_LIKE[a]["params"], rng)},
        "b": {"indicator": b, "params": _sample_params(PRICE_LIKE[b]["params"], rng)},
        "op": str(rng.choice(COMPARE_OPS)),
    }


def _random_slope_condition(rng: np.random.Generator) -> dict:
    """Condición de PENDIENTE: la serie sube/baja respecto a hace n velas
    (momentum estructural de cualquier indicador, no solo del precio)."""
    name = str(rng.choice(list(_ALL.keys())))
    lo, hi = SLOPE_BARS_RANGE
    return {
        "type": "slope",
        "indicator": name,
        "params": _sample_params(_ALL[name]["params"], rng),
        "op": str(rng.choice(SLOPE_OPS)),
        "bars": int(rng.integers(lo, hi + 1)),
    }


def _random_pattern_condition(rng: np.random.Generator) -> dict:
    """
    Condición de ACCIÓN DEL PRECIO: un suceso con estructura, no un nivel.

    Lleva `lookback` porque el patrón es puntual: sin ventana de vigencia,
    combinarlo con Y contra cualquier otra condición sería casi siempre falso, y
    el generador descartaría la familia entera por estéril en vez de por mala.
    """
    name = str(rng.choice(list(PATTERNS.keys())))
    lo, hi = PATTERN_LOOKBACK_RANGE
    return {
        "type": "pattern",
        "pattern": name,
        "params": _sample_params(PATTERNS[name]["params"], rng),
        "lookback": int(rng.integers(lo, hi + 1)),
    }


def _can_negate(c: dict) -> bool:
    """¿Tiene esta condición un estado «off» informativo? (ver `NEGATABLE`)."""
    if c["type"] not in NEGATABLE:
        return False
    if c["type"] == "pattern":
        return int(c.get("lookback", 1)) >= MIN_NEGATABLE_LOOKBACK
    return True


def random_condition(rng: np.random.Generator) -> dict:
    """
    Condición aleatoria legal. Mezcla de los 5 tipos con pesos que favorecen los
    más expresivos (umbral y estado) sin abandonar cruces, pendientes ni acción
    del precio.

    Los patrones se llevan un 20 %: suficiente para que la familia aparezca en
    la población inicial y el GA pueda evaluarla, sin inundar la búsqueda con
    sucesos raros que casi nunca disparan. Que sea el gating quien decida si
    aportan, no una cuota que se la conceda de antemano.
    """
    roll = rng.random()
    if roll < 0.28:
        cond = _random_threshold_condition(rng)
    elif roll < 0.48:
        cond = _random_cross_condition(rng)
    elif roll < 0.68:
        cond = _random_compare_condition(rng)
    elif roll < 0.80:
        cond = _random_slope_condition(rng)
    else:
        cond = _random_pattern_condition(rng)

    # Negación: un 15 % de las condiciones negables. La ausencia de un estado es
    # información tan legítima como su presencia —«el precio NO está en zona de
    # premium», «no ha habido barrida en 5 velas»— y hasta ahora era inexpresable
    # salvo que existiera por casualidad un indicador espejo.
    if rng.random() < 0.15 and _can_negate(cond):
        cond["negate"] = True
    return cond


def _random_block(rng: np.random.Generator) -> dict:
    """
    Bloque aleatorio legal.

    `K_OF_N` solo se sortea con 3 o más condiciones: con dos, k=1 es OR y k=2 es
    AND, así que no aportaría ninguna lógica nueva y sí tres formas distintas de
    escribir la misma estrategia — lo que ensucia el hash y engaña al control de
    diversidad del GA.
    """
    n = int(rng.integers(1, _MAX_CONDITIONS + 1))
    conditions = [random_condition(rng) for _ in range(n)]
    if n >= 3 and rng.random() < 0.2:
        return {"combine": "K_OF_N", "k": int(rng.integers(2, n)), "conditions": conditions}
    return {
        "combine": str(rng.choice(("AND", "OR"))),
        "conditions": conditions,
    }


# Rangos de la gestión de riesgo: stops en fracciones, salida por tiempo en
# velas y stop por volatilidad en múltiplos de ATR (estilo StrategyQuant).
RISK_RANGES = {
    "stop_loss_pct": (0.02, 0.15),
    "take_profit_pct": (0.03, 0.30),
    "trailing_stop_pct": (0.03, 0.20),
    "max_bars": (5, 60),
    "atr_stop_mult": (1.5, 4.0),
    "atr_target_mult": (1.5, 6.0),
}


def _random_risk(rng: np.random.Generator) -> dict | None:
    """Bloque de riesgo aleatorio (o None). Combina stop-loss/take-profit,
    trailing o triple barrera, para que el GA pueda evolucionar gestión de
    riesgo —y política de salida— y no solo señales."""
    roll = rng.random()
    if roll < 0.35:
        return None  # sin gestión de riesgo
    risk: dict = {}
    if roll < 0.55:  # stop-loss (+ a veces take-profit)
        lo, hi = RISK_RANGES["stop_loss_pct"]
        risk["stop_loss_pct"] = round(float(rng.uniform(lo, hi)), 3)
        if rng.random() < 0.6:
            lo, hi = RISK_RANGES["take_profit_pct"]
            risk["take_profit_pct"] = round(float(rng.uniform(lo, hi)), 3)
    elif roll < 0.72:  # trailing-stop
        lo, hi = RISK_RANGES["trailing_stop_pct"]
        risk["trailing_stop_pct"] = round(float(rng.uniform(lo, hi)), 3)
    elif roll < 0.85:  # stop por volatilidad (múltiplos de ATR en la entrada)
        lo, hi = RISK_RANGES["atr_stop_mult"]
        risk["atr_stop_mult"] = round(float(rng.uniform(lo, hi)), 2)
    else:
        # ── Triple barrera ────────────────────────────────────────
        # Stop y objetivo escalados por la volatilidad de la entrada, más un
        # horizonte que cierra la posición si no ocurre ninguna de las dos.
        # La pregunta que responde una salida así —«¿qué pasó primero?»— es la
        # correcta; «¿se cumple otra condición técnica?» no lo es.
        lo, hi = RISK_RANGES["atr_stop_mult"]
        stop = round(float(rng.uniform(lo, hi)), 2)
        lo, hi = RISK_RANGES["atr_target_mult"]
        # Objetivo asimétrico al alza: la geometría por defecto del método
        # (2σ arriba, 1σ abajo) es lo que hace rentable una tasa de acierto
        # por debajo del 50 %.
        risk["atr_stop_mult"] = stop
        risk["atr_target_mult"] = round(float(min(hi, max(lo, stop * rng.uniform(1.2, 2.5)))), 2)
        lo, hi = RISK_RANGES["max_bars"]
        risk["max_bars"] = int(rng.integers(int(lo), int(hi) + 1))
        return risk
    # Salida por tiempo: componible con cualquiera de los stops (o sola).
    if rng.random() < 0.3:
        lo, hi = RISK_RANGES["max_bars"]
        risk["max_bars"] = int(rng.integers(int(lo), int(hi) + 1))
    return risk or None


# Rangos del dimensionamiento de posición.
SIZING_FRACTION_RANGE = (0.25, 1.0)
SIZING_RISK_PCT_RANGE = (0.01, 0.05)


def _random_sizing(rng: np.random.Generator) -> dict | None:
    """Bloque de sizing aleatorio (o None = invierte todo). El GA puede evolucionar
    cuánto capital arriesgar por operación, no solo cuándo entrar/salir."""
    roll = rng.random()
    if roll < 0.5:
        return None  # "full": invierte todo (comportamiento por defecto)
    if roll < 0.8:
        lo, hi = SIZING_FRACTION_RANGE
        return {"mode": "fraction", "fraction": round(float(rng.uniform(lo, hi)), 3)}
    lo, hi = SIZING_RISK_PCT_RANGE
    return {"mode": "risk", "risk_pct": round(float(rng.uniform(lo, hi)), 4)}


# Filtro de régimen: ADX mínimo (con su ventana fija) para permitir entradas.
REGIME_ADX_RANGE = (15.0, 35.0)
REGIME_ADX_WINDOW = 14


def _random_regime(rng: np.random.Generator) -> dict | None:
    """Filtro de régimen aleatorio (o None): exigir tendencia (ADX≥x) para entrar."""
    if rng.random() < 0.65:
        return None
    lo, hi = REGIME_ADX_RANGE
    return {"adx_min": round(float(rng.uniform(lo, hi)), 1)}


def random_direction(rng: np.random.Generator, mode: str = DEFAULT_DIRECTION) -> str:
    """
    Dirección de un spec nuevo bajo el modo de la ejecución.

    Con un modo fijo devuelve ese modo (toda la población opera al mismo lado).
    Con "auto" sortea según `AUTO_DIRECTION_WEIGHTS`, y la dirección pasa a ser
    un gen más: se hereda en el cruce y muta como cualquier otro.
    """
    if mode != "auto":
        return mode if mode in DIRECTIONS else DEFAULT_DIRECTION
    roll = float(rng.random())
    acc = 0.0
    for direction in DIRECTIONS:
        acc += AUTO_DIRECTION_WEIGHTS[direction]
        if roll < acc:
            return direction
    return DIRECTIONS[-1]


def random_spec(rng: np.random.Generator, direction: str = DEFAULT_DIRECTION) -> dict:
    """
    Genera un StrategySpec aleatorio legal (riesgo, sizing y régimen opcionales).

    `direction` es el MODO de la ejecución, no la dirección literal: admite
    "auto", que sortea la dirección de cada genoma (ver `random_direction`).
    """
    chosen = random_direction(rng, direction)
    spec = {"entry": _random_block(rng), "exit": _random_block(rng)}
    if chosen != DEFAULT_DIRECTION:
        # El campo solo se escribe cuando dice algo. Un spec largo sigue
        # serializándose exactamente igual que antes de existir la dirección, y
        # su hash no cambia: los libros de estrategias ya guardados siguen
        # siendo comparables con los nuevos.
        spec["direction"] = chosen
    if chosen == "both":
        # Los dos lados nacen INDEPENDIENTES, no en espejo. Una reversión a la
        # media al alza no es la misma estrategia que a la baja.
        spec["short_entry"] = _random_block(rng)
        spec["short_exit"] = _random_block(rng)
    risk = _random_risk(rng)
    if risk:
        spec["risk"] = risk
    sizing = _random_sizing(rng)
    if sizing:
        spec["sizing"] = sizing
    regime = _random_regime(rng)
    if regime:
        spec["regime"] = regime
    return spec


# ═══════════════════════════════════════════════════════════════════
# Validación de legalidad
# ═══════════════════════════════════════════════════════════════════

def _validate_params(indicator: str, params: dict) -> bool:
    if indicator not in _ALL:
        return False
    spec = _ALL[indicator]["params"]
    if set(params) != set(spec):
        return False
    for name, (kind, lo, hi) in spec.items():
        v = params[name]
        if not isinstance(v, (int, float)) or not (lo <= v <= hi):
            return False
    return True


def _validate_pattern_params(name: str, params: dict) -> bool:
    """Igual que `_validate_params`, pero contra el catálogo de patrones.

    Muchos patrones no tienen parámetros (una envolvente es una envolvente), así
    que el conjunto vacío es legal y frecuente."""
    spec = PATTERNS[name]["params"]
    if set(params) != set(spec):
        return False
    for pname, (_kind, lo, hi) in spec.items():
        v = params[pname]
        if not isinstance(v, (int, float)) or not (lo - 1e-9 <= v <= hi + 1e-9):
            return False
    return True


def _validate_negation(c: dict) -> bool:
    """La negación solo es legal donde tiene un «off» informativo (ver NEGATABLE)."""
    if not c.get("negate"):
        return "negate" not in c or c["negate"] is False
    if c.get("type") not in NEGATABLE:
        return False
    if c["type"] == "pattern":
        return int(c.get("lookback", 1)) >= MIN_NEGATABLE_LOOKBACK
    return True


def _validate_condition(c: dict) -> bool:
    if not _validate_negation(c):
        return False
    if c.get("type") == "pattern":
        name = c.get("pattern")
        if name not in PATTERNS:
            return False
        if not _validate_pattern_params(name, c.get("params", {})):
            return False
        lb = c.get("lookback", 1)
        lo, hi = PATTERN_LOOKBACK_RANGE
        return isinstance(lb, int) and lo <= lb <= hi
    if c.get("type") == "threshold":
        ind = c.get("indicator")
        if ind not in OSCILLATORS or c.get("op") not in THRESHOLD_OPS:
            return False
        if not _validate_params(ind, c.get("params", {})):
            return False
        lo, hi = OSCILLATORS[ind]["threshold"]
        thr = c.get("threshold")
        return isinstance(thr, (int, float)) and lo - 1e-9 <= thr <= hi + 1e-9
    if c.get("type") in ("cross", "compare"):
        ops = CROSS_OPS if c["type"] == "cross" else COMPARE_OPS
        if c.get("op") not in ops:
            return False
        for side in ("a", "b"):
            leg = c.get(side, {})
            if leg.get("indicator") not in PRICE_LIKE:
                return False
            if not _validate_params(leg["indicator"], leg.get("params", {})):
                return False
        return c["a"]["indicator"] != c["b"]["indicator"] or c["a"]["params"] != c["b"]["params"]
    if c.get("type") == "slope":
        ind = c.get("indicator")
        if ind not in _ALL or c.get("op") not in SLOPE_OPS:
            return False
        if not _validate_params(ind, c.get("params", {})):
            return False
        bars = c.get("bars")
        lo, hi = SLOPE_BARS_RANGE
        return isinstance(bars, int) and lo <= bars <= hi
    return False


def _validate_block(block: dict) -> bool:
    if block.get("combine") not in COMBINES:
        return False
    conds = block.get("conditions", [])
    if not (1 <= len(conds) <= _MAX_CONDITIONS):
        return False
    if block["combine"] == "K_OF_N":
        k = block.get("k")
        # k estrictamente entre 1 y n: en los extremos K_OF_N ES un OR o un AND,
        # y admitir esas formas duplicadas daría varios specs distintos para la
        # misma estrategia.
        if not isinstance(k, int) or not (2 <= k <= len(conds) - 1):
            return False
    elif "k" in block:
        return False
    return all(_validate_condition(c) for c in conds)


def _validate_risk(risk) -> bool:
    if risk is None:
        return True
    if not isinstance(risk, dict) or not risk:
        return False
    if set(risk) - set(RISK_RANGES):
        return False
    for name, value in risk.items():
        lo, hi = RISK_RANGES[name]
        if not isinstance(value, (int, float)) or not (lo - 1e-9 <= value <= hi + 1e-9):
            return False
    return True


def _validate_sizing(sizing) -> bool:
    if sizing is None:
        return True
    if not isinstance(sizing, dict):
        return False
    mode = sizing.get("mode")
    if mode == "fraction":
        f = sizing.get("fraction")
        lo, hi = SIZING_FRACTION_RANGE
        return isinstance(f, (int, float)) and lo - 1e-9 <= f <= hi + 1e-9
    if mode == "risk":
        r = sizing.get("risk_pct")
        lo, hi = SIZING_RISK_PCT_RANGE
        return isinstance(r, (int, float)) and lo - 1e-9 <= r <= hi + 1e-9
    return mode == "full"


def _validate_regime(regime) -> bool:
    if regime is None:
        return True
    if not isinstance(regime, dict) or set(regime) != {"adx_min"}:
        return False
    lo, hi = REGIME_ADX_RANGE
    v = regime["adx_min"]
    return isinstance(v, (int, float)) and lo - 1e-9 <= v <= hi + 1e-9


def spec_direction(spec: dict) -> str:
    """Dirección declarada por el spec (los guardados sin el campo son largos)."""
    direction = spec.get("direction", DEFAULT_DIRECTION)
    return direction if direction in DIRECTIONS else DEFAULT_DIRECTION


# Todos los bloques de condiciones que puede tener un spec, en orden canónico.
_ALL_BLOCKS = ("entry", "exit", "short_entry", "short_exit")


def condition_blocks(spec: dict) -> tuple[str, ...]:
    """
    Nombres de los bloques de condiciones PRESENTES en el spec.

    Todo lo que recorre la genética —jitter, mutación, complejidad, warm-up—
    debe pasar por aquí. Escribir `("entry", "exit")` a mano funciona hasta que
    el spec es "both", y entonces deja los bloques cortos fuera del operador sin
    romper nada: el genoma sigue siendo válido, simplemente hay medio genoma que
    no evoluciona nunca. Es el tipo de fallo que no da error, solo peores
    resultados.
    """
    return tuple(b for b in _ALL_BLOCKS if isinstance(spec.get(b), dict))


def validate_spec(spec: dict) -> bool:
    """True si el spec es estructuralmente legal y todos sus bloques válidos."""
    if not isinstance(spec, dict) or "entry" not in spec or "exit" not in spec:
        return False
    if spec.get("direction", DEFAULT_DIRECTION) not in DIRECTIONS:
        return False
    if not _validate_risk(spec.get("risk")) or not _validate_sizing(spec.get("sizing")):
        return False
    if not _validate_regime(spec.get("regime")):
        return False
    if not (_validate_block(spec["entry"]) and _validate_block(spec["exit"])):
        return False

    # Los bloques cortos SOLO existen en "both". En "short" el lado corto lo
    # abren los bloques principales, así que un `short_entry` ahí sería material
    # inerte que el GA mutaría sin efecto — y dos specs distintos describirían la
    # misma estrategia, rompiendo el hash del que depende el control de
    # diversidad.
    has_short_blocks = "short_entry" in spec or "short_exit" in spec
    if spec_direction(spec) == "both":
        if not ("short_entry" in spec and "short_exit" in spec):
            return False
        return _validate_block(spec["short_entry"]) and _validate_block(spec["short_exit"])
    return not has_short_blocks


def spec_risk(spec: dict):
    """RiskModel del spec (o None si no define gestión de riesgo)."""
    from core.domain.services.backtest_execution import RiskModel
    risk = spec.get("risk")
    if not risk:
        return None
    return RiskModel(
        stop_loss_pct=risk.get("stop_loss_pct"),
        take_profit_pct=risk.get("take_profit_pct"),
        trailing_stop_pct=risk.get("trailing_stop_pct"),
        max_bars=int(risk["max_bars"]) if risk.get("max_bars") is not None else None,
        atr_stop_mult=risk.get("atr_stop_mult"),
        atr_target_mult=risk.get("atr_target_mult"),
    )


def spec_sizing(spec: dict):
    """SizingModel del spec (o None = invierte todo el capital)."""
    from core.domain.services.backtest_execution import SizingModel
    sizing = spec.get("sizing")
    if not sizing or sizing.get("mode", "full") == "full":
        return None
    return SizingModel(
        mode=sizing["mode"],
        fraction=sizing.get("fraction", 1.0),
        risk_pct=sizing.get("risk_pct", 0.02),
    )


# ═══════════════════════════════════════════════════════════════════
# Compilación a señales (intérprete causal, sin lookahead)
# ═══════════════════════════════════════════════════════════════════

def _series(df: pd.DataFrame, indicator: str, params: dict, cache: dict) -> np.ndarray:
    key = (indicator, tuple(sorted(params.items())))
    if key not in cache:
        try:
            arr = np.asarray(_ALL[indicator]["compute"](df, params), dtype=float)
        except Exception:
            # Algunos indicadores (ADX, MFI…) fallan en ventanas demasiado cortas:
            # devolver NaN (no dispara señal) en vez de romper el backtest.
            arr = np.full(len(df), np.nan)
        cache[key] = arr
    return cache[key]


def _condition_bool(df: pd.DataFrame, c: dict, cache: dict) -> np.ndarray:
    """Evalúa la condición y aplica su negación si la declara (ver `NEGATABLE`)."""
    out = _condition_bool_raw(df, c, cache)
    return ~out if c.get("negate") else out


def _condition_bool_raw(df: pd.DataFrame, c: dict, cache: dict) -> np.ndarray:
    if c["type"] == "pattern":
        # Sucesos de acción del precio. Ya llegan como booleanos causales desde
        # `price_patterns`; aquí solo se aplica la ventana de vigencia.
        key = ("pattern", c["pattern"], tuple(sorted(c.get("params", {}).items())),
               int(c.get("lookback", 1)))
        if key not in cache:
            flags = price_patterns.detect(df, c["pattern"], c.get("params"))
            cache[key] = price_patterns.occurred_within(flags, int(c.get("lookback", 1)))
        return cache[key]

    if c["type"] == "threshold":
        s = _series(df, c["indicator"], c["params"], cache)
        # Comparaciones con NaN dan False en numpy (el warm-up no dispara señal)
        return s > c["threshold"] if c["op"] == "gt" else s < c["threshold"]

    if c["type"] == "slope":
        # Pendiente: la serie sube/baja respecto a hace `bars` velas (estado).
        s = _series(df, c["indicator"], c["params"], cache)
        bars = int(c["bars"])
        prev = np.full_like(s, np.nan)
        prev[bars:] = s[:-bars]
        with np.errstate(invalid="ignore"):
            sb = s > prev if c["op"] == "rising" else s < prev
        return np.where(np.isnan(s) | np.isnan(prev), False, sb)

    a = _series(df, c["a"]["indicator"], c["a"]["params"], cache)
    b = _series(df, c["b"]["indicator"], c["b"]["params"], cache)
    diff = a - b

    if c["type"] == "compare":
        # Estado persistente: True mientras A esté por encima/debajo de B.
        with np.errstate(invalid="ignore"):
            cmp_ = diff > 0 if c["op"] == "above" else diff < 0
        return np.where(np.isnan(diff), False, cmp_)

    # cruce: solo en la vela del cruce (i-1 al lado opuesto, i al lado nuevo)
    prev = np.empty_like(diff)
    prev[0] = np.nan
    prev[1:] = diff[:-1]
    with np.errstate(invalid="ignore"):
        if c["op"] == "cross_above":
            cb = (prev <= 0) & (diff > 0)
        else:
            cb = (prev >= 0) & (diff < 0)
    return np.where(np.isnan(diff) | np.isnan(prev), False, cb)


def _combine(bools: list[np.ndarray], how: str, k: int | None = None) -> np.ndarray:
    """
    Combina las condiciones de un bloque.

    `K_OF_N` es la generalización de las otras dos: con k=n es AND y con k=1 es
    OR, y entre medias expresa algo que ninguna de ellas puede decir —«al menos
    2 de estas 3 confirmaciones»—. Es una familia entera de estrategias que
    hasta ahora era inalcanzable, no difícil de alcanzar: la lógica de
    confirmación parcial no se puede escribir encadenando Y y O sin anidar.
    """
    stack = np.vstack(bools)
    if how == "K_OF_N":
        return np.sum(stack, axis=0) >= int(k or 1)
    return np.all(stack, axis=0) if how == "AND" else np.any(stack, axis=0)


def compile_signals(df: pd.DataFrame, spec: dict) -> np.ndarray:
    """
    Traduce un StrategySpec a un array de señales (1=compra, -1=venta, 0=hold).
    El cálculo es causal (indicadores rolling + cruces i-1/i), por lo que no
    introduce lookahead. Si entrada y salida coinciden en una vela, prevalece
    la salida (evita whipsaw).
    """
    n = len(df)
    cache: dict = {}
    entry = _combine([_condition_bool(df, c, cache) for c in spec["entry"]["conditions"]],
                     spec["entry"]["combine"], spec["entry"].get("k"))
    exit_ = _combine([_condition_bool(df, c, cache) for c in spec["exit"]["conditions"]],
                     spec["exit"]["combine"], spec["exit"].get("k"))
    # Filtro de régimen: solo se permite ENTRAR si hay tendencia (ADX ≥ umbral).
    # No afecta a las salidas: se debe poder salir en cualquier régimen.
    regime = spec.get("regime")
    if regime:
        adx = _series(df, "ADX", {"window": REGIME_ADX_WINDOW}, cache)
        with np.errstate(invalid="ignore"):
            trending = np.where(np.isnan(adx), False, adx >= regime["adx_min"])
        entry = entry & trending
    signals = np.zeros(n)
    signals[exit_] = -1
    signals[entry & ~exit_] = 1
    return signals


def compile_short_signals(df: pd.DataFrame, spec: dict) -> np.ndarray | None:
    """
    Señales del lado CORTO (1 = abrir, −1 = cerrar, 0 = mantener), o `None`.

    Devuelve `None` cuando la estrategia no opera cortos, y eso importa: es lo
    que permite al motor comportarse exactamente como antes en todo lo ya
    validado, en vez de recibir un array de ceros que tendría que recorrer igual.

    Qué bloques usa según la dirección:
      · "long"  → ninguno (None).
      · "short" → los bloques PRINCIPALES. La estrategia es una sola y opera al
        otro lado; no hay bloques duplicados que mantener sincronizados.
      · "both"  → `short_entry` / `short_exit`, evolucionados aparte del lado
        largo porque una reversión al alza no es la misma estrategia que a la
        baja.

    El filtro de régimen se aplica igual que en el lado largo: condiciona la
    ENTRADA, nunca la salida. Se debe poder cerrar un corto en cualquier
    régimen, y más aún que un largo — su pérdida no tiene tope.
    """
    direction = spec_direction(spec)
    if direction == "long":
        return None

    entry_block = spec["entry"] if direction == "short" else spec.get("short_entry")
    exit_block = spec["exit"] if direction == "short" else spec.get("short_exit")
    if not entry_block or not exit_block:
        return None

    n = len(df)
    cache: dict = {}
    entry = _combine([_condition_bool(df, c, cache) for c in entry_block["conditions"]],
                     entry_block["combine"], entry_block.get("k"))
    exit_ = _combine([_condition_bool(df, c, cache) for c in exit_block["conditions"]],
                     exit_block["combine"], exit_block.get("k"))

    regime = spec.get("regime")
    if regime:
        adx = _series(df, "ADX", {"window": REGIME_ADX_WINDOW}, cache)
        with np.errstate(invalid="ignore"):
            trending = np.where(np.isnan(adx), False, adx >= regime["adx_min"])
        entry = entry & trending

    signals = np.zeros(n)
    signals[exit_] = -1
    signals[entry & ~exit_] = 1
    return signals


def compile_long_signals(df: pd.DataFrame, spec: dict) -> np.ndarray:
    """
    Señales del lado LARGO, o un array inerte si la estrategia es solo corta.

    `compile_signals` sigue devolviendo las señales de los bloques principales
    sin mirar la dirección — es lo que consumen el detector de lookahead, el
    explicador de señales y todo lo construido encima. Esta función es la que
    aplica la dirección, y por eso es la que usa el backtest.
    """
    if spec_direction(spec) == "short":
        return np.zeros(len(df))
    return compile_signals(df, spec)


@dataclass(frozen=True)
class SideSignals:
    """
    Las señales de los DOS lados de una estrategia, viajando juntas.

    Existe por una razón concreta: el backtest necesita ambas a la vez, y el
    walk-forward reutiliza el cálculo de los prefijos (ver `_prefix_signals`).
    Con dos parámetros sueltos sería posible recortar uno y olvidar el otro
    —dando un tramo con largos del prefijo y cortos del histórico entero—, y
    ese fallo no rompería nada: devolvería números plausibles y equivocados.
    Empaquetados, recortar uno recorta los dos o no compila.

    `short` es `None` —no un array de ceros— cuando la estrategia no opera
    cortos. Así el motor toma exactamente el mismo camino que antes de que
    existieran los cortos en todo lo ya validado.
    """
    long: np.ndarray
    short: np.ndarray | None = None

    def __len__(self) -> int:
        return len(self.long)

    def head(self, k: int) -> "SideSignals":
        """Prefijo de ambos lados. Ver `_prefix_signals` para por qué es legítimo."""
        return SideSignals(self.long[:k], None if self.short is None else self.short[:k])


def compile_sides(df: pd.DataFrame, spec: dict) -> SideSignals:
    """Compila los dos lados del spec en una sola llamada."""
    return SideSignals(compile_long_signals(df, spec), compile_short_signals(df, spec))


# Acciones que puede emitir una estrategia en vivo.
#
# Cuatro, no dos. Con solo BUY/SELL, la orden «abrir un corto» tendría que
# viajar como una de las dos, y la que se le parece —SELL— significa justo lo
# contrario: cerrar una posición larga. Un consumidor que las confundiera
# operaría al revés sin que nada fallara.
SIGNALS = ("BUY", "SELL", "SHORT", "COVER", "HOLD")

# Qué acción significa cada señal, para las superficies que la muestran.
SIGNAL_LABELS = {
    "BUY": "COMPRA",
    "SELL": "VENTA",
    "SHORT": "APERTURA EN CORTO",
    "COVER": "CIERRE DE CORTO",
    "HOLD": "SIN CAMBIOS",
}

# Señales que abren o cierran el lado corto. Un consumidor que no sepa operar
# cortos tiene que poder detectarlas y ABSTENERSE, no interpretarlas a su manera.
SHORT_SIGNALS = ("SHORT", "COVER")


def signal_state(df: pd.DataFrame, spec: dict) -> dict:
    """
    Estado de la estrategia en la ÚLTIMA vela: la acción actual y qué
    condiciones están activas ahora mismo. Sirve para "activar" una estrategia
    generada y mostrar/notificar su señal en vivo. Causal: solo usa información
    disponible al cierre de la última vela.

    `signal` es una de `SIGNALS`. Cuál sale depende de la dirección del spec:

      · "long"  → BUY / SELL, como siempre.
      · "short" → SHORT (abrir) / COVER (cerrar). Emitir BUY aquí sería decirle
        al usuario que compre cuando la estrategia dice justo lo contrario.
      · "both"  → las cuatro, con los cierres por delante de las aperturas,
        igual que en el motor de backtest: si las dos cosas coinciden en la
        misma vela, primero se sale.

    `direction` y `side` acompañan a la señal para que un consumidor que no
    sepa operar cortos pueda ABSTENERSE en vez de interpretarla a su manera.
    """
    direction = spec_direction(spec)
    if df is None or len(df) == 0:
        return {"signal": "HOLD", "direction": direction, "side": None,
                "entry_active": False, "exit_active": False, "conditions": []}

    cache: dict = {}
    def last(arr) -> bool:
        return bool(np.asarray(arr)[-1])

    conditions: list[dict] = []

    def block_active(block: dict, label: str) -> bool:
        bools = []
        for c in block["conditions"]:
            b = _condition_bool(df, c, cache)
            bools.append(b)
            conditions.append({"side": label, "desc": _describe_condition(c), "active": last(b)})
        # `k` viaja con el bloque: sin él, un bloque «al menos 2 de 3» se
        # evaluaría como un O y dispararía la señal en vivo mucho más a menudo
        # que la estrategia que se validó.
        return last(_combine(bools, block["combine"], block.get("k")))

    entry_active = block_active(spec["entry"], "entry")
    exit_active = block_active(spec["exit"], "exit")

    if direction == "short":
        signal = "COVER" if exit_active else ("SHORT" if entry_active else "HOLD")
        side = "short" if signal != "HOLD" else None
        return {"signal": signal, "direction": direction, "side": side,
                "entry_active": entry_active, "exit_active": exit_active,
                "conditions": conditions}

    if direction == "both":
        short_entry = block_active(spec["short_entry"], "short_entry")
        short_exit = block_active(spec["short_exit"], "short_exit")
        # Los cierres ganan a las aperturas, y el cierre del largo al del corto:
        # el mismo orden de precedencia que aplica el motor de backtest, para
        # que lo que se notifica coincida con lo que se midió.
        if exit_active:
            signal, side = "SELL", "long"
        elif short_exit:
            signal, side = "COVER", "short"
        elif entry_active:
            signal, side = "BUY", "long"
        elif short_entry:
            signal, side = "SHORT", "short"
        else:
            signal, side = "HOLD", None
        return {"signal": signal, "direction": direction, "side": side,
                "entry_active": entry_active, "exit_active": exit_active,
                "short_entry_active": short_entry, "short_exit_active": short_exit,
                "conditions": conditions}

    signal = "SELL" if exit_active else ("BUY" if entry_active else "HOLD")
    return {
        "signal": signal,
        "direction": direction,
        "side": "long" if signal != "HOLD" else None,
        "entry_active": entry_active,
        "exit_active": exit_active,
        "conditions": conditions,
    }


# ═══════════════════════════════════════════════════════════════════
# Identidad y descripción legible
# ═══════════════════════════════════════════════════════════════════

def spec_hash(spec: dict) -> str:
    """Hash canónico (control de diversidad y deduplicación en el GA)."""
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(canonical.encode()).hexdigest()[:12]


def _describe_indicator(leg: dict) -> str:
    params = ",".join(f"{v}" for v in leg["params"].values())
    return f"{leg['indicator']}({params})" if params else leg["indicator"]


def _describe_condition(c: dict) -> str:
    text = _describe_condition_raw(c)
    return f"NO ({text})" if c.get("negate") else text


def _describe_condition_raw(c: dict) -> str:
    if c["type"] == "pattern":
        label = price_patterns.PATTERN_LABELS.get(c["pattern"], c["pattern"])
        lb = int(c.get("lookback", 1))
        window = "" if lb <= 1 else f" en las últimas {lb} velas"
        return f"hay {label}{window}"
    if c["type"] == "threshold":
        sym = ">" if c["op"] == "gt" else "<"
        return f"{_describe_indicator(c)} {sym} {c['threshold']}"
    if c["type"] == "slope":
        verb = "al alza" if c["op"] == "rising" else "a la baja"
        return f"{_describe_indicator(c)} {verb} en {c['bars']} velas"
    if c["type"] == "compare":
        rel = "POR ENCIMA de" if c["op"] == "above" else "POR DEBAJO de"
        return f"{_describe_indicator(c['a'])} {rel} {_describe_indicator(c['b'])}"
    arrow = "cruza arriba" if c["op"] == "cross_above" else "cruza abajo"
    return f"{_describe_indicator(c['a'])} {arrow} {_describe_indicator(c['b'])}"


def _describe_risk(risk: dict | None) -> str:
    if not risk:
        return ""
    parts = []
    if risk.get("stop_loss_pct") is not None:
        parts.append(f"SL {round(risk['stop_loss_pct'] * 100, 1)}%")
    if risk.get("take_profit_pct") is not None:
        parts.append(f"TP {round(risk['take_profit_pct'] * 100, 1)}%")
    if risk.get("trailing_stop_pct") is not None:
        parts.append(f"trailing {round(risk['trailing_stop_pct'] * 100, 1)}%")
    if risk.get("atr_stop_mult") is not None and risk.get("atr_target_mult") is not None:
        # Las tres juntas tienen nombre propio: decirlo es más informativo que
        # enumerar sus lados por separado.
        parts.append(f"triple barrera {risk['atr_target_mult']}/{risk['atr_stop_mult']}×ATR")
    elif risk.get("atr_stop_mult") is not None:
        parts.append(f"stop {risk['atr_stop_mult']}×ATR")
    elif risk.get("atr_target_mult") is not None:
        parts.append(f"objetivo {risk['atr_target_mult']}×ATR")
    if risk.get("max_bars") is not None:
        parts.append(f"máx {int(risk['max_bars'])} velas")
    return f" [{' · '.join(parts)}]" if parts else ""


def _describe_sizing(sizing: dict | None) -> str:
    if not sizing or sizing.get("mode", "full") == "full":
        return ""
    if sizing["mode"] == "fraction":
        return f" [tamaño {round(sizing['fraction'] * 100)}% del capital]"
    return f" [riesgo {round(sizing['risk_pct'] * 100, 1)}% por trade]"


def describe_spec(spec: dict) -> str:
    """Descripción en español legible de la lógica de la estrategia."""
    def block(b):
        parts = [_describe_condition(c) for c in b["conditions"]]
        if b["combine"] == "K_OF_N":
            # «al menos 2 de: A, B, C» — lógica de confirmación parcial, que no
            # se puede decir encadenando Y y O sin anidar.
            return f"al menos {b['k']} de: " + ", ".join(parts)
        sep = " Y " if b["combine"] == "AND" else " O "
        return sep.join(parts)
    regime = spec.get("regime")
    regime_txt = f" (solo si ADX≥{regime['adx_min']})" if regime else ""
    direction = spec_direction(spec)
    tail = f"{_describe_risk(spec.get('risk'))}{_describe_sizing(spec.get('sizing'))}"

    if direction == "short":
        return (f"CORTO si {block(spec['entry'])}{regime_txt}; "
                f"CERRAR si {block(spec['exit'])}{tail}")
    if direction == "both":
        return (f"LARGO si {block(spec['entry'])}{regime_txt}; salir si {block(spec['exit'])}. "
                f"CORTO si {block(spec['short_entry'])}; cerrar si {block(spec['short_exit'])}"
                f"{tail}")
    return (f"ENTRAR si {block(spec['entry'])}{regime_txt}; SALIR si {block(spec['exit'])}"
            f"{tail}")


def max_warmup(spec: dict) -> int:
    """Mayor ventana usada por el spec (velas de calentamiento antes de operar)."""
    longest = 1
    def scan(c):
        nonlocal longest
        if c["type"] == "pattern":
            # El calentamiento de un patrón no sale de sus parámetros: una
            # envolvente no tiene ninguno y aun así necesita 2 velas. El
            # catálogo lo declara explícitamente.
            longest = max(longest, int(PATTERNS[c["pattern"]]["warmup"]))
            for v in c.get("params", {}).values():
                longest = max(longest, int(v))
            return
        legs = [c] if c["type"] in ("threshold", "slope") else [c["a"], c["b"]]
        for leg in legs:
            for v in leg["params"].values():
                longest = max(longest, int(v))
        if c["type"] == "slope":
            longest = max(longest, int(c["bars"]))
    # Los bloques cortos cuentan igual: si el lado corto usa una EMA de 200 y el
    # largo solo una de 20, la estrategia sigue necesitando 200 velas de
    # calentamiento antes de poder operar de verdad. Mirar solo `entry`/`exit`
    # subestimaría el warm-up de todo spec "both".
    for side in condition_blocks(spec):
        for c in spec[side]["conditions"]:
            scan(c)
    return longest


# ═══════════════════════════════════════════════════════════════════
# Semillas: las 5 estrategias clásicas expresadas como specs (warm start)
# ═══════════════════════════════════════════════════════════════════

def _jitter_value(indicator: str, name: str, value, rng: np.random.Generator):
    kind, lo, hi = _ALL[indicator]["params"][name]
    if kind == "int":
        step = max(1, int(round((hi - lo) * 0.1)))
        nv = int(value) + int(rng.integers(-step, step + 1))
        return int(min(hi, max(lo, nv)))
    span = (hi - lo) * 0.1
    nv = float(value) + float(rng.uniform(-span, span))
    return round(float(min(hi, max(lo, nv))), 2)


def jitter_params(spec: dict, rng: np.random.Generator) -> dict:
    """
    Vecino del spec: perturba ligeramente sus parámetros numéricos (±10% del
    rango) sin cambiar la estructura. Lo usa el gating para construir la matriz
    de configuraciones del PBO (CSCV) alrededor de la estrategia finalista.
    """
    import copy
    out = copy.deepcopy(spec)
    for side in condition_blocks(out):
        for c in out[side]["conditions"]:
            if c["type"] == "pattern":
                # El patrón en sí no se cambia (sería otra estructura, no un
                # vecino); sí sus parámetros y su ventana de vigencia, que es
                # donde vive la sensibilidad real de este tipo de condición.
                meta = PATTERNS[c["pattern"]]["params"]
                for k, v in c.get("params", {}).items():
                    kind, lo, hi = meta[k]
                    span = (hi - lo) * 0.1
                    nv = float(min(hi, max(lo, v + rng.uniform(-span, span))))
                    c["params"][k] = int(round(nv)) if kind == "int" else round(nv, 2)
                lo, hi = PATTERN_LOOKBACK_RANGE
                c["lookback"] = int(min(hi, max(lo, int(c.get("lookback", 1))
                                               + int(rng.integers(-1, 2)))))
            elif c["type"] in ("threshold", "slope"):
                for k, v in c["params"].items():
                    c["params"][k] = _jitter_value(c["indicator"], k, v, rng)
            else:  # cross / compare: dos patas de tipo precio
                for leg in (c["a"], c["b"]):
                    for k, v in leg["params"].items():
                        leg["params"][k] = _jitter_value(leg["indicator"], k, v, rng)
                # Si el jitter igualó ambas patas (p. ej. SMA(38) vs SMA(38)),
                # separar la pata B un paso para mantener la condición legal.
                if c["a"]["indicator"] == c["b"]["indicator"] and c["a"]["params"] == c["b"]["params"]:
                    for k, v in c["b"]["params"].items():
                        kind, lo, hi = _ALL[c["b"]["indicator"]]["params"][k]
                        if kind == "int":
                            c["b"]["params"][k] = int(v + 1) if v + 1 <= hi else int(v - 1)
                        else:
                            step = round((hi - lo) * 0.05, 2)
                            c["b"]["params"][k] = round(v + step, 2) if v + step <= hi else round(v - step, 2)
                        break
    # Perturbar también la gestión de riesgo (±10% del rango)
    if out.get("risk"):
        for name, value in out["risk"].items():
            lo, hi = RISK_RANGES[name]
            span = (hi - lo) * 0.1
            nv = float(min(hi, max(lo, value + rng.uniform(-span, span))))
            out["risk"][name] = int(round(nv)) if name == "max_bars" else round(nv, 3)
    # Perturbar el dimensionamiento de posición
    sizing = out.get("sizing")
    if sizing and sizing.get("mode") == "fraction":
        lo, hi = SIZING_FRACTION_RANGE
        span = (hi - lo) * 0.1
        sizing["fraction"] = round(float(min(hi, max(lo, sizing["fraction"] + rng.uniform(-span, span)))), 3)
    elif sizing and sizing.get("mode") == "risk":
        lo, hi = SIZING_RISK_PCT_RANGE
        span = (hi - lo) * 0.1
        sizing["risk_pct"] = round(float(min(hi, max(lo, sizing["risk_pct"] + rng.uniform(-span, span)))), 4)
    # Perturbar el filtro de régimen (umbral de ADX)
    if out.get("regime"):
        lo, hi = REGIME_ADX_RANGE
        span = (hi - lo) * 0.1
        out["regime"]["adx_min"] = round(float(min(hi, max(lo, out["regime"]["adx_min"] + rng.uniform(-span, span)))), 1)
    return out


# ═══════════════════════════════════════════════════════════════════
# Espejo direccional (solo para SEMBRAR, nunca para generar)
# ═══════════════════════════════════════════════════════════════════

# Patrones que tienen contrario. Los que no aparecen aquí son NEUTRALES —un
# doji, una vela interior o una CRT no tienen lado— y se dejan intactos:
# inventarles un opuesto sería fabricar una condición que no existe.
_MIRROR_PATTERNS = {
    "BULL_ENGULF": "BEAR_ENGULF",
    "FVG_BULL": "FVG_BEAR",
    "OB_BULL": "OB_BEAR",
    "ORB_UP": "ORB_DOWN",
    "PO3_BULL": "PO3_BEAR",
    "SWEEP_LOW": "SWEEP_HIGH",
    "HAMMER": "SHOOTING_STAR",
    "FIB_DISCOUNT": "FIB_PREMIUM",
}
_MIRROR_PATTERNS.update({v: k for k, v in _MIRROR_PATTERNS.items()})

# Osciladores que NO tienen dirección: miden intensidad o régimen, no sesgo.
# «ADX > 25» significa «hay tendencia», y su espejo no es «ADX < 30» — es «ADX
# > 25» otra vez. Reflejar su umbral no invertiría la estrategia, la rompería.
_NON_DIRECTIONAL = ("ADX", "ATR_PCT", "VOLRATIO")


def _mirror_condition(c: dict) -> dict:
    """La condición contraria: mismo indicador y mismos parámetros, lado opuesto."""
    out = copy_module.deepcopy(c)
    kind = out["type"]

    if kind == "pattern":
        out["pattern"] = _MIRROR_PATTERNS.get(out["pattern"], out["pattern"])
        return out

    if kind == "threshold":
        if out["indicator"] in _NON_DIRECTIONAL:
            return out
        lo, hi = OSCILLATORS[out["indicator"]]["threshold"]
        # Reflexión dentro del rango del propio oscilador: en un RSI de rango
        # (15, 85), «< 30» pasa a «> 70». No es una constante mágica, es el
        # mismo punto medido desde el otro extremo.
        out["threshold"] = round(float(lo + hi - out["threshold"]), 2)
        out["op"] = "gt" if out["op"] == "lt" else "lt"
        return out

    if kind == "slope":
        if out["indicator"] not in _NON_DIRECTIONAL:
            out["op"] = "falling" if out["op"] == "rising" else "rising"
        return out

    if kind == "cross":
        out["op"] = "cross_below" if out["op"] == "cross_above" else "cross_above"
        return out

    out["op"] = "below" if out["op"] == "above" else "above"   # compare
    return out


def _mirror_block(block: dict) -> dict:
    out = copy_module.deepcopy(block)
    out["conditions"] = [_mirror_condition(c) for c in block["conditions"]]
    return out


def mirror_spec(spec: dict) -> dict:
    """
    La versión CONTRARIA de la lógica del spec, con la misma estructura.

    Existe para un solo uso: **sembrar** una búsqueda de cortos. Las 5 clásicas
    del catálogo son estrategias largas, y meterlas sin tocar en una ejecución
    de cortos arrancaría el GA desde estrategias que en ese lado pierden dinero
    por construcción. Su espejo —«RSI > 70 → corto» en vez de «RSI < 30 →
    largo»— sí es el punto de partida canónico, el mismo que usaría cualquiera
    a mano.

    Lo que NO es: una forma de generar el lado corto de una estrategia. Eso
    sigue prohibido en `random_spec` y en `_mutate_direction`, y por la misma
    razón de siempre — un lado corto obtenido por espejo hereda umbrales
    calibrados contra una dinámica que no es la suya. Aquí es aceptable porque
    una semilla no es un resultado: es un punto de partida que el fitness va a
    juzgar igual que a cualquier otro.

    Deja intacto lo que no tiene contrario: los patrones neutros (doji, vela
    interior, CRT) y los osciladores de intensidad (ADX, ATR%, ratio de
    volumen), que miden régimen y no sesgo.
    """
    out = copy_module.deepcopy(spec)
    for side in condition_blocks(spec):
        out[side] = _mirror_block(spec[side])
    return out


def seed_specs() -> list[dict]:
    """
    Las 5 estrategias del catálogo escritas como StrategySpec. Sirven de
    población inicial "buena" para el GA y demuestran que la representación
    componible cubre las estrategias clásicas.
    """
    return [
        {  # RSI reversal
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 30.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 70.0}]},
        },
        {  # MACD crossover
            "entry": {"combine": "AND", "conditions": [
                {"type": "cross", "a": {"indicator": "MACD_LINE", "params": {"fast": 12, "slow": 26, "signal": 9}},
                 "b": {"indicator": "MACD_SIGNAL", "params": {"fast": 12, "slow": 26, "signal": 9}}, "op": "cross_above"}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "cross", "a": {"indicator": "MACD_LINE", "params": {"fast": 12, "slow": 26, "signal": 9}},
                 "b": {"indicator": "MACD_SIGNAL", "params": {"fast": 12, "slow": 26, "signal": 9}}, "op": "cross_below"}]},
        },
        {  # SMA crossover
            "entry": {"combine": "AND", "conditions": [
                {"type": "cross", "a": {"indicator": "SMA", "params": {"window": 20}},
                 "b": {"indicator": "SMA", "params": {"window": 50}}, "op": "cross_above"}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "cross", "a": {"indicator": "SMA", "params": {"window": 20}},
                 "b": {"indicator": "SMA", "params": {"window": 50}}, "op": "cross_below"}]},
        },
        {  # EMA trend
            "entry": {"combine": "AND", "conditions": [
                {"type": "cross", "a": {"indicator": "PRICE", "params": {}},
                 "b": {"indicator": "EMA", "params": {"window": 26}}, "op": "cross_above"}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "cross", "a": {"indicator": "PRICE", "params": {}},
                 "b": {"indicator": "EMA", "params": {"window": 26}}, "op": "cross_below"}]},
        },
        {  # Bollinger bounce
            "entry": {"combine": "AND", "conditions": [
                {"type": "cross", "a": {"indicator": "PRICE", "params": {}},
                 "b": {"indicator": "BB_LOWER", "params": {"window": 20, "dev": 2.0}}, "op": "cross_below"}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "cross", "a": {"indicator": "PRICE", "params": {}},
                 "b": {"indicator": "BB_UPPER", "params": {"window": 20, "dev": 2.0}}, "op": "cross_above"}]},
        },
        {  # Ruptura de Donchian con filtro de tendencia (estilo turtle)
            "entry": {"combine": "AND", "conditions": [
                {"type": "cross", "a": {"indicator": "PRICE", "params": {}},
                 "b": {"indicator": "DONCH_UPPER", "params": {"window": 20}}, "op": "cross_above"},
                {"type": "compare", "a": {"indicator": "PRICE", "params": {}},
                 "b": {"indicator": "SMA", "params": {"window": 100}}, "op": "above"}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "cross", "a": {"indicator": "PRICE", "params": {}},
                 "b": {"indicator": "DONCH_LOWER", "params": {"window": 10}}, "op": "cross_below"}]},
        },
        {  # Pullback en tendencia: RSI barato con el precio sobre su SMA(150)
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 40.0},
                {"type": "compare", "a": {"indicator": "PRICE", "params": {}},
                 "b": {"indicator": "SMA", "params": {"window": 150}}, "op": "above"}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 65.0}]},
        },
    ]
