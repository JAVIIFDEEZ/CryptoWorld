"""
price_patterns.py — Acción del precio como vocabulario del generador.

El catálogo de indicadores describe el mercado con **niveles**: un RSI vale 32,
una media vale 104. Hay una familia entera de información que ese vocabulario no
puede expresar, porque no es un nivel sino un **suceso con estructura**: que una
vela se trague a la anterior, que el precio perfore un mínimo y vuelva dentro,
que quede un hueco sin negociar entre dos velas. Un generador que solo combina
osciladores no puede descubrir esas estrategias por mucho que evolucione — no
están en su idioma.

Este módulo añade ese idioma. Cada detector devuelve un **array booleano** por
vela, y el spec los usa mediante la condición `pattern`.

Dos reglas que cumplen todos, sin excepción
───────────────────────────────────────────
· **Causalidad estricta.** Un detector solo puede mirar velas ≤ i. Es fácil
  escribir un detector de patrones que use la vela siguiente para «confirmar»
  —de hecho es como se explican en casi toda la literatura— y el backtest
  resultante es ficción. Aquí, si un patrón necesita confirmación, la señal se
  emite en la vela que la aporta, no retroactivamente en la que lo originó.
· **Sin parámetros mágicos.** Todo umbral (qué es un cuerpo «pequeño», cuánta
  mecha es «larga») es proporcional al rango de la propia vela o a la
  volatilidad reciente, nunca un porcentaje fijo. Un 0,1 % significa cosas
  distintas en BTC y en una altcoin, y distintas en 2021 y en 2024.

Sobre la nomenclatura
─────────────────────
Buena parte de estos conceptos vienen del price action moderno (FVG, order
block, liquidity sweep, AMD/Power of Three, CRT). Se implementan por su
**definición mecánica**, que es objetiva y comprobable, sin ninguna afirmación
sobre por qué funcionarían. Si tienen edge lo dirá el gating, igual que con
cualquier otro bloque; el generador no los privilegia.

Capa de dominio: NumPy puro.
"""

from __future__ import annotations

import numpy as np


# ═══════════════════════════════════════════════════════════════════
# Utilidades comunes
# ═══════════════════════════════════════════════════════════════════

def _ohlc(df):
    """Arrays OHLC del DataFrame, con repliegue al cierre si falta alguno."""
    close = np.asarray(df["close"], dtype=float)
    open_ = np.asarray(df["open"], dtype=float) if "open" in df else close
    high = np.asarray(df["high"], dtype=float) if "high" in df else close
    low = np.asarray(df["low"], dtype=float) if "low" in df else close
    return open_, high, low, close


def _body(open_, close):
    return np.abs(close - open_)


def _range(high, low):
    """Rango de la vela, con suelo para no dividir por cero en velas planas."""
    rng = high - low
    return np.where(rng > 0, rng, np.finfo(float).eps)


def _rolling_max(arr: np.ndarray, window: int, shift: int = 1) -> np.ndarray:
    """
    Máximo de las `window` velas ANTERIORES a cada índice.

    El desplazamiento por defecto es lo que separa «rompo el máximo previo» de
    «soy el máximo», que es una tautología: sin él, toda vela que marca un nuevo
    extremo cumpliría su propia condición de ruptura.

    Va por pandas y no por un bucle porque estos detectores se evalúan dentro
    del GA: miles de genomas × varios tramos walk-forward cada uno. Un bucle de
    Python aquí cuesta ~8 ms por llamada, que multiplicado por el presupuesto de
    una generación exhaustiva son horas.
    """
    import pandas as pd
    return pd.Series(arr, dtype=float).rolling(int(window)).max().shift(int(shift)).to_numpy()


def _rolling_min(arr: np.ndarray, window: int, shift: int = 1) -> np.ndarray:
    """Mínimo de las `window` velas anteriores (ver `_rolling_max`)."""
    import pandas as pd
    return pd.Series(arr, dtype=float).rolling(int(window)).min().shift(int(shift)).to_numpy()


