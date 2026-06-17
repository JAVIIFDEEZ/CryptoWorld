"""
technical_analysis_service.py — Motor de análisis técnico.

Calcula indicadores reales sobre datos OHLCV usando la librería `ta`.
Genera señales (COMPRA / VENTA / NEUTRAL) y detecta patrones de velas.
Incluye predicción ML con scikit-learn (Random Forest).

Principio aplicado: Domain Service (Arquitectura Hexagonal).
No accede a BD ni a HTTP — recibe DataFrames y devuelve resultados puros.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import ta as ta_lib

from core.domain.services.backtest_execution import CostModel, RiskModel, simulate

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# 1. CÁLCULO INDIVIDUAL DE INDICADORES
# ═══════════════════════════════════════════════════════════════════

# Mapeo de tipo de señal
SIGNAL_BUY = "COMPRA"
SIGNAL_SELL = "VENTA"
SIGNAL_NEUTRAL = "NEUTRAL"
SIGNAL_STRONG_BUY = "COMPRA_FUERTE"
SIGNAL_STRONG_SELL = "VENTA_FUERTE"


def _safe(val) -> Optional[float]:
    """Convierte NaN/Inf a None para serialización JSON."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6)
    except (TypeError, ValueError):
        return None


def _series_tail(series: pd.Series, n: int = 50) -> list:
    """Últimos n valores de una serie, sin NaN."""
    return [_safe(v) for v in series.tail(n).tolist()]


def calculate_indicator(df: pd.DataFrame, indicator_type: str) -> dict:
    """
    Calcula un indicador técnico concreto sobre un DataFrame OHLCV.

    Args:
        df: DataFrame con columnas [open, high, low, close, volume]
        indicator_type: RSI | MACD | SMA | EMA | BOLLINGER

    Returns:
        Dict con value, signal, interpretation y series.
    """
    indicator_type = indicator_type.upper()
    close = df["close"]
    last_price = float(close.iloc[-1])

    if indicator_type == "RSI":
        rsi_series = ta_lib.momentum.RSIIndicator(close, window=14).rsi()
        val = _safe(rsi_series.iloc[-1])
        if val is None:
            signal, interp = SIGNAL_NEUTRAL, "Datos insuficientes para calcular RSI."
        elif val > 70:
            signal = SIGNAL_SELL
            interp = f"RSI en {val:.1f} — zona de SOBRECOMPRA (>70). Posible corrección a la baja."
        elif val < 30:
            signal = SIGNAL_BUY
            interp = f"RSI en {val:.1f} — zona de SOBREVENTA (<30). Posible rebote alcista."
        else:
            signal = SIGNAL_NEUTRAL
            interp = f"RSI en {val:.1f} — zona neutral (30-70)."
        return {
            "indicator": "RSI",
            "params": {"length": 14},
            "value": val,
            "signal": signal,
            "interpretation": interp,
            "series": _series_tail(rsi_series),
        }

    elif indicator_type == "MACD":
        macd_obj = ta_lib.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = macd_obj.macd()
        signal_line = macd_obj.macd_signal()
        histogram = macd_obj.macd_diff()
        if macd_line is None or macd_line.dropna().empty:
            return _empty_result("MACD")
        val = _safe(macd_line.iloc[-1])
        sig_val = _safe(signal_line.iloc[-1])
        hist_val = _safe(histogram.iloc[-1])
        if val is not None and sig_val is not None:
            if val > sig_val:
                signal = SIGNAL_BUY
                interp = f"MACD ({val:.4f}) por encima de señal ({sig_val:.4f}) — momentum alcista."
            else:
                signal = SIGNAL_SELL
                interp = f"MACD ({val:.4f}) por debajo de señal ({sig_val:.4f}) — momentum bajista."
        else:
            signal, interp = SIGNAL_NEUTRAL, "Datos insuficientes para MACD."
        return {
            "indicator": "MACD",
            "params": {"fast": 12, "slow": 26, "signal": 9},
            "value": val,
            "signal_line": sig_val,
            "histogram": hist_val,
            "signal": signal,
            "interpretation": interp,
            "series_macd": _series_tail(macd_line),
            "series_signal": _series_tail(signal_line),
            "series_histogram": _series_tail(histogram),
        }

    elif indicator_type == "SMA":
        sma20 = ta_lib.trend.SMAIndicator(close, window=20).sma_indicator()
        sma50 = ta_lib.trend.SMAIndicator(close, window=50).sma_indicator()
        val20 = _safe(sma20.iloc[-1])
        val50 = _safe(sma50.iloc[-1])
        if val20 is not None:
            if last_price > float(val20):
                signal = SIGNAL_BUY
                interp = f"Precio ({last_price:.2f}) por encima de SMA20 ({val20:.2f}) — tendencia alcista."
            else:
                signal = SIGNAL_SELL
                interp = f"Precio ({last_price:.2f}) por debajo de SMA20 ({val20:.2f}) — tendencia bajista."
        else:
            signal, interp = SIGNAL_NEUTRAL, "Datos insuficientes para SMA."
        return {
            "indicator": "SMA",
            "params": {"lengths": [20, 50]},
            "sma_20": val20,
            "sma_50": val50,
            "value": val20,
            "signal": signal,
            "interpretation": interp,
            "series_sma20": _series_tail(sma20),
            "series_sma50": _series_tail(sma50),
        }

    elif indicator_type == "EMA":
        ema12 = ta_lib.trend.EMAIndicator(close, window=12).ema_indicator()
        ema26 = ta_lib.trend.EMAIndicator(close, window=26).ema_indicator()
        val12 = _safe(ema12.iloc[-1])
        val26 = _safe(ema26.iloc[-1])
        if val12 is not None and val26 is not None:
            if float(val12) > float(val26):
                signal = SIGNAL_BUY
                interp = f"EMA12 ({val12:.2f}) > EMA26 ({val26:.2f}) — cruce alcista."
            else:
                signal = SIGNAL_SELL
                interp = f"EMA12 ({val12:.2f}) < EMA26 ({val26:.2f}) — cruce bajista."
        else:
            signal, interp = SIGNAL_NEUTRAL, "Datos insuficientes para EMA."
        return {
            "indicator": "EMA",
            "params": {"lengths": [12, 26]},
            "ema_12": val12,
            "ema_26": val26,
            "value": val12,
            "signal": signal,
            "interpretation": interp,
            "series_ema12": _series_tail(ema12),
            "series_ema26": _series_tail(ema26),
        }

    elif indicator_type == "BOLLINGER":
        bb = ta_lib.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_upper = bb.bollinger_hband()
        bb_mid = bb.bollinger_mavg()
        bb_lower = bb.bollinger_lband()
        upper = _safe(bb_upper.iloc[-1])
        mid = _safe(bb_mid.iloc[-1])
        lower = _safe(bb_lower.iloc[-1])
        if upper is not None and lower is not None:
            if last_price > float(upper):
                signal = SIGNAL_SELL
                interp = f"Precio ({last_price:.2f}) por encima de banda superior ({upper:.2f}) — sobrecompra."
            elif last_price < float(lower):
                signal = SIGNAL_BUY
                interp = f"Precio ({last_price:.2f}) por debajo de banda inferior ({lower:.2f}) — sobreventa."
            else:
                signal = SIGNAL_NEUTRAL
                interp = f"Precio ({last_price:.2f}) dentro de las bandas ({lower:.2f} - {upper:.2f})."
        else:
            signal, interp = SIGNAL_NEUTRAL, "Datos insuficientes para Bollinger."
        return {
            "indicator": "BOLLINGER",
            "params": {"length": 20, "std": 2},
            "upper": upper,
            "middle": mid,
            "lower": lower,
            "value": mid,
            "signal": signal,
            "interpretation": interp,
            "series_upper": _series_tail(bb_upper),
            "series_middle": _series_tail(bb_mid),
            "series_lower": _series_tail(bb_lower),
        }

    else:
        return _empty_result(indicator_type)


