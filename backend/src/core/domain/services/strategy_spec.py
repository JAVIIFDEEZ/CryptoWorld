"""
strategy_spec.py — Representación componible de estrategias (Módulo 0).

Una estrategia es un StrategySpec: bloques de condiciones de entrada y de
salida sobre los indicadores existentes (RSI, MACD, Bollinger, SMA/EMA, Stoch
RSI, CCI, ADX, Williams %R) con sus operadores (cruce, umbral) y rangos de
parámetros. El compilador traduce un spec a un array de señales (1/-1/0) que
el motor de backtest existente (backtest_signals) puede ejecutar — de modo que
el generador genético produce estrategias NUEVAS sin tocar el motor ni la
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


# Osciladores: se comparan contra un umbral numérico.
OSCILLATORS: dict[str, dict] = {
    "RSI": {"compute": _rsi, "params": {"window": ("int", 7, 21)}, "threshold": (15.0, 85.0)},
    "STOCHRSI": {"compute": _stochrsi, "params": {"window": ("int", 7, 21)}, "threshold": (10.0, 90.0)},
    "CCI": {"compute": _cci, "params": {"window": ("int", 14, 30)}, "threshold": (-150.0, 150.0)},
    "WILLR": {"compute": _willr, "params": {"window": ("int", 10, 21)}, "threshold": (-90.0, -10.0)},
    "ADX": {"compute": _adx, "params": {"window": ("int", 10, 30)}, "threshold": (15.0, 40.0)},
}

# Tipo precio: se cruzan entre sí (o contra el precio).
PRICE_LIKE: dict[str, dict] = {
    "PRICE": {"compute": _price, "params": {}},
    "SMA": {"compute": _sma, "params": {"window": ("int", 5, 100)}},
    "EMA": {"compute": _ema, "params": {"window": ("int", 5, 100)}},
    "BB_UPPER": {"compute": _bb_upper, "params": {"window": ("int", 10, 40), "dev": ("float", 1.5, 3.0)}},
    "BB_LOWER": {"compute": _bb_lower, "params": {"window": ("int", 10, 40), "dev": ("float", 1.5, 3.0)}},
    "MACD_LINE": {"compute": _macd_line, "params": {"fast": ("int", 8, 16), "slow": ("int", 20, 34), "signal": ("int", 6, 12)}},
    "MACD_SIGNAL": {"compute": _macd_signal, "params": {"fast": ("int", 8, 16), "slow": ("int", 20, 34), "signal": ("int", 6, 12)}},
}

_ALL = {**OSCILLATORS, **PRICE_LIKE}
THRESHOLD_OPS = ("gt", "lt")
CROSS_OPS = ("cross_above", "cross_below")
COMBINES = ("AND", "OR")
_MAX_CONDITIONS = 3


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


def random_condition(rng: np.random.Generator) -> dict:
    """Condición aleatoria legal (umbral o cruce, equiprobables)."""
    return _random_threshold_condition(rng) if rng.random() < 0.5 else _random_cross_condition(rng)


def _random_block(rng: np.random.Generator) -> dict:
    k = int(rng.integers(1, _MAX_CONDITIONS + 1))
    return {
        "combine": str(rng.choice(COMBINES)),
        "conditions": [random_condition(rng) for _ in range(k)],
    }


def random_spec(rng: np.random.Generator) -> dict:
    """Genera un StrategySpec aleatorio legal."""
    return {"entry": _random_block(rng), "exit": _random_block(rng)}


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
    if c.get("type") == "cross":
        if c.get("op") not in CROSS_OPS:
            return False
        for side in ("a", "b"):
            leg = c.get(side, {})
            if leg.get("indicator") not in PRICE_LIKE:
                return False
            if not _validate_params(leg["indicator"], leg.get("params", {})):
                return False
        return c["a"]["indicator"] != c["b"]["indicator"] or c["a"]["params"] != c["b"]["params"]
    return False


def _validate_block(block: dict) -> bool:
    if block.get("combine") not in COMBINES:
        return False
    conds = block.get("conditions", [])
    if not (1 <= len(conds) <= _MAX_CONDITIONS):
        return False
    return all(_validate_condition(c) for c in conds)


def validate_spec(spec: dict) -> bool:
    """True si el spec es estructuralmente legal y todos sus bloques válidos."""
    if not isinstance(spec, dict) or "entry" not in spec or "exit" not in spec:
        return False
    return _validate_block(spec["entry"]) and _validate_block(spec["exit"])


# ═══════════════════════════════════════════════════════════════════
# Compilación a señales (intérprete causal, sin lookahead)
# ═══════════════════════════════════════════════════════════════════

def _series(df: pd.DataFrame, indicator: str, params: dict, cache: dict) -> np.ndarray:
    key = (indicator, tuple(sorted(params.items())))
    if key not in cache:
        cache[key] = np.asarray(_ALL[indicator]["compute"](df, params), dtype=float)
    return cache[key]


def _condition_bool(df: pd.DataFrame, c: dict, cache: dict) -> np.ndarray:
    if c["type"] == "threshold":
        s = _series(df, c["indicator"], c["params"], cache)
        # Comparaciones con NaN dan False en numpy (el warm-up no dispara señal)
        return s > c["threshold"] if c["op"] == "gt" else s < c["threshold"]
    # cruce: solo en la vela del cruce (i-1 al lado opuesto, i al lado nuevo)
    a = _series(df, c["a"]["indicator"], c["a"]["params"], cache)
    b = _series(df, c["b"]["indicator"], c["b"]["params"], cache)
    diff = a - b
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
    arrow = "cruza arriba" if c["op"] == "cross_above" else "cruza abajo"
    return f"{_describe_indicator(c['a'])} {arrow} {_describe_indicator(c['b'])}"


def describe_spec(spec: dict) -> str:
    """Descripción en español legible de la lógica de la estrategia."""
    def block(b):
        sep = " Y " if b["combine"] == "AND" else " O "
        return sep.join(_describe_condition(c) for c in b["conditions"])
    return f"ENTRAR si {block(spec['entry'])}; SALIR si {block(spec['exit'])}"


def max_warmup(spec: dict) -> int:
    """Mayor ventana usada por el spec (velas de calentamiento antes de operar)."""
    longest = 1
    def scan(c):
        nonlocal longest
        legs = [c] if c["type"] == "threshold" else [c["a"], c["b"]]
        for leg in legs:
            for v in leg["params"].values():
                longest = max(longest, int(v))
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
            if c["type"] == "threshold":
                for k, v in c["params"].items():
                    c["params"][k] = _jitter_value(c["indicator"], k, v, rng)
            else:
                for leg in (c["a"], c["b"]):
                    for k, v in leg["params"].items():
                        leg["params"][k] = _jitter_value(leg["indicator"], k, v, rng)
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
    ]