def _false(n: int) -> np.ndarray:
    return np.zeros(n, dtype=bool)


# ═══════════════════════════════════════════════════════════════════
# Patrones de vela japonesa
# ═══════════════════════════════════════════════════════════════════

def bullish_engulfing(df, **_) -> np.ndarray:
    """
    Vela alcista cuyo cuerpo envuelve al cuerpo bajista anterior.

    Se exige que el cuerpo previo tenga tamaño real (≥ 10 % de su rango): una
    vela prácticamente sin cuerpo se «envuelve» sin esfuerzo y el patrón
    dispararía en cualquier lateral.
    """
    o, h, l, c = _ohlc(df)
    n = c.size
    if n < 2:
        return _false(n)

    prev_bear = np.zeros(n, dtype=bool)
    prev_bear[1:] = c[:-1] < o[:-1]
    prev_has_body = np.zeros(n, dtype=bool)
    prev_has_body[1:] = _body(o[:-1], c[:-1]) >= 0.1 * _range(h[:-1], l[:-1])

    engulfs = np.zeros(n, dtype=bool)
    engulfs[1:] = (c[1:] >= o[:-1]) & (o[1:] <= c[:-1])
    return (c > o) & prev_bear & prev_has_body & engulfs


def bearish_engulfing(df, **_) -> np.ndarray:
    """Espejo del anterior: vela bajista que envuelve al cuerpo alcista previo."""
    o, h, l, c = _ohlc(df)
    n = c.size
    if n < 2:
        return _false(n)

    prev_bull = np.zeros(n, dtype=bool)
    prev_bull[1:] = c[:-1] > o[:-1]
    prev_has_body = np.zeros(n, dtype=bool)
    prev_has_body[1:] = _body(o[:-1], c[:-1]) >= 0.1 * _range(h[:-1], l[:-1])

    engulfs = np.zeros(n, dtype=bool)
    engulfs[1:] = (c[1:] <= o[:-1]) & (o[1:] >= c[:-1])
    return (c < o) & prev_bull & prev_has_body & engulfs


def hammer(df, wick_ratio: float = 2.0, **_) -> np.ndarray:
    """
    Martillo / pin bar alcista: mecha inferior larga, cuerpo arriba.

    La mecha inferior mide `wick_ratio` veces el cuerpo como mínimo, y el cuerpo
    queda en el tercio superior de la vela. Lo que describe es un rechazo: el
    precio bajó y fue devuelto dentro de la misma vela.
    """
    o, h, l, c = _ohlc(df)
    body = _body(o, c)
    rng = _range(h, l)
    lower = np.minimum(o, c) - l
    upper = h - np.maximum(o, c)
    return (lower >= wick_ratio * np.maximum(body, rng * 0.05)) & (upper <= body) & (body > 0)


def shooting_star(df, wick_ratio: float = 2.0, **_) -> np.ndarray:
    """Espejo bajista del martillo: mecha superior larga, cuerpo abajo."""
    o, h, l, c = _ohlc(df)
    body = _body(o, c)
    rng = _range(h, l)
    lower = np.minimum(o, c) - l
    upper = h - np.maximum(o, c)
    return (upper >= wick_ratio * np.maximum(body, rng * 0.05)) & (lower <= body) & (body > 0)


def doji(df, max_body_pct: float = 0.1, **_) -> np.ndarray:
    """Cuerpo despreciable frente al rango: indecisión, apertura ≈ cierre."""
    o, h, l, c = _ohlc(df)
    return _body(o, c) <= max_body_pct * _range(h, l)


def inside_bar(df, **_) -> np.ndarray:
    """
    Vela contenida por completo en el rango de la anterior.

    Es compresión: el mercado deja de expandirse. Precede a las rupturas por lo
    mismo que las precede un rango estrecho — no porque «prediga», sino porque
    la volatilidad se agrupa.
    """
    _, h, l, c = _ohlc(df)
    n = c.size
    if n < 2:
        return _false(n)
    out = np.zeros(n, dtype=bool)
    out[1:] = (h[1:] <= h[:-1]) & (l[1:] >= l[:-1])
    return out