def _empty_result(name: str) -> dict:
    return {
        "indicator": name,
        "value": None,
        "signal": SIGNAL_NEUTRAL,
        "interpretation": f"No se pudo calcular {name}.",
        "series": [],
    }


# ═══════════════════════════════════════════════════════════════════
# 2. PANEL DE SEÑALES MULTI-INDICADOR
# ═══════════════════════════════════════════════════════════════════

_SIGNAL_WEIGHTS = {
    SIGNAL_STRONG_BUY: 2,
    SIGNAL_BUY: 1,
    SIGNAL_NEUTRAL: 0,
    SIGNAL_SELL: -1,
    SIGNAL_STRONG_SELL: -2,
}


def calculate_signals_dashboard(df: pd.DataFrame) -> dict:
    """
    Ejecuta todos los indicadores principales y devuelve un resumen
    estilo TradingView con semáforos y veredicto global.
    """
    close = df["close"]
    high = df["high"]
    low = df["low"]
    last_price = float(close.iloc[-1])
    indicators = []
    score = 0

    # ── RSI ────────────────────────────────────────────────────────
    rsi_series = ta_lib.momentum.RSIIndicator(close, window=14).rsi()
    rsi_val = _safe(rsi_series.iloc[-1])
    if rsi_val is not None:
        if rsi_val > 70:
            sig = SIGNAL_SELL
        elif rsi_val < 30:
            sig = SIGNAL_BUY
        else:
            sig = SIGNAL_NEUTRAL
        indicators.append({"name": "RSI (14)", "value": rsi_val, "signal": sig})
        score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── MACD ───────────────────────────────────────────────────────
    macd_obj = ta_lib.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
    macd_line = macd_obj.macd()
    sig_line = macd_obj.macd_signal()
    if macd_line is not None and not macd_line.dropna().empty:
        macd_val = _safe(macd_line.iloc[-1])
        sig_val_m = _safe(sig_line.iloc[-1])
        if macd_val is not None and sig_val_m is not None:
            sig = SIGNAL_BUY if macd_val > sig_val_m else SIGNAL_SELL
            indicators.append({"name": "MACD (12,26,9)", "value": macd_val, "signal": sig})
            score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── SMA 20 ─────────────────────────────────────────────────────
    sma20 = ta_lib.trend.SMAIndicator(close, window=20).sma_indicator()
    sma20_val = _safe(sma20.iloc[-1])
    if sma20_val is not None:
        sig = SIGNAL_BUY if last_price > sma20_val else SIGNAL_SELL
        indicators.append({"name": "SMA (20)", "value": sma20_val, "signal": sig})
        score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── SMA 50 ─────────────────────────────────────────────────────
    sma50 = ta_lib.trend.SMAIndicator(close, window=50).sma_indicator()
    sma50_val = _safe(sma50.iloc[-1])
    if sma50_val is not None:
        sig = SIGNAL_BUY if last_price > sma50_val else SIGNAL_SELL
        indicators.append({"name": "SMA (50)", "value": sma50_val, "signal": sig})
        score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── EMA 12 ─────────────────────────────────────────────────────
    ema12 = ta_lib.trend.EMAIndicator(close, window=12).ema_indicator()
    ema12_val = _safe(ema12.iloc[-1])
    if ema12_val is not None:
        sig = SIGNAL_BUY if last_price > ema12_val else SIGNAL_SELL
        indicators.append({"name": "EMA (12)", "value": ema12_val, "signal": sig})
        score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── EMA 26 ─────────────────────────────────────────────────────
    ema26 = ta_lib.trend.EMAIndicator(close, window=26).ema_indicator()
    ema26_val = _safe(ema26.iloc[-1])
    if ema26_val is not None:
        sig = SIGNAL_BUY if last_price > ema26_val else SIGNAL_SELL
        indicators.append({"name": "EMA (26)", "value": ema26_val, "signal": sig})
        score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── Bollinger Bands ────────────────────────────────────────────
    bb = ta_lib.volatility.BollingerBands(close, window=20, window_dev=2)
    bb_upper_val = _safe(bb.bollinger_hband().iloc[-1])
    bb_lower_val = _safe(bb.bollinger_lband().iloc[-1])
    if bb_upper_val is not None and bb_lower_val is not None:
        if last_price > bb_upper_val:
            sig = SIGNAL_SELL
        elif last_price < bb_lower_val:
            sig = SIGNAL_BUY
        else:
            sig = SIGNAL_NEUTRAL
        indicators.append({"name": "Bollinger (20,2)", "value": f"{bb_lower_val:.2f} - {bb_upper_val:.2f}", "signal": sig})
        score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── Stochastic RSI ─────────────────────────────────────────────
    stoch_rsi = ta_lib.momentum.StochRSIIndicator(close, window=14)
    stoch_k = _safe(stoch_rsi.stochrsi_k().iloc[-1])
    if stoch_k is not None:
        stoch_k_pct = stoch_k * 100  # ta lib devuelve 0-1
        if stoch_k_pct > 80:
            sig = SIGNAL_SELL
        elif stoch_k_pct < 20:
            sig = SIGNAL_BUY
        else:
            sig = SIGNAL_NEUTRAL
        indicators.append({"name": "Stoch RSI", "value": round(stoch_k_pct, 4), "signal": sig})
        score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── ADX ─────────────────────────────────────────────────────────
    adx_obj = ta_lib.trend.ADXIndicator(high, low, close, window=14)
    adx_val = _safe(adx_obj.adx().iloc[-1])
    plus_di = _safe(adx_obj.adx_pos().iloc[-1])
    minus_di = _safe(adx_obj.adx_neg().iloc[-1])
    if adx_val is not None and plus_di is not None and minus_di is not None:
        if adx_val > 25:
            sig = SIGNAL_BUY if plus_di > minus_di else SIGNAL_SELL
        else:
            sig = SIGNAL_NEUTRAL
        indicators.append({"name": "ADX (14)", "value": adx_val, "signal": sig})
        score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── CCI ─────────────────────────────────────────────────────────
    cci_series = ta_lib.trend.CCIIndicator(high, low, close, window=20).cci()
    cci_val = _safe(cci_series.iloc[-1])
    if cci_val is not None:
        if cci_val > 100:
            sig = SIGNAL_SELL
        elif cci_val < -100:
            sig = SIGNAL_BUY
        else:
            sig = SIGNAL_NEUTRAL
        indicators.append({"name": "CCI (20)", "value": cci_val, "signal": sig})
        score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── Williams %R ────────────────────────────────────────────────
    willr_series = ta_lib.momentum.WilliamsRIndicator(high, low, close, lbp=14).williams_r()
    willr_val = _safe(willr_series.iloc[-1])
    if willr_val is not None:
        if willr_val < -80:
            sig = SIGNAL_BUY
        elif willr_val > -20:
            sig = SIGNAL_SELL
        else:
            sig = SIGNAL_NEUTRAL
        indicators.append({"name": "Williams %R", "value": willr_val, "signal": sig})
        score += _SIGNAL_WEIGHTS.get(sig, 0)

    # ── Veredicto global ───────────────────────────────────────────
    n = len(indicators) or 1
    avg = score / n
    buys = sum(1 for i in indicators if i["signal"] == SIGNAL_BUY)
    sells = sum(1 for i in indicators if i["signal"] == SIGNAL_SELL)
    neutrals = sum(1 for i in indicators if i["signal"] == SIGNAL_NEUTRAL)

    if avg > 0.5:
        verdict = SIGNAL_STRONG_BUY
    elif avg > 0:
        verdict = SIGNAL_BUY
    elif avg < -0.5:
        verdict = SIGNAL_STRONG_SELL
    elif avg < 0:
        verdict = SIGNAL_SELL
    else:
        verdict = SIGNAL_NEUTRAL

    return {
        "indicators": indicators,
        "summary": {
            "verdict": verdict,
            "score": round(avg, 2),
            "buy_count": buys,
            "sell_count": sells,
            "neutral_count": neutrals,
            "total": len(indicators),
        },
        "last_price": last_price,
    }


