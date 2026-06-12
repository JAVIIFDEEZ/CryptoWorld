"""
confluence_service.py — Motor de la Confluence Card.

Agrega en una sola ficha técnica accionable todo el análisis de un activo:
tendencia de fondo, soportes/resistencias por pivotes, retrocesos de
Fibonacci, resumen multi-indicador (reutiliza calculate_signals_dashboard)
y un veredicto global con nivel de confianza. Genera además una narrativa
determinista en español a partir de los datos (plantillas interpoladas,
sin LLM): la misma lógica alimenta el endpoint REST y la landing SEO.

Principio aplicado: Domain Service (Arquitectura Hexagonal).
No accede a BD ni a HTTP — recibe DataFrames y devuelve resultados puros.
"""

import math
from datetime import datetime, timezone

import pandas as pd
import ta as ta_lib

from core.domain.services.technical_analysis_service import (
    SIGNAL_BUY,
    SIGNAL_NEUTRAL,
    SIGNAL_SELL,
    SIGNAL_STRONG_BUY,
    SIGNAL_STRONG_SELL,
    calculate_signals_dashboard,
)

# Tendencias
TREND_UP = "ALCISTA"
TREND_SIDEWAYS = "LATERAL"
TREND_DOWN = "BAJISTA"

# Ratios clásicos de retroceso de Fibonacci
_FIB_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786)

# Tolerancia de agrupación de pivotes en un mismo nivel (en % del precio)
_CLUSTER_TOLERANCE_PCT = 0.75


def _round_price(value: float) -> float:
    """Redondeo adaptado a la magnitud (BTC a 2 decimales, shitcoins a 6)."""
    if value is None or math.isnan(value) or math.isinf(value):
        return 0.0
    abs_v = abs(value)
    decimals = 2 if abs_v >= 1 else 4 if abs_v >= 0.01 else 6
    return round(float(value), decimals)


def _fmt(value: float) -> str:
    """Formato es-ES legible para la narrativa: 65.432,10 / 0,0345."""
    abs_v = abs(value)
    decimals = 2 if abs_v >= 1 else 4 if abs_v >= 0.01 else 6
    text = f"{value:,.{decimals}f}"
    # Convención española: punto de miles, coma decimal
    return text.replace(",", "@").replace(".", ",").replace("@", ".")


# ═══════════════════════════════════════════════════════════════════
# 1. SOPORTES Y RESISTENCIAS POR PIVOTES (swing highs / swing lows)
# ═══════════════════════════════════════════════════════════════════

def _find_pivots(values, window: int, find_high: bool) -> list[float]:
    """
    Un pivote es una vela cuyo high (o low) es el extremo de su entorno
    de ±window velas. Detecta los puntos de giro del precio.
    """
    pivots: list[float] = []
    n = len(values)
    for i in range(window, n - window):
        segment = values[i - window : i + window + 1]
        extreme = max(segment) if find_high else min(segment)
        if values[i] == extreme:
            pivots.append(float(values[i]))
    return pivots


def _cluster_levels(levels: list[float], tolerance_pct: float) -> list[dict]:
    """
    Agrupa pivotes cercanos en un único nivel: cuantas más veces ha girado
    el precio en una zona (touches), más relevante es el nivel.
    """
    if not levels:
        return []
    ordered = sorted(levels)
    clusters: list[list[float]] = [[ordered[0]]]
    for level in ordered[1:]:
        center = sum(clusters[-1]) / len(clusters[-1])
        if center > 0 and abs(level - center) / center * 100 <= tolerance_pct:
            clusters[-1].append(level)
        else:
            clusters.append([level])
    return [
        {"level": _round_price(sum(c) / len(c)), "touches": len(c)}
        for c in clusters
    ]