def outside_bar(df, **_) -> np.ndarray:
    """Vela cuyo rango engulle al de la anterior: expansión por ambos lados."""
    _, h, l, c = _ohlc(df)
    n = c.size
    if n < 2:
        return _false(n)
    out = np.zeros(n, dtype=bool)
    out[1:] = (h[1:] >= h[:-1]) & (l[1:] <= l[:-1])
    return out


# ═══════════════════════════════════════════════════════════════════
# Estructura y liquidez
# ═══════════════════════════════════════════════════════════════════

def fvg_bullish(df, **_) -> np.ndarray:
    """
    Fair Value Gap alcista: hueco de negociación en un impulso de tres velas.

    Se marca en la vela `i` cuando `low[i] > high[i-2]`: entre esos dos precios
    no ha habido negociación, y el movimiento fue lo bastante rápido como para
    saltárselo. La señal va en `i` —la vela que completa el hueco— y no en
    `i-1`, que es donde suele dibujarse: marcarla en `i-1` exigiría conocer `i`.
    """
    _, h, l, c = _ohlc(df)
    n = c.size
    if n < 3:
        return _false(n)
    out = np.zeros(n, dtype=bool)
    out[2:] = l[2:] > h[:-2]
    return out


def fvg_bearish(df, **_) -> np.ndarray:
    """FVG bajista: `high[i] < low[i-2]`."""
    _, h, l, c = _ohlc(df)
    n = c.size
    if n < 3:
        return _false(n)
    out = np.zeros(n, dtype=bool)
    out[2:] = h[2:] < l[:-2]
    return out


def liquidity_sweep_low(df, window: int = 20, **_) -> np.ndarray:
    """
    Barrida de liquidez bajo mínimos: perfora y vuelve dentro.

    La vela rompe el mínimo de las `window` anteriores **pero cierra por
    encima** de él. Es la firma mecánica de una ejecución de stops: el precio
    va a buscar las órdenes que hay debajo y no se queda allí.

    La condición de cierre es lo que separa esto de una ruptura bajista real. Sin
    ella el detector marcaría ambas cosas, que son opuestas.
    """
    _, h, l, c = _ohlc(df)
    prior_low = _rolling_min(l, window)
    with np.errstate(invalid="ignore"):
        out = (l < prior_low) & (c > prior_low)
    return np.where(np.isnan(prior_low), False, out)


def liquidity_sweep_high(df, window: int = 20, **_) -> np.ndarray:
    """Espejo: perfora el máximo previo y cierra por debajo."""
    _, h, l, c = _ohlc(df)
    prior_high = _rolling_max(h, window)
    with np.errstate(invalid="ignore"):
        out = (h > prior_high) & (c < prior_high)
    return np.where(np.isnan(prior_high), False, out)


def order_block_bullish(df, impulse: int = 3, **_) -> np.ndarray:
    """
    Mitigación de un bloque de órdenes alcista.

    Definición mecánica en dos tiempos, ambos pasados:
      1. Una vela **bajista** es seguida, en las `impulse` velas siguientes, de
         un movimiento que rompe su máximo. Esa vela queda marcada como bloque.
      2. La señal se emite cuando el precio **regresa** al rango de ese bloque
         (lo toca por debajo de su máximo y cierra por encima de su mínimo).

    El paso 2 es lo que hace la señal operable: el paso 1 solo se sabe a
    posteriori, así que un detector que marcara la propia vela del bloque
    estaría mirando el futuro. Aquí el bloque se **activa** al confirmarse y solo
    entonces empieza a poder emitir.
    """
    o, h, l, c = _ohlc(df)
    n = c.size
    if n < impulse + 2:
        return _false(n)

    out = np.zeros(n, dtype=bool)
    # Bloques ya confirmados y aún sin mitigar: (mínimo, máximo).
    blocks: list[tuple[float, float]] = []

    for i in range(n):
        # ── Confirmación de bloques (solo con velas pasadas) ──
        k = i - impulse
        if k >= 0 and c[k] < o[k]:
            # ¿El impulso posterior rompió el máximo de esa vela bajista?
            if np.max(h[k + 1:i + 1]) > h[k]:
                blocks.append((float(l[k]), float(h[k])))

        # ── ¿El precio ha vuelto a alguno? ──
        remaining = []
        touched = False
        for lo_b, hi_b in blocks:
            if l[i] <= hi_b and c[i] >= lo_b:
                touched = True          # mitigado: deja de estar disponible
            else:
                remaining.append((lo_b, hi_b))
        blocks = remaining[-20:]        # memoria acotada: los 20 más recientes
        out[i] = touched
    return out