# ═══════════════════════════════════════════════════════════════════
# 3. DETECCIÓN DE PATRONES DE VELAS
# ═══════════════════════════════════════════════════════════════════

def detect_candle_patterns(df: pd.DataFrame) -> list[dict]:
    """
    Detecta patrones de velas japonesas en las últimas velas.
    Implementación manual de los 12 patrones más comunes.
    """
    if len(df) < 5:
        return []

    patterns_found = []
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    # Trabajamos sobre las últimas 5 velas
    for i in range(max(len(df) - 5, 2), len(df)):
        body = abs(c[i] - o[i])
        upper_wick = h[i] - max(c[i], o[i])
        lower_wick = min(c[i], o[i]) - l[i]
        total_range = h[i] - l[i]
        if total_range == 0:
            continue
        body_pct = body / total_range

        is_bullish = c[i] > o[i]
        is_bearish = c[i] < o[i]

        # ── Doji ───────────────────────────────────────
        if body_pct < 0.1:
            patterns_found.append({
                "name": "Doji",
                "index": int(i - len(df)),
                "signal": "NEUTRAL",
                "reliability": "MEDIA",
                "description": "Indecisión del mercado. Posible cambio de tendencia.",
            })

        # ── Hammer (Martillo) ──────────────────────────
        if is_bullish and lower_wick > body * 2 and upper_wick < body * 0.5 and body_pct > 0.05:
            patterns_found.append({
                "name": "Hammer",
                "index": int(i - len(df)),
                "signal": "COMPRA",
                "reliability": "ALTA",
                "description": "Martillo alcista. Rechazo de precios bajos, posible reversión alcista.",
            })

        # ── Inverted Hammer ────────────────────────────
        if is_bullish and upper_wick > body * 2 and lower_wick < body * 0.5 and body_pct > 0.05:
            patterns_found.append({
                "name": "Inverted Hammer",
                "index": int(i - len(df)),
                "signal": "COMPRA",
                "reliability": "MEDIA",
                "description": "Martillo invertido. Señal alcista tras tendencia bajista.",
            })

        # ── Shooting Star ──────────────────────────────
        if is_bearish and upper_wick > body * 2 and lower_wick < body * 0.5 and body_pct > 0.05:
            patterns_found.append({
                "name": "Shooting Star",
                "index": int(i - len(df)),
                "signal": "VENTA",
                "reliability": "ALTA",
                "description": "Estrella fugaz. Rechazo de precios altos, posible reversión bajista.",
            })

        # ── Bullish Engulfing ──────────────────────────
        if i > 0 and is_bullish and c[i - 1] < o[i - 1]:
            if o[i] <= c[i - 1] and c[i] >= o[i - 1]:
                patterns_found.append({
                    "name": "Bullish Engulfing",
                    "index": int(i - len(df)),
                    "signal": "COMPRA",
                    "reliability": "ALTA",
                    "description": "Envolvente alcista. Vela verde envuelve completamente la roja anterior.",
                })

        # ── Bearish Engulfing ──────────────────────────
        if i > 0 and is_bearish and c[i - 1] > o[i - 1]:
            if o[i] >= c[i - 1] and c[i] <= o[i - 1]:
                patterns_found.append({
                    "name": "Bearish Engulfing",
                    "index": int(i - len(df)),
                    "signal": "VENTA",
                    "reliability": "ALTA",
                    "description": "Envolvente bajista. Vela roja envuelve completamente la verde anterior.",
                })

        # ── Morning Star ───────────────────────────────
        if i >= 2:
            body_prev2 = abs(c[i - 2] - o[i - 2])
            body_prev1 = abs(c[i - 1] - o[i - 1])
            range_prev2 = h[i - 2] - l[i - 2] or 1
            range_prev1 = h[i - 1] - l[i - 1] or 1
            if (c[i - 2] < o[i - 2] and  # Primera: bajista grande
                    body_prev2 / range_prev2 > 0.5 and
                    body_prev1 / range_prev1 < 0.3 and  # Segunda: cuerpo pequeño
                    is_bullish and body_pct > 0.5):  # Tercera: alcista grande
                patterns_found.append({
                    "name": "Morning Star",
                    "index": int(i - len(df)),
                    "signal": "COMPRA",
                    "reliability": "ALTA",
                    "description": "Estrella de la mañana. Patrón de tres velas que señala reversión alcista.",
                })

        # ── Evening Star ───────────────────────────────
        if i >= 2:
            body_prev2 = abs(c[i - 2] - o[i - 2])
            body_prev1 = abs(c[i - 1] - o[i - 1])
            range_prev2 = h[i - 2] - l[i - 2] or 1
            range_prev1 = h[i - 1] - l[i - 1] or 1
            if (c[i - 2] > o[i - 2] and  # Primera: alcista grande
                    body_prev2 / range_prev2 > 0.5 and
                    body_prev1 / range_prev1 < 0.3 and  # Segunda: cuerpo pequeño
                    is_bearish and body_pct > 0.5):  # Tercera: bajista grande
                patterns_found.append({
                    "name": "Evening Star",
                    "index": int(i - len(df)),
                    "signal": "VENTA",
                    "reliability": "ALTA",
                    "description": "Estrella de la tarde. Patrón de tres velas que señala reversión bajista.",
                })

        # ── Three White Soldiers ───────────────────────
        if i >= 2:
            if (c[i] > o[i] and c[i - 1] > o[i - 1] and c[i - 2] > o[i - 2] and
                    c[i] > c[i - 1] > c[i - 2] and
                    o[i] > o[i - 1] > o[i - 2]):
                patterns_found.append({
                    "name": "Three White Soldiers",
                    "index": int(i - len(df)),
                    "signal": "COMPRA",
                    "reliability": "ALTA",
                    "description": "Tres soldados blancos. Tres velas alcistas consecutivas con máximos crecientes.",
                })

        # ── Three Black Crows ──────────────────────────
        if i >= 2:
            if (c[i] < o[i] and c[i - 1] < o[i - 1] and c[i - 2] < o[i - 2] and
                    c[i] < c[i - 1] < c[i - 2] and
                    o[i] < o[i - 1] < o[i - 2]):
                patterns_found.append({
                    "name": "Three Black Crows",
                    "index": int(i - len(df)),
                    "signal": "VENTA",
                    "reliability": "ALTA",
                    "description": "Tres cuervos negros. Tres velas bajistas consecutivas con mínimos decrecientes.",
                })

    return patterns_found