def calculate_support_resistance(
    df: pd.DataFrame, window: int = 5, max_levels: int = 3
) -> dict:
    """
    Soportes (pivotes de mínimos bajo el precio actual) y resistencias
    (pivotes de máximos sobre el precio actual), ordenados por cercanía.
    """
    last_price = float(df["close"].iloc[-1])

    pivot_highs = _find_pivots(df["high"].values, window, find_high=True)
    pivot_lows = _find_pivots(df["low"].values, window, find_high=False)

    supports = [
        c for c in _cluster_levels(pivot_lows, _CLUSTER_TOLERANCE_PCT)
        if c["level"] < last_price
    ]
    resistances = [
        c for c in _cluster_levels(pivot_highs, _CLUSTER_TOLERANCE_PCT)
        if c["level"] > last_price
    ]

    # Soportes: de mayor a menor (el primero es el más cercano por abajo).
    # Resistencias: de menor a mayor (la primera es la más cercana por arriba).
    supports.sort(key=lambda c: c["level"], reverse=True)
    resistances.sort(key=lambda c: c["level"])

    for level in supports + resistances:
        level["distance_pct"] = round(
            (level["level"] - last_price) / last_price * 100, 2
        )

    return {
        "supports": supports[:max_levels],
        "resistances": resistances[:max_levels],
        "pivot_window": window,
    }


# ═══════════════════════════════════════════════════════════════════
# 2. RETROCESOS DE FIBONACCI
# ═══════════════════════════════════════════════════════════════════

def calculate_fibonacci_levels(df: pd.DataFrame, lookback: int = 180) -> dict:
    """
    Niveles de retroceso sobre el último impulso relevante: el rango entre
    el mínimo y el máximo de las últimas `lookback` velas. La dirección del
    impulso (qué extremo es más reciente) decide desde dónde se mide.
    """
    data = df.tail(lookback)
    last_price = float(df["close"].iloc[-1])

    high_idx = data["high"].idxmax()
    low_idx = data["low"].idxmin()
    swing_high = float(data["high"].max())
    swing_low = float(data["low"].min())
    price_range = swing_high - swing_low

    # Mínimo anterior al máximo → el impulso dominante fue alcista:
    # los retrocesos se miden descendiendo desde el máximo.
    is_upswing = low_idx < high_idx

    def _label(ratio: float) -> str:
        return f"{ratio * 100:.1f}".replace(".", ",") + "%"

    if price_range <= 0:
        levels = []
    elif is_upswing:
        levels = [
            {"ratio": r, "label": _label(r), "price": _round_price(swing_high - price_range * r)}
            for r in _FIB_RATIOS
        ]
    else:
        levels = [
            {"ratio": r, "label": _label(r), "price": _round_price(swing_low + price_range * r)}
            for r in _FIB_RATIOS
        ]

    nearest = (
        min(levels, key=lambda l: abs(l["price"] - last_price)) if levels else None
    )

    return {
        "swing_high": _round_price(swing_high),
        "swing_low": _round_price(swing_low),
        "direction": "ALCISTA" if is_upswing else "BAJISTA",
        "lookback": int(min(lookback, len(df))),
        "levels": levels,
        "nearest_level": nearest,
    }


# ═══════════════════════════════════════════════════════════════════
# 3. CLASIFICACIÓN DE TENDENCIA
# ═══════════════════════════════════════════════════════════════════