def order_block_bearish(df, impulse: int = 3, **_) -> np.ndarray:
    """Espejo: vela alcista cuyo mínimo se rompe después, mitigada al volver."""
    o, h, l, c = _ohlc(df)
    n = c.size
    if n < impulse + 2:
        return _false(n)

    out = np.zeros(n, dtype=bool)
    blocks: list[tuple[float, float]] = []

    for i in range(n):
        k = i - impulse
        if k >= 0 and c[k] > o[k]:
            if np.min(l[k + 1:i + 1]) < l[k]:
                blocks.append((float(l[k]), float(h[k])))

        remaining = []
        touched = False
        for lo_b, hi_b in blocks:
            if h[i] >= lo_b and c[i] <= hi_b:
                touched = True
            else:
                remaining.append((lo_b, hi_b))
        blocks = remaining[-20:]
        out[i] = touched
    return out


def crt(df, **_) -> np.ndarray:
    """
    Candle Range Theory: la vela toma la liquidez de la anterior y vuelve dentro.

    Mecánicamente: perfora el máximo **o** el mínimo de la vela previa y cierra
    dentro de su rango. Es el mismo esqueleto que la barrida de liquidez, pero
    con la vela anterior como referencia en lugar de un rango de N velas — la
    versión de grano fino del mismo suceso.
    """
    _, h, l, c = _ohlc(df)
    n = c.size
    if n < 2:
        return _false(n)
    out = np.zeros(n, dtype=bool)
    swept = (h[1:] > h[:-1]) | (l[1:] < l[:-1])
    inside = (c[1:] <= h[:-1]) & (c[1:] >= l[:-1])
    out[1:] = swept & inside
    return out


def power_of_three(df, window: int = 6, **_) -> np.ndarray:
    """
    Power of Three (acumulación → manipulación → distribución), o AMD.

    Sobre una ventana de `window` velas ya cerradas se busca la secuencia:

      1. **Acumulación** — el primer tercio comprime: su rango es menor que el
         de la ventana completa.
      2. **Manipulación** — el tercio central perfora el mínimo de la fase de
         acumulación (barrida a la baja).
      3. **Distribución** — la vela actual cierra por encima del máximo de la
         acumulación, en dirección contraria a la manipulación.

    Es una traducción literal y comprobable del concepto, sin ninguna
    afirmación sobre por qué funcionaría. La variante bajista es su espejo y se
    expone como `power_of_three_bearish`.
    """
    return _amd(df, window, bullish=True)


def power_of_three_bearish(df, window: int = 6, **_) -> np.ndarray:
    """Espejo bajista: manipulación al alza y distribución a la baja."""
    return _amd(df, window, bullish=False)