# ═══════════════════════════════════════════════════════════════════
# 4. PREDICCIÓN ML
# ═══════════════════════════════════════════════════════════════════

def predict_price_direction(df: pd.DataFrame, horizon: int = 5) -> dict:
    """
    Predice la dirección del precio usando Random Forest.

    Usa indicadores técnicos como features.
    Target: 1 si precio sube en 'horizon' velas, 0 si baja.

    Args:
        df: DataFrame OHLCV con al menos 100 filas.
        horizon: Número de velas futuras para la predicción.

    Returns:
        Dict con prediction, confidence, features_importance, etc.
    """
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score

    if len(df) < 100:
        return {
            "prediction": "INSUFFICIENT_DATA",
            "confidence": 0,
            "horizon": horizon,
            "message": "Se necesitan al menos 100 velas para entrenar el modelo.",
        }

    # ── Construir features ─────────────────────────────────────────
    feat = pd.DataFrame(index=df.index)
    feat["rsi_14"] = ta_lib.momentum.RSIIndicator(df["close"], window=14).rsi()
    feat["rsi_7"] = ta_lib.momentum.RSIIndicator(df["close"], window=7).rsi()

    macd_obj = ta_lib.trend.MACD(df["close"], window_slow=26, window_fast=12, window_sign=9)
    feat["macd"] = macd_obj.macd()
    feat["macd_signal"] = macd_obj.macd_signal()
    feat["macd_hist"] = macd_obj.macd_diff()

    feat["sma_20"] = ta_lib.trend.SMAIndicator(df["close"], window=20).sma_indicator()
    feat["sma_50"] = ta_lib.trend.SMAIndicator(df["close"], window=50).sma_indicator()
    feat["ema_12"] = ta_lib.trend.EMAIndicator(df["close"], window=12).ema_indicator()
    feat["ema_26"] = ta_lib.trend.EMAIndicator(df["close"], window=26).ema_indicator()

    bb = ta_lib.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    feat["bb_upper"] = bb.bollinger_hband()
    feat["bb_middle"] = bb.bollinger_mavg()
    feat["bb_lower"] = bb.bollinger_lband()
    feat["bb_width"] = bb.bollinger_wband()

    adx_obj = ta_lib.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    feat["adx"] = adx_obj.adx()

    # vol_change: si el volumen es todo cero (datos CoinGecko sin volumen real)
    # pct_change() produciría NaN en cada fila y dropna() eliminaría todo el DataFrame.
    # En ese caso se sustituye por 0.0 (neutro) para no perder los demás features.
    volume_series = df["volume"]
    if volume_series.sum() == 0:
        feat["vol_change"] = 0.0
    else:
        feat["vol_change"] = (
            volume_series.pct_change()
            .fillna(0)
            .replace([np.inf, -np.inf], 0)
        )
    feat["price_change_1"] = df["close"].pct_change(1)
    feat["price_change_5"] = df["close"].pct_change(5)
    feat["high_low_ratio"] = (df["high"] - df["low"]) / df["close"]

    # ── Target: ¿sube el precio en N velas? ────────────────────────
    feat["target"] = (df["close"].shift(-horizon) > df["close"]).astype(int)

    # Limpiar NaN
    feat = feat.dropna()

    if len(feat) < 60:
        return {
            "prediction": "INSUFFICIENT_DATA",
            "confidence": 0,
            "horizon": horizon,
            "message": "Datos insuficientes tras calcular indicadores.",
        }

    feature_cols = [c for c in feat.columns if c != "target"]
    X = feat[feature_cols].values
    y = feat["target"].values

    # Separar train (todo menos últimas 'horizon' filas) y predict (última fila)
    X_train = X[:-horizon]
    y_train = y[:-horizon]
    X_latest = X[-1:].copy()

    if len(X_train) < 50:
        return {
            "prediction": "INSUFFICIENT_DATA",
            "confidence": 0,
            "horizon": horizon,
            "message": "Datos de entrenamiento insuficientes.",
        }

    # ── Entrenar modelo ────────────────────────────────────────────
    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=8,
        min_samples_split=10,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    # Cross-validation para evaluar fiabilidad
    cv_scores = cross_val_score(model, X_train, y_train, cv=max(2, min(5, len(X_train) // 10)), scoring="accuracy")

    # Predicción
    proba = model.predict_proba(X_latest)[0]
    pred_class = model.predict(X_latest)[0]

    # Feature importance
    importances = model.feature_importances_
    top_features = sorted(
        zip(feature_cols, importances),
        key=lambda x: x[1],
        reverse=True,
    )[:8]

    prediction = "ALCISTA" if pred_class == 1 else "BAJISTA"
    confidence = float(max(proba))

    return {
        "prediction": prediction,
        "confidence": round(confidence, 4),
        "horizon": horizon,
        "model": "RandomForest",
        "cv_accuracy": round(float(cv_scores.mean()), 4),
        "cv_std": round(float(cv_scores.std()), 4),
        "features_importance": [
            {"feature": name, "importance": round(float(imp), 4)}
            for name, imp in top_features
        ],
        "disclaimer": "Predicción estadística basada en indicadores técnicos. No constituye consejo financiero.",
    }


# ═══════════════════════════════════════════════════════════════════
# 5. BACKTESTING
# ═══════════════════════════════════════════════════════════════════

STRATEGIES = {
    "rsi_reversal": {
        "name": "RSI Reversal",
        "description": "Comprar cuando RSI < 30 (sobreventa), vender cuando RSI > 70 (sobrecompra).",
        "param_space": [
            {"name": "window", "type": "int", "low": 7, "high": 21, "default": 14},
            {"name": "oversold", "type": "int", "low": 20, "high": 35, "default": 30},
            {"name": "overbought", "type": "int", "low": 65, "high": 80, "default": 70},
        ],
    },
    "macd_crossover": {
        "name": "MACD Crossover",
        "description": "Comprar cuando MACD cruza por encima de la señal, vender al revés.",
        "param_space": [
            {"name": "fast", "type": "int", "low": 8, "high": 16, "default": 12},
            {"name": "slow", "type": "int", "low": 20, "high": 34, "default": 26},
            {"name": "signal", "type": "int", "low": 6, "high": 12, "default": 9},
        ],
    },
    "bollinger_bounce": {
        "name": "Bollinger Bounce",
        "description": "Comprar al tocar banda inferior, vender al tocar banda superior.",
        "param_space": [
            {"name": "window", "type": "int", "low": 14, "high": 30, "default": 20},
            {"name": "dev", "type": "float", "low": 1.5, "high": 3.0, "default": 2.0},
        ],
    },
    "sma_crossover": {
        "name": "SMA Crossover",
        "description": "Comprar cuando SMA rápida (20) cruza por encima de SMA lenta (50).",
        "param_space": [
            {"name": "fast", "type": "int", "low": 10, "high": 30, "default": 20},
            {"name": "slow", "type": "int", "low": 40, "high": 100, "default": 50},
        ],
    },
    "ema_trend": {
        "name": "EMA Trend",
        "description": "Comprar cuando precio > EMA(26), vender cuando precio < EMA(26).",
        "param_space": [
            {"name": "window", "type": "int", "low": 14, "high": 40, "default": 26},
        ],
    },
}


def strategy_param_space(strategy: str) -> list[dict]:
    """Espacio de parámetros optimizables de una estrategia (rangos + defaults)."""
    return STRATEGIES[strategy]["param_space"]


def strategy_defaults(strategy: str) -> dict:
    """Valores por defecto de los parámetros (reproducen el comportamiento clásico)."""
    return {p["name"]: p["default"] for p in STRATEGIES[strategy]["param_space"]}


def _merge_params(strategy: str, params: Optional[dict]) -> dict:
    """Combina los parámetros recibidos con los defaults; ignora claves desconocidas."""
    merged = strategy_defaults(strategy)
    if params:
        for key, value in params.items():
            if key in merged:
                merged[key] = value
    return merged


def _generate_signals(df: pd.DataFrame, strategy: str, params: dict) -> np.ndarray:
    """
    Genera el array de señales (1=compra, -1=venta, 0=hold) de una estrategia
    según sus parámetros. Con los defaults reproduce exactamente la lógica
    clásica; solo cambia QUÉ parámetros usa, no el algoritmo.
    """
    close = df["close"].values
    n = len(close)
    signals = np.zeros(n)

    if strategy == "rsi_reversal":
        window = int(params["window"])
        oversold = float(params["oversold"])
        overbought = float(params["overbought"])
        rsi_vals = ta_lib.momentum.RSIIndicator(df["close"], window=window).rsi().values
        for i in range(window, n):
            if not np.isnan(rsi_vals[i]):
                if rsi_vals[i] < oversold:
                    signals[i] = 1
                elif rsi_vals[i] > overbought:
                    signals[i] = -1

    elif strategy == "macd_crossover":
        fast, slow, sign = int(params["fast"]), int(params["slow"]), int(params["signal"])
        if fast >= slow:
            return signals  # combinación inválida (rápida ≥ lenta) → sin operaciones
        macd_obj = ta_lib.trend.MACD(df["close"], window_slow=slow, window_fast=fast, window_sign=sign)
        macd_line = macd_obj.macd().values
        sig_line = macd_obj.macd_signal().values
        for i in range(1, n):
            if not np.isnan(macd_line[i]) and not np.isnan(sig_line[i]):
                if macd_line[i] > sig_line[i] and macd_line[i - 1] <= sig_line[i - 1]:
                    signals[i] = 1
                elif macd_line[i] < sig_line[i] and macd_line[i - 1] >= sig_line[i - 1]:
                    signals[i] = -1

    elif strategy == "bollinger_bounce":
        window = int(params["window"])
        dev = float(params["dev"])
        bb = ta_lib.volatility.BollingerBands(df["close"], window=window, window_dev=dev)
        upper = bb.bollinger_hband().values
        lower = bb.bollinger_lband().values
        for i in range(window, n):
            if not np.isnan(upper[i]) and not np.isnan(lower[i]):
                if close[i] <= lower[i]:
                    signals[i] = 1
                elif close[i] >= upper[i]:
                    signals[i] = -1

    elif strategy == "sma_crossover":
        fast, slow = int(params["fast"]), int(params["slow"])
        if fast >= slow:
            return signals
        s_fast = ta_lib.trend.SMAIndicator(df["close"], window=fast).sma_indicator().values
        s_slow = ta_lib.trend.SMAIndicator(df["close"], window=slow).sma_indicator().values
        for i in range(1, n):
            if not np.isnan(s_fast[i]) and not np.isnan(s_slow[i]):
                if s_fast[i] > s_slow[i] and s_fast[i - 1] <= s_slow[i - 1]:
                    signals[i] = 1
                elif s_fast[i] < s_slow[i] and s_fast[i - 1] >= s_slow[i - 1]:
                    signals[i] = -1

    elif strategy == "ema_trend":
        window = int(params["window"])
        ema_vals = ta_lib.trend.EMAIndicator(df["close"], window=window).ema_indicator().values
        for i in range(1, n):
            if not np.isnan(ema_vals[i]):
                if close[i] > ema_vals[i] and close[i - 1] <= ema_vals[i - 1]:
                    signals[i] = 1
                elif close[i] < ema_vals[i] and close[i - 1] >= ema_vals[i - 1]:
                    signals[i] = -1

    return signals


def generate_signals(df: pd.DataFrame, strategy: str, params: Optional[dict] = None) -> np.ndarray:
    """Señales (1/-1/0) de una estrategia con sus parámetros (defaults si None).
    Público para los detectores de sesgo de la suite de robustez."""
    return _generate_signals(df, strategy, _merge_params(strategy, params))


def strategy_indicator_series(
    df: pd.DataFrame, strategy: str, params: Optional[dict] = None
) -> np.ndarray:
    """
    Serie del indicador principal que dirige cada estrategia. La usa el
    detector de inestabilidad recursiva (EMA/RSI son recursivos; SMA no).
    """
    p = _merge_params(strategy, params)
    close = df["close"]
    if strategy == "rsi_reversal":
        return ta_lib.momentum.RSIIndicator(close, window=int(p["window"])).rsi().values
    if strategy == "macd_crossover":
        return ta_lib.trend.MACD(
            close, window_slow=int(p["slow"]), window_fast=int(p["fast"]),
            window_sign=int(p["signal"]),
        ).macd().values
    if strategy == "bollinger_bounce":
        return ta_lib.volatility.BollingerBands(
            close, window=int(p["window"]), window_dev=float(p["dev"]),
        ).bollinger_pband().values
    if strategy == "sma_crossover":
        return ta_lib.trend.SMAIndicator(close, window=int(p["fast"])).sma_indicator().values
    if strategy == "ema_trend":
        return ta_lib.trend.EMAIndicator(close, window=int(p["window"])).ema_indicator().values
    return np.full(len(df), np.nan)


def run_backtest(
    df: pd.DataFrame,
    strategy: str,
    initial_capital: float = 10000.0,
    params: Optional[dict] = None,
    costs: "CostModel | None" = None,
    risk: "RiskModel | None" = None,
) -> dict:
    """
    Ejecuta un backtest de una estrategia sobre datos OHLCV.

    Salida pública estable (compatibilidad): métricas + las últimas 20
    operaciones. Sin `params`/costes usa los valores por defecto (comportamiento
    histórico idéntico). `costs` aplica comisión+deslizamiento y `risk` aplica
    stop-loss/take-profit. La curva de equity completa se obtiene con
    run_backtest_full().
    """
    full = run_backtest_full(df, strategy, initial_capital, params, costs=costs, risk=risk)
    if "error" in full:
        return full
    public = {
        k: v for k, v in full.items()
        if k not in ("trades", "equity_curve", "bar_returns", "params", "exposure_pct")
    }
    public["trades"] = full["trades"][-20:]  # Últimas 20 operaciones
    return public


def run_backtest_full(
    df: pd.DataFrame,
    strategy: str,
    initial_capital: float = 10000.0,
    params: Optional[dict] = None,
    costs: "CostModel | None" = None,
    risk: "RiskModel | None" = None,
) -> dict:
    """
    Igual que run_backtest pero devuelve además la curva de equity, la serie
    de retornos por vela y TODAS las operaciones. Lo consume la suite de
    robustez (métricas, Monte Carlo, PBO). Con costes/riesgo None es idéntico
    al motor histórico (la suite de robustez lo usa así).
    """
    if strategy not in STRATEGIES:
        return {"error": f"Estrategia '{strategy}' no reconocida. Opciones: {list(STRATEGIES.keys())}"}

    if len(df) < 60:
        return {"error": "Se necesitan al menos 60 velas para backtesting."}

    merged = _merge_params(strategy, params)
    signals = _generate_signals(df, strategy, merged)
    result = _simulate_and_measure(df, strategy, signals, initial_capital, costs=costs, risk=risk)
    result["params"] = merged
    return result


def backtest_signals(
    df: pd.DataFrame,
    signals: np.ndarray,
    initial_capital: float = 10000.0,
    costs: "CostModel | None" = None,
    risk: "RiskModel | None" = None,
) -> dict:
    """
    Backtest long-only (todo dentro / todo fuera) de un array de señales
    arbitrario (1=compra, -1=venta, 0=hold). Reutilizable por el generador
    de estrategias (señales compiladas de un StrategySpec componible), no
    solo por las 5 estrategias del catálogo.

    `costs` aplica comisión + deslizamiento (None = sin costes, comportamiento
    histórico); `risk` aplica stop-loss/take-profit/trailing intrabar. Devuelve
    métricas + curva de equity + retornos por vela + todas las operaciones (con
    su motivo de salida) + costes pagados.
    """
    close = df["close"].values
    high = df["high"].values if "high" in df.columns else close
    low = df["low"].values if "low" in df.columns else close
    n = len(close)

    sim = simulate(close, high, low, signals, initial_capital, costs=costs, risk=risk)
    trades = sim["trades"]
    equity_curve = sim["equity_curve"]
    final_capital = sim["final_capital"]

    # ── Métricas ───────────────────────────────────────────────────
    total_return = ((final_capital - initial_capital) / initial_capital) * 100
    buy_hold_return = ((close[-1] - close[0]) / close[0]) * 100

    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0

    peak = equity_curve[0]
    max_dd = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd

    # Retornos por vela de la propia estrategia (0 cuando está en liquidez).
    # Base de las métricas de riesgo (Sharpe, Sortino, VaR…).
    bar_returns = [
        (equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
        if equity_curve[i - 1] else 0.0
        for i in range(1, len(equity_curve))
    ]
    exposure_pct = (sim["in_market_bars"] / n * 100) if n else 0.0

    avg_win = np.mean([t["pnl_pct"] for t in wins]) if wins else 0
    avg_loss = np.mean([abs(t["pnl_pct"]) for t in losses]) if losses else 0

    # ── Rango de fechas del periodo analizado ─────────────────────
    start_date: str | None = None
    end_date: str | None = None
    if "timestamp" in df.columns:
        ts_vals = df["timestamp"].dropna()
        if len(ts_vals) >= 2:
            start_ts = int(ts_vals.iloc[0])
            end_ts = int(ts_vals.iloc[-1])
            # Binance y CoinGecko devuelven timestamps en milisegundos
            if start_ts > 1_000_000_000_000:
                start_ts //= 1000
                end_ts //= 1000
            start_date = datetime.fromtimestamp(start_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            end_date = datetime.fromtimestamp(end_ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")

    return {
        "strategy": "Personalizada",
        "strategy_key": None,
        "description": "Estrategia compuesta",
        "initial_capital": initial_capital,
        "final_capital": round(float(final_capital), 2),
        "total_return_pct": round(float(total_return), 2),
        "buy_hold_return_pct": round(float(buy_hold_return), 2),
        "start_date": start_date,
        "end_date": end_date,
        "candles_count": n,
        "total_trades": len(trades),
        "win_rate_pct": round(float(win_rate), 2),
        "avg_win_pct": round(float(avg_win), 2),
        "avg_loss_pct": round(float(avg_loss), 2),
        "max_drawdown_pct": round(float(max_dd), 2),
        "exposure_pct": round(float(exposure_pct), 2),
        "total_commission_pct": sim["total_commission_pct"],
        "turnover": sim["turnover"],
        "exit_reasons": _exit_reason_counts(trades),
        # Datos completos para la suite de robustez (run_backtest los recorta):
        "trades": trades,
        "equity_curve": equity_curve,
        "bar_returns": bar_returns,
    }


def _exit_reason_counts(trades: list[dict]) -> dict:
    """Recuento de operaciones por motivo de salida (señal, stop, objetivo…)."""
    counts: dict[str, int] = {}
    for t in trades:
        reason = t.get("exit_reason", "signal")
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def _simulate_and_measure(
    df: pd.DataFrame, strategy: str, signals: np.ndarray, initial_capital: float,
    costs: "CostModel | None" = None, risk: "RiskModel | None" = None,
) -> dict:
    """Backtest de una de las 5 estrategias del catálogo: añade nombre y
    descripción a la salida genérica de backtest_signals (compatibilidad)."""
    result = backtest_signals(df, signals, initial_capital, costs=costs, risk=risk)
    info = STRATEGIES[strategy]
    result["strategy"] = info["name"]
    result["strategy_key"] = strategy
    result["description"] = info["description"]
    return result