def classify_trend(df: pd.DataFrame) -> dict:
    """
    Tendencia de fondo: posición del precio respecto a la SMA200 (o la más
    larga disponible) combinada con la pendiente reciente de la EMA50.
    """
    close = df["close"]
    last_price = float(close.iloc[-1])

    sma_period = 200 if len(close) >= 200 else max(20, len(close) // 2)
    sma = ta_lib.trend.SMAIndicator(close, window=sma_period).sma_indicator()
    sma_val = float(sma.iloc[-1])

    ema_period = 50 if len(close) >= 60 else max(10, len(close) // 3)
    ema = ta_lib.trend.EMAIndicator(close, window=ema_period).ema_indicator()
    slope_lookback = min(10, len(ema) - 1)
    ema_now = float(ema.iloc[-1])
    ema_before = float(ema.iloc[-1 - slope_lookback])
    slope_pct = (
        (ema_now - ema_before) / ema_before * 100 if ema_before else 0.0
    )

    price_vs_sma_pct = (
        (last_price - sma_val) / sma_val * 100 if sma_val else 0.0
    )

    if last_price > sma_val and slope_pct > 0.3:
        trend = TREND_UP
    elif last_price < sma_val and slope_pct < -0.3:
        trend = TREND_DOWN
    else:
        trend = TREND_SIDEWAYS

    return {
        "trend": trend,
        "sma_period": sma_period,
        "sma_value": _round_price(sma_val),
        "price_vs_sma_pct": round(price_vs_sma_pct, 2),
        "ema_period": ema_period,
        "ema_slope_pct": round(slope_pct, 2),
    }


# ═══════════════════════════════════════════════════════════════════
# 4. VEREDICTO GLOBAL CON CONFIANZA
# ═══════════════════════════════════════════════════════════════════

_BULLISH = (SIGNAL_BUY, SIGNAL_STRONG_BUY)
_BEARISH = (SIGNAL_SELL, SIGNAL_STRONG_SELL)


def _build_verdict(signals: dict, trend: dict) -> dict:
    """
    Veredicto = el del panel multi-indicador; la confianza mide cuántos
    indicadores apoyan la dirección dominante, con bonus/penalización
    según la tendencia de fondo confirme o contradiga.
    """
    summary = signals["summary"]
    verdict = summary["verdict"]
    total = summary["total"] or 1

    if verdict in _BULLISH:
        agreeing = summary["buy_count"]
    elif verdict in _BEARISH:
        agreeing = summary["sell_count"]
    else:
        agreeing = summary["neutral_count"]

    confidence = round(100 * agreeing / total)

    trend_agrees = (
        (verdict in _BULLISH and trend["trend"] == TREND_UP)
        or (verdict in _BEARISH and trend["trend"] == TREND_DOWN)
        or (verdict == SIGNAL_NEUTRAL and trend["trend"] == TREND_SIDEWAYS)
    )
    trend_contradicts = (
        (verdict in _BULLISH and trend["trend"] == TREND_DOWN)
        or (verdict in _BEARISH and trend["trend"] == TREND_UP)
    )
    if trend_agrees:
        confidence += 10
    elif trend_contradicts:
        confidence -= 10
    confidence = max(5, min(95, confidence))

    level = "ALTA" if confidence >= 70 else "MEDIA" if confidence >= 45 else "BAJA"

    return {
        "verdict": verdict,
        "confidence_pct": confidence,
        "confidence_level": level,
        "trend_agrees": trend_agrees,
    }


# ═══════════════════════════════════════════════════════════════════
# 5. NARRATIVA DETERMINISTA EN ESPAÑOL
# ═══════════════════════════════════════════════════════════════════

_VERDICT_ES = {
    SIGNAL_STRONG_BUY: "compra fuerte",
    SIGNAL_BUY: "compra",
    SIGNAL_NEUTRAL: "neutral",
    SIGNAL_SELL: "venta",
    SIGNAL_STRONG_SELL: "venta fuerte",
}

_TREND_ES = {
    TREND_UP: "alcista",
    TREND_SIDEWAYS: "lateral",
    TREND_DOWN: "bajista",
}


def _paragraph_intro(symbol: str, last_price: float, trend: dict, verdict: dict) -> str:
    trend_es = _TREND_ES[trend["trend"]]
    position = "por encima" if trend["price_vs_sma_pct"] >= 0 else "por debajo"
    slope = (
        "ascendente" if trend["ema_slope_pct"] > 0.3
        else "descendente" if trend["ema_slope_pct"] < -0.3
        else "plana"
    )
    return (
        f"{symbol} cotiza actualmente en {_fmt(last_price)} USD con una estructura "
        f"de fondo {trend_es} en gráfico diario. El precio se sitúa un "
        f"{_fmt(abs(trend['price_vs_sma_pct']))}% {position} de su media móvil de "
        f"{trend['sma_period']} sesiones ({_fmt(trend['sma_value'])} USD), mientras que la "
        f"EMA de {trend['ema_period']} periodos muestra una pendiente {slope} del "
        f"{_fmt(abs(trend['ema_slope_pct']))}% en las últimas diez sesiones. El consenso "
        f"de los indicadores técnicos arroja un veredicto de {_VERDICT_ES[verdict['verdict']]} "
        f"con una confianza del {verdict['confidence_pct']}% ({verdict['confidence_level'].lower()})."
    )


def _paragraph_indicators(signals: dict) -> str:
    summary = signals["summary"]
    parts = [
        f"De los {summary['total']} indicadores evaluados, {summary['buy_count']} "
        f"emiten señal de compra, {summary['sell_count']} de venta y "
        f"{summary['neutral_count']} se mantienen neutrales."
    ]
    by_name = {i["name"]: i for i in signals["indicators"]}

    rsi = by_name.get("RSI (14)")
    if rsi and isinstance(rsi["value"], (int, float)):
        zone = (
            "sobrecompra (por encima de 70)" if rsi["value"] > 70
            else "sobreventa (por debajo de 30)" if rsi["value"] < 30
            else "territorio neutral"
        )
        parts.append(
            f"El RSI de 14 periodos marca {_fmt(rsi['value'])}, situándose en {zone}."
        )

    macd = by_name.get("MACD (12,26,9)")
    if macd:
        momentum = "alcista" if macd["signal"] == SIGNAL_BUY else "bajista"
        parts.append(
            f"El MACD confirma un momentum {momentum} a corto plazo."
        )

    sma50 = by_name.get("SMA (50)")
    if sma50 and isinstance(sma50["value"], (int, float)):
        rel = "por encima" if sma50["signal"] == SIGNAL_BUY else "por debajo"
        parts.append(
            f"Respecto a las medias móviles, el precio se mantiene {rel} de la "
            f"SMA50 ({_fmt(sma50['value'])} USD), un nivel que los operadores "
            f"suelen vigilar como referencia de medio plazo."
        )
    return " ".join(parts)


def _paragraph_levels(symbol: str, last_price: float, sr: dict) -> str:
    parts = []
    if sr["supports"]:
        s = sr["supports"][0]
        extra = (
            f", una zona que ha frenado las caídas en {s['touches']} ocasiones"
            if s["touches"] > 1 else ""
        )
        parts.append(
            f"El soporte más inmediato se encuentra en {_fmt(s['level'])} USD "
            f"(a un {_fmt(abs(s['distance_pct']))}% del precio actual){extra}."
        )
        if len(sr["supports"]) > 1:
            parts.append(
                f"Por debajo, el siguiente apoyo relevante aparece en "
                f"{_fmt(sr['supports'][1]['level'])} USD."
            )
    else:
        parts.append(
            f"No se detectan soportes históricos relevantes por debajo del precio "
            f"actual en el periodo analizado, lo que sugiere cautela ante retrocesos."
        )

    if sr["resistances"]:
        r = sr["resistances"][0]
        extra = (
            f", testeada {r['touches']} veces"
            if r["touches"] > 1 else ""
        )
        parts.append(
            f"Al alza, la primera resistencia se sitúa en {_fmt(r['level'])} USD "
            f"(un {_fmt(abs(r['distance_pct']))}% por encima){extra}; su ruptura "
            f"abriría la puerta a una extensión del movimiento."
        )
    else:
        parts.append(
            f"{symbol} cotiza sin resistencias históricas por encima en el rango "
            f"analizado: el precio se mueve en zona de máximos, donde el descubrimiento "
            f"de precio manda y conviene gestionar el riesgo con especial disciplina."
        )
    return " ".join(parts)


def _paragraph_fibonacci(fibo: dict) -> str:
    if not fibo["levels"]:
        return (
            "El rango de precios del periodo analizado es demasiado estrecho para "
            "trazar retrocesos de Fibonacci con fiabilidad."
        )
    direction = "alcista" if fibo["direction"] == "ALCISTA" else "bajista"
    text = (
        f"Sobre el último impulso {direction}, comprendido entre {_fmt(fibo['swing_low'])} "
        f"y {_fmt(fibo['swing_high'])} USD, los retrocesos de Fibonacci dibujan la hoja "
        f"de ruta de las correcciones: el 38,2% pasa por {_fmt(fibo['levels'][1]['price'])} USD "
        f"y el nivel dorado del 61,8% por {_fmt(fibo['levels'][3]['price'])} USD."
    )
    if fibo["nearest_level"]:
        n = fibo["nearest_level"]
        ratio_pct = f"{n['ratio'] * 100:.1f}".replace(".", ",")
        text += (
            f" El nivel más próximo a la cotización actual es el retroceso del "
            f"{ratio_pct}% ({_fmt(n['price'])} USD), un área a vigilar como posible "
            f"zona de reacción del precio."
        )
    return text


def _paragraph_conclusion(symbol: str, verdict: dict, trend: dict) -> str:
    if verdict["trend_agrees"]:
        coherence = (
            "Las señales de corto plazo y la estructura de fondo apuntan en la misma "
            "dirección, lo que refuerza la lectura actual"
        )
    else:
        coherence = (
            "Las señales de corto plazo y la tendencia de fondo no están plenamente "
            "alineadas, por lo que conviene esperar confirmación antes de tomar decisiones"
        )
    return (
        f"En conjunto, la confluencia técnica de {symbol} se resume en un sesgo de "
        f"{_VERDICT_ES[verdict['verdict']]} dentro de un contexto "
        f"{_TREND_ES[trend['trend']]}. {coherence}. Este análisis se genera "
        f"automáticamente a partir de datos de mercado y tiene fines exclusivamente "
        f"informativos y educativos: no constituye asesoramiento financiero ni una "
        f"recomendación de inversión."
    )


def build_narrative(
    symbol: str,
    last_price: float,
    trend: dict,
    sr: dict,
    fibo: dict,
    signals: dict,
    verdict: dict,
) -> list[str]:
    """Análisis en español (4-5 párrafos, ~250-400 palabras), 100% determinista."""
    return [
        _paragraph_intro(symbol, last_price, trend, verdict),
        _paragraph_indicators(signals),
        _paragraph_levels(symbol, last_price, sr),
        _paragraph_fibonacci(fibo),
        _paragraph_conclusion(symbol, verdict, trend),
    ]


# ═══════════════════════════════════════════════════════════════════
# 6. AGREGADOR: LA CONFLUENCE CARD
# ═══════════════════════════════════════════════════════════════════

def build_confluence_card(df: pd.DataFrame, symbol: str) -> dict:
    """
    Construye la ficha de confluencia completa de un activo a partir de su
    DataFrame OHLCV. Única fuente de verdad para el endpoint REST y la
    landing SEO (cero duplicación de lógica).
    """
    symbol = symbol.upper()
    last_price = float(df["close"].iloc[-1])

    trend = classify_trend(df)
    sr = calculate_support_resistance(df)
    fibo = calculate_fibonacci_levels(df)
    signals = calculate_signals_dashboard(df)
    verdict = _build_verdict(signals, trend)
    paragraphs = build_narrative(symbol, last_price, trend, sr, fibo, signals, verdict)

    return {
        "symbol": symbol,
        "last_price": _round_price(last_price),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "trend": trend,
        "support_resistance": sr,
        "fibonacci": fibo,
        "signals": signals,
        "verdict": verdict,
        # Narrativa corta (card) y análisis completo (landing SEO)
        "narrative": paragraphs[0],
        "analysis_paragraphs": paragraphs,
    }