def _amd(df, window: int, bullish: bool) -> np.ndarray:
    """
    Las tres fases, en aritmética de ventanas móviles.

    Para la vela `i` con ventana `w` y tercio `t`, todas las referencias son
    pasadas y se expresan como un rolling desplazado:

      · acumulación  = velas [i−w, i−w+t−1]  → rolling(t)   desplazado w−t+1
      · manipulación = velas [i−w+t, i−1]    → rolling(w−t) desplazado 1
      · ventana      = velas [i−w, i−1]      → rolling(w)   desplazado 1

    El «+1» de la acumulación no es un detalle: `shift(s)` en `i` devuelve el
    rolling cerrado en `i−s`, y esa ventana termina en `i−w+t−1`, no en `i−w+t`.
    Sin él, la fase de acumulación se solapaba una vela con la de manipulación.

    Escrito como bucle costaba ~37 ms por llamada; dentro del GA eso lo hacía
    inviable, y un bloque que el generador no puede permitirse evaluar es un
    bloque que no existe.
    """
    _o, h, l, c = _ohlc(df)
    n = c.size
    third = max(1, int(window) // 3)
    mid_len = int(window) - third
    if n < window + 1 or mid_len < 1:
        return _false(n)

    acc_h = _rolling_max(h, third, shift=window - third + 1)
    acc_l = _rolling_min(l, third, shift=window - third + 1)
    win_h = _rolling_max(h, window, shift=1)
    win_l = _rolling_min(l, window, shift=1)
    mid_h = _rolling_max(h, mid_len, shift=1)
    mid_l = _rolling_min(l, mid_len, shift=1)

    with np.errstate(invalid="ignore"):
        win_range = win_h - win_l
        # Sin compresión inicial no hay acumulación: la secuencia sería solo un
        # movimiento más al que ponerle un nombre de tres fases.
        compressed = (win_range > 0) & ((acc_h - acc_l) < win_range * 0.6)
        if bullish:
            phases = (mid_l < acc_l) & (c > acc_h)
        else:
            phases = (mid_h > acc_h) & (c < acc_l)
        out = compressed & phases

    return np.where(np.isfinite(acc_h) & np.isfinite(acc_l)
                    & np.isfinite(mid_h) & np.isfinite(mid_l)
                    & np.isfinite(win_range), out, False)


def opening_range_break_up(df, bars: int = 6, **_) -> np.ndarray:
    """
    Opening Range Breakout al alza.

    El rango de apertura son las primeras `bars` velas de cada día UTC; la señal
    se emite cuando una vela POSTERIOR del mismo día cierra por encima del
    máximo de ese rango, y solo la **primera vez** de cada día: un ORB que
    dispara diez veces en una sesión no es una ruptura, es una tendencia ya en
    marcha.

    En un mercado 24/7 el «día» es una convención, y se declara como tal: el
    corte UTC no marca ninguna apertura real de sesión. Sigue siendo útil porque
    la actividad cripto sí tiene estacionalidad diaria, pero no es lo mismo que
    la apertura de un mercado con horario.

    Efecto de borde, dicho explícitamente: si el DataFrame empieza a media
    sesión —como ocurre en cada tramo del walk-forward— la primera vela del
    tramo se toma como apertura de día. No es una fuga (solo mira hacia atrás),
    pero sí hace que el primer día de un tramo no sea idéntico al mismo día
    dentro de la serie completa. Es el mismo tipo de artefacto de arranque que
    tiene una media de 200 velas al principio de un tramo, y se acepta por la
    misma razón: eliminarlo exigiría datos anteriores al tramo, que es
    justamente lo que el tramo no debe ver.
    """
    return _orb(df, bars, up=True)


def opening_range_break_down(df, bars: int = 6, **_) -> np.ndarray:
    """Espejo: cierre por debajo del mínimo del rango de apertura."""
    return _orb(df, bars, up=False)


_DAY_MS = 86_400_000


def _orb(df, bars: int, up: bool) -> np.ndarray:
    _, h, l, c = _ohlc(df)
    n = c.size
    out = np.zeros(n, dtype=bool)
    if "timestamp" not in getattr(df, "columns", ()) or n == 0:
        return out

    days = (np.asarray(df["timestamp"], dtype=np.int64) // _DAY_MS)
    day_start = 0
    fired = False
    for i in range(n):
        if i == 0 or days[i] != days[i - 1]:
            day_start = i
            fired = False
        offset = i - day_start
        if offset < bars or fired:
            continue
        rng_h = float(np.max(h[day_start:day_start + bars]))
        rng_l = float(np.min(l[day_start:day_start + bars]))
        if (c[i] > rng_h) if up else (c[i] < rng_l):
            out[i] = True
            fired = True
    return out


def fib_discount(df, window: int = 60, lower: float = 0.618, upper: float = 0.786, **_) -> np.ndarray:
    """
    El precio está en la zona de descuento del swing reciente.

    El catálogo ya expone `FIB_RETR` como **nivel** cruzable. Esto es la otra
    mitad del concepto: la **zona**. Operar «en descuento» no es cruzar el
    0.618, es estar entre el 0.618 y el 0.786 del swing — un estado, no un
    suceso, y por eso no se puede expresar con un cruce.

    El swing se mide sobre las `window` velas anteriores (desplazado una vela,
    para que el extremo no sea la propia vela evaluada).
    """
    _, h, l, c = _ohlc(df)
    hi = _rolling_max(h, window)
    lo = _rolling_min(l, window)
    span = hi - lo
    with np.errstate(invalid="ignore"):
        # Retroceso desde el máximo: 0 en el máximo, 1 en el mínimo.
        retr = (hi - c) / np.where(span > 0, span, np.nan)
        out = (retr >= lower) & (retr <= upper)
    return np.where(np.isfinite(retr), out, False)


def fib_premium(df, window: int = 60, lower: float = 0.618, upper: float = 0.786, **_) -> np.ndarray:
    """Zona de premium: el espejo del descuento, medido desde el mínimo."""
    _, h, l, c = _ohlc(df)
    hi = _rolling_max(h, window)
    lo = _rolling_min(l, window)
    span = hi - lo
    with np.errstate(invalid="ignore"):
        retr = (c - lo) / np.where(span > 0, span, np.nan)
        out = (retr >= lower) & (retr <= upper)
    return np.where(np.isfinite(retr), out, False)


# ═══════════════════════════════════════════════════════════════════
# Catálogo
# ═══════════════════════════════════════════════════════════════════

# Cada entrada: función + espacio de parámetros evolucionable + calentamiento.
# `warmup` son las velas que el detector necesita antes de poder emitir; el
# generador lo usa para no evaluar una estrategia sobre su propio arranque.
PATTERNS: dict[str, dict] = {
    # ── Velas japonesas ──
    "BULL_ENGULF":   {"compute": bullish_engulfing, "params": {}, "warmup": 2},
    "BEAR_ENGULF":   {"compute": bearish_engulfing, "params": {}, "warmup": 2},
    "HAMMER":        {"compute": hammer, "params": {"wick_ratio": ("float", 1.5, 3.5)}, "warmup": 1},
    "SHOOTING_STAR": {"compute": shooting_star, "params": {"wick_ratio": ("float", 1.5, 3.5)}, "warmup": 1},
    "DOJI":          {"compute": doji, "params": {"max_body_pct": ("float", 0.05, 0.2)}, "warmup": 1},
    "INSIDE_BAR":    {"compute": inside_bar, "params": {}, "warmup": 2},
    "OUTSIDE_BAR":   {"compute": outside_bar, "params": {}, "warmup": 2},
    # ── Estructura y liquidez ──
    "FVG_BULL":      {"compute": fvg_bullish, "params": {}, "warmup": 3},
    "FVG_BEAR":      {"compute": fvg_bearish, "params": {}, "warmup": 3},
    "SWEEP_LOW":     {"compute": liquidity_sweep_low, "params": {"window": ("int", 10, 60)}, "warmup": 61},
    "SWEEP_HIGH":    {"compute": liquidity_sweep_high, "params": {"window": ("int", 10, 60)}, "warmup": 61},
    "OB_BULL":       {"compute": order_block_bullish, "params": {"impulse": ("int", 2, 6)}, "warmup": 10},
    "OB_BEAR":       {"compute": order_block_bearish, "params": {"impulse": ("int", 2, 6)}, "warmup": 10},
    "CRT":           {"compute": crt, "params": {}, "warmup": 2},
    "PO3_BULL":      {"compute": power_of_three, "params": {"window": ("int", 6, 24)}, "warmup": 25},
    "PO3_BEAR":      {"compute": power_of_three_bearish, "params": {"window": ("int", 6, 24)}, "warmup": 25},
    "ORB_UP":        {"compute": opening_range_break_up, "params": {"bars": ("int", 2, 12)}, "warmup": 13},
    "ORB_DOWN":      {"compute": opening_range_break_down, "params": {"bars": ("int", 2, 12)}, "warmup": 13},
    # ── Fibonacci como ZONA (el nivel ya está en el catálogo de indicadores) ──
    "FIB_DISCOUNT":  {"compute": fib_discount, "params": {"window": ("int", 30, 120)}, "warmup": 121},
    "FIB_PREMIUM":   {"compute": fib_premium, "params": {"window": ("int", 30, 120)}, "warmup": 121},
}


# Nombres legibles para la descripción en español de una estrategia.
PATTERN_LABELS: dict[str, str] = {
    "BULL_ENGULF": "envolvente alcista",
    "BEAR_ENGULF": "envolvente bajista",
    "HAMMER": "martillo (rechazo por abajo)",
    "SHOOTING_STAR": "estrella fugaz (rechazo por arriba)",
    "DOJI": "doji (indecisión)",
    "INSIDE_BAR": "vela interior (compresión)",
    "OUTSIDE_BAR": "vela envolvente (expansión)",
    "FVG_BULL": "hueco de valor alcista (FVG)",
    "FVG_BEAR": "hueco de valor bajista (FVG)",
    "SWEEP_LOW": "barrida de liquidez bajo mínimos",
    "SWEEP_HIGH": "barrida de liquidez sobre máximos",
    "OB_BULL": "vuelta a bloque de órdenes alcista",
    "OB_BEAR": "vuelta a bloque de órdenes bajista",
    "CRT": "toma del rango de la vela previa (CRT)",
    "PO3_BULL": "acumulación–manipulación–distribución alcista",
    "PO3_BEAR": "acumulación–manipulación–distribución bajista",
    "ORB_UP": "ruptura al alza del rango de apertura",
    "ORB_DOWN": "ruptura a la baja del rango de apertura",
    "FIB_DISCOUNT": "zona de descuento (Fibonacci 0.618–0.786)",
    "FIB_PREMIUM": "zona de premium (Fibonacci 0.618–0.786)",
}


def detect(df, name: str, params: dict | None = None) -> np.ndarray:
    """
    Evalúa un patrón del catálogo sobre el DataFrame.

    Un detector que falla devuelve todo False —nunca dispara— en vez de romper
    el backtest: es la misma política que el catálogo de indicadores sigue con
    las ventanas demasiado cortas, y por la misma razón. Una estrategia que no
    puede evaluarse debe morir en el gating por no operar, no reventar la
    generación entera.
    """
    entry = PATTERNS.get(name)
    if entry is None:
        return _false(len(df))
    try:
        out = np.asarray(entry["compute"](df, **(params or {})), dtype=bool)
    except Exception:  # noqa: BLE001 — ver docstring
        return _false(len(df))
    return out if out.size == len(df) else _false(len(df))


def occurred_within(flags: np.ndarray, lookback: int) -> np.ndarray:
    """
    «El patrón ocurrió en alguna de las últimas `lookback` velas.»

    Sin esto, combinar dos patrones con Y sería casi siempre falso: son sucesos
    puntuales y la probabilidad de que coincidan en la misma vela es ínfima. Con
    la ventana, el generador puede expresar secuencias reales —«hubo barrida y
    ahora envolvente»— que es como se usan de verdad.

    La ventana mira hacia ATRÁS, nunca hacia delante: incluye la vela actual y
    las `lookback − 1` anteriores.
    """
    flags = np.asarray(flags, dtype=bool)
    if lookback <= 1 or flags.size == 0:
        return flags
    out = flags.copy()
    for k in range(1, int(lookback)):
        shifted = np.zeros_like(flags)
        shifted[k:] = flags[:-k]
        out |= shifted
    return out
