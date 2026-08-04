"""
strategy_spec.py — Representación componible de estrategias (Módulo 0).

Una estrategia es un StrategySpec: bloques de condiciones de entrada y de
salida sobre el catálogo de indicadores (osciladores: RSI, StochRSI, Stoch,
CCI, Williams %R, ADX, MFI, CMF, ROC, ATR%, Aroon, TRIX, ratio de volumen;
series de precio: SMA/EMA/WMA/Hull/KAMA, Bollinger, MACD, Ichimoku, PSAR,
canales Donchian/Keltner y retrocesos de Fibonacci) con CUATRO tipos de
condición al estilo de los generadores profesionales (StrategyQuant y afines):
umbral, cruce, estado (A por encima/debajo de B) y pendiente (al alza/baja en
n velas). El compilador traduce un spec a un array de señales (1/-1/0) que el
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

Capa de dominio: Python puro, sin BD ni framework.
"""

import hashlib
import json
import math
from typing import Callable

import numpy as np
import pandas as pd
import ta as ta_lib

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
THRESHOLD_OPS = ("gt", "lt")
CROSS_OPS = ("cross_above", "cross_below")
COMPARE_OPS = ("above", "below")   # estado persistente: A por encima/debajo de B
SLOPE_OPS = ("rising", "falling")  # pendiente: la serie sube/baja vs hace n velas
SLOPE_BARS_RANGE = (2, 10)
COMBINES = ("AND", "OR")
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
    payload = {
        "blocks": blocks,
        "ops": {
            "threshold": list(THRESHOLD_OPS), "cross": list(CROSS_OPS),
            "compare": list(COMPARE_OPS), "slope": list(SLOPE_OPS),
            "slope_bars": list(SLOPE_BARS_RANGE), "combines": list(COMBINES),
        },
        "max_conditions": _MAX_CONDITIONS,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"{len(_ALL)}b-{digest[:12]}"


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


def random_condition(rng: np.random.Generator) -> dict:
    """Condición aleatoria legal. Mezcla de los 4 tipos con pesos que favorecen
    los tipos más expresivos (umbral y estado) sin abandonar cruces/pendientes."""
    roll = rng.random()
    if roll < 0.35:
        return _random_threshold_condition(rng)
    if roll < 0.60:
        return _random_cross_condition(rng)
    if roll < 0.85:
        return _random_compare_condition(rng)
    return _random_slope_condition(rng)


def _random_block(rng: np.random.Generator) -> dict:
    k = int(rng.integers(1, _MAX_CONDITIONS + 1))
    return {
        "combine": str(rng.choice(COMBINES)),
        "conditions": [random_condition(rng) for _ in range(k)],
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


def random_spec(rng: np.random.Generator) -> dict:
    """Genera un StrategySpec aleatorio legal (riesgo, sizing y régimen opcionales)."""
    spec = {"entry": _random_block(rng), "exit": _random_block(rng)}
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


def _validate_condition(c: dict) -> bool:
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


def validate_spec(spec: dict) -> bool:
    """True si el spec es estructuralmente legal y todos sus bloques válidos."""
    if not isinstance(spec, dict) or "entry" not in spec or "exit" not in spec:
        return False
    if not _validate_risk(spec.get("risk")) or not _validate_sizing(spec.get("sizing")):
        return False
    if not _validate_regime(spec.get("regime")):
        return False
    return _validate_block(spec["entry"]) and _validate_block(spec["exit"])


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


def _combine(bools: list[np.ndarray], how: str) -> np.ndarray:
    stack = np.vstack(bools)
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
                     spec["entry"]["combine"])
    exit_ = _combine([_condition_bool(df, c, cache) for c in spec["exit"]["conditions"]],
                     spec["exit"]["combine"])
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


def signal_state(df: pd.DataFrame, spec: dict) -> dict:
    """
    Estado de la estrategia en la ÚLTIMA vela: la señal actual (BUY/SELL/HOLD) y
    qué condiciones de entrada/salida están activas ahora mismo. Sirve para
    "activar" una estrategia generada y mostrar/notificar su señal en vivo.
    Causal: solo usa información disponible al cierre de la última vela.
    """
    if df is None or len(df) == 0:
        return {"signal": "HOLD", "entry_active": False, "exit_active": False, "conditions": []}

    cache: dict = {}
    def last(arr) -> bool:
        return bool(np.asarray(arr)[-1])

    conditions = []
    entry_bools = []
    for c in spec["entry"]["conditions"]:
        b = _condition_bool(df, c, cache)
        entry_bools.append(b)
        conditions.append({"side": "entry", "desc": _describe_condition(c), "active": last(b)})
    exit_bools = []
    for c in spec["exit"]["conditions"]:
        b = _condition_bool(df, c, cache)
        exit_bools.append(b)
        conditions.append({"side": "exit", "desc": _describe_condition(c), "active": last(b)})

    entry_active = last(_combine(entry_bools, spec["entry"]["combine"]))
    exit_active = last(_combine(exit_bools, spec["exit"]["combine"]))
    signal = "SELL" if exit_active else ("BUY" if entry_active else "HOLD")
    return {
        "signal": signal,
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
        sep = " Y " if b["combine"] == "AND" else " O "
        return sep.join(_describe_condition(c) for c in b["conditions"])
    regime = spec.get("regime")
    regime_txt = f" (solo si ADX≥{regime['adx_min']})" if regime else ""
    return (f"ENTRAR si {block(spec['entry'])}{regime_txt}; SALIR si {block(spec['exit'])}"
            f"{_describe_risk(spec.get('risk'))}{_describe_sizing(spec.get('sizing'))}")


def max_warmup(spec: dict) -> int:
    """Mayor ventana usada por el spec (velas de calentamiento antes de operar)."""
    longest = 1
    def scan(c):
        nonlocal longest
        legs = [c] if c["type"] in ("threshold", "slope") else [c["a"], c["b"]]
        for leg in legs:
            for v in leg["params"].values():
                longest = max(longest, int(v))
        if c["type"] == "slope":
            longest = max(longest, int(c["bars"]))
    for side in ("entry", "exit"):
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
    for side in ("entry", "exit"):
        for c in out[side]["conditions"]:
            if c["type"] in ("threshold", "slope"):
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
