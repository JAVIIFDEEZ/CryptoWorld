"""
quant_metrics.py — Estadística cuantitativa institucional sobre OHLCV.

Reúne en un único snapshot las métricas que un terminal profesional (estilo
Bloomberg) muestra de un activo de un vistazo: volatilidad realizada anualizada,
ATR, retornos multi-horizonte con z-score, Sharpe/Sortino del propio activo,
drawdown, posición en el rango, beta/correlación frente a BTC, volumen relativo
y un clasificador de régimen (tendencia/rango + volatilidad). Todo se deriva del
precio y el volumen — nada de opiniones, solo la fotografía cuantitativa del
estado del mercado AHORA.

Principio aplicado: Domain Service (Arquitectura Hexagonal). No accede a BD ni a
HTTP — recibe DataFrames y devuelve un dict puro serializable a JSON.
"""

import logging
import math

import numpy as np
import pandas as pd
import ta as ta_lib

logger = logging.getLogger(__name__)

# Minutos por año (365 días; el cripto cotiza 24/7). Base de la anualización.
_MINUTES_PER_YEAR = 365 * 24 * 60

_INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360,
    "12h": 720, "1d": 1440, "1w": 10080,
}

# Horizontes de retorno (en velas) que se reportan.
_RETURN_HORIZONS = [1, 7, 30, 90]


def _safe(val) -> float | None:
    """NaN/Inf → None para serialización JSON; redondea a 4 decimales."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def periods_per_year(interval: str) -> float:
    """Nº de velas de este marco que caben en un año (para anualizar σ, Sharpe…)."""
    minutes = _INTERVAL_MINUTES.get(interval, 60)
    return _MINUTES_PER_YEAR / minutes


def compute_quant_snapshot(
    df: pd.DataFrame,
    interval: str = "1h",
    btc_df: pd.DataFrame | None = None,
    symbol: str = "",
) -> dict:
    """
    Snapshot cuantitativo completo de un activo a partir de su OHLCV.

    Args:
        df: DataFrame con columnas [open, high, low, close, volume].
        interval: marco temporal de las velas (para anualizar).
        btc_df: OHLCV de BTC en el MISMO marco, para beta/correlación (opcional).
        symbol: símbolo del activo (BTC se auto-excluye del cálculo de beta).

    Returns:
        Dict con volatilidad, retornos, riesgo, rango, beta, volumen y régimen.
    """
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    n = len(close)
    if n < 30:
        return {"error": "Datos insuficientes para el snapshot cuantitativo."}

    last_price = float(close.iloc[-1])
    ppy = periods_per_year(interval)
    sqrt_ppy = math.sqrt(ppy)

    ret = close.pct_change().dropna()
    ret_arr = ret.to_numpy()

    # ── Volatilidad ────────────────────────────────────────────────
    sigma = float(ret.std(ddof=1)) if len(ret) > 2 else 0.0
    vol_annual_pct = sigma * sqrt_ppy * 100.0
    downside = ret_arr[ret_arr < 0]
    downside_sigma = float(np.std(downside, ddof=1)) if len(downside) > 2 else 0.0

    atr_series = ta_lib.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()
    atr = _safe(atr_series.iloc[-1])
    atr_pct = _safe(atr / last_price * 100.0) if atr and last_price else None

    # Régimen de volatilidad: σ anualizada actual vs. su mediana móvil (30 velas).
    roll_sigma = ret.rolling(30).std(ddof=1) * sqrt_ppy * 100.0
    vol_median = _safe(roll_sigma.median())
    vol_ratio = _safe(vol_annual_pct / vol_median) if vol_median else None
    if vol_ratio is None:
        vol_regime = "—"
    elif vol_ratio >= 1.3:
        vol_regime = "ALTA"
    elif vol_ratio <= 0.7:
        vol_regime = "BAJA"
    else:
        vol_regime = "NORMAL"

    # ── Retornos multi-horizonte + z-score de la última vela ───────
    returns_by_h = []
    for h in _RETURN_HORIZONS:
        if n > h:
            r = (last_price / float(close.iloc[-1 - h]) - 1.0) * 100.0
            returns_by_h.append({"h": h, "pct": _safe(r)})
        else:
            returns_by_h.append({"h": h, "pct": None})
    # ¿Cómo de extremo es el movimiento de la última vela frente a su historia?
    last_ret = float(ret.iloc[-1]) if len(ret) else 0.0
    z_last = _safe((last_ret - float(ret.mean())) / sigma) if sigma else None

    # ── Riesgo del propio activo (Sharpe/Sortino anualizados, rf=0) ──
    mean_ret = float(ret.mean()) if len(ret) else 0.0
    sharpe = _safe(mean_ret / sigma * sqrt_ppy) if sigma else None
    sortino = _safe(mean_ret / downside_sigma * sqrt_ppy) if downside_sigma else None

    # ── Drawdown sobre la ventana ──────────────────────────────────
    running_max = close.cummax()
    dd_series = (close / running_max - 1.0) * 100.0
    max_drawdown_pct = _safe(dd_series.min())
    current_drawdown_pct = _safe(dd_series.iloc[-1])

    # ── Posición en el rango de la ventana ─────────────────────────
    hi_w = float(high.max())
    lo_w = float(low.min())
    span = hi_w - lo_w
    range_pct_rank = _safe((last_price - lo_w) / span * 100.0) if span > 0 else None
    dist_to_high_pct = _safe((last_price / hi_w - 1.0) * 100.0) if hi_w else None
    dist_to_low_pct = _safe((last_price / lo_w - 1.0) * 100.0) if lo_w else None

    # ── Beta / correlación frente a BTC (riesgo sistemático) ───────
    beta = corr = None
    if btc_df is not None and symbol.upper() != "BTC":
        beta, corr = _beta_correlation(ret, btc_df)

    # ── Volumen relativo ───────────────────────────────────────────
    vol_series = df["volume"].astype(float)
    has_volume = bool(vol_series.sum() > 0)
    rel_volume = vol_z = None
    if has_volume and n > 20:
        base = vol_series.iloc[-21:-1]
        base_mean = float(base.mean())
        base_std = float(base.std(ddof=1))
        last_vol = float(vol_series.iloc[-1])
        rel_volume = _safe(last_vol / base_mean) if base_mean else None
        vol_z = _safe((last_vol - base_mean) / base_std) if base_std else None

    # ── Régimen de tendencia (ADX + medias) ────────────────────────
    regime = _trend_regime(df, close)

    # ── Sesgo direccional por confirmaciones (0-5 alcistas) ────────
    bias, bull_confirms = _directional_bias(close, regime, returns_by_h)

    # ── Chispa de precio (últimas 60 velas normalizadas 0-1) ───────
    spark = _spark(close, points=60)

    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "last_price": _safe(last_price),
        "candles": n,
        "periods_per_year": round(ppy, 1),
        # Volatilidad
        "volatility": {
            "annualized_pct": _safe(vol_annual_pct),
            "atr": atr,
            "atr_pct": atr_pct,
            "regime": vol_regime,
            "ratio_vs_median": vol_ratio,
        },
        # Retornos
        "returns": returns_by_h,
        "z_last_return": z_last,
        # Riesgo
        "risk": {
            "sharpe": sharpe,
            "sortino": sortino,
            "max_drawdown_pct": max_drawdown_pct,
            "current_drawdown_pct": current_drawdown_pct,
        },
        # Rango
        "range": {
            "high": _safe(hi_w),
            "low": _safe(lo_w),
            "pct_rank": range_pct_rank,
            "dist_to_high_pct": dist_to_high_pct,
            "dist_to_low_pct": dist_to_low_pct,
        },
        # Riesgo sistemático
        "market": {"beta_btc": beta, "corr_btc": corr},
        # Volumen
        "volume": {
            "has_volume": has_volume,
            "relative": rel_volume,
            "z_score": vol_z,
        },
        # Régimen
        "regime": regime,
        "bias": bias,
        "bull_confirmations": bull_confirms,
        "spark": spark,
        "disclaimer": "Estadística cuantitativa derivada del precio y volumen. "
                      "No constituye consejo financiero.",
    }


def _beta_correlation(asset_ret: pd.Series, btc_df: pd.DataFrame) -> tuple[float | None, float | None]:
    """Beta y correlación de los retornos del activo frente a los de BTC.
    Alinea ambas series por la cola (misma longitud) — mismo marco temporal."""
    try:
        btc_ret = btc_df["close"].astype(float).pct_change().dropna().to_numpy()
        a = asset_ret.to_numpy()
        m = min(len(a), len(btc_ret))
        if m < 20:
            return None, None
        a = a[-m:]
        b = btc_ret[-m:]
        var_b = float(np.var(b, ddof=1))
        if var_b == 0:
            return None, None
        cov = float(np.cov(a, b, ddof=1)[0, 1])
        beta = cov / var_b
        corr = float(np.corrcoef(a, b)[0, 1])
        return _safe(beta), _safe(corr)
    except Exception:  # noqa: BLE001 — beta es accesoria, nunca rompe el snapshot
        return None, None


def _trend_regime(df: pd.DataFrame, close: pd.Series) -> dict:
    """Clasifica el régimen: fuerza de tendencia (ADX) + dirección (±DI / medias)."""
    high, low = df["high"].astype(float), df["low"].astype(float)
    adx_obj = ta_lib.trend.ADXIndicator(high, low, close, window=14)
    adx = _safe(adx_obj.adx().iloc[-1])
    plus_di = _safe(adx_obj.adx_pos().iloc[-1])
    minus_di = _safe(adx_obj.adx_neg().iloc[-1])

    sma20 = _safe(ta_lib.trend.SMAIndicator(close, window=20).sma_indicator().iloc[-1])
    sma50 = _safe(ta_lib.trend.SMAIndicator(close, window=50).sma_indicator().iloc[-1]) if len(close) >= 50 else None
    last = float(close.iloc[-1])

    # Fuerza por ADX (convención estándar).
    if adx is None:
        strength = "—"
    elif adx < 20:
        strength = "SIN TENDENCIA"
    elif adx < 25:
        strength = "DÉBIL"
    elif adx < 50:
        strength = "FUERTE"
    else:
        strength = "MUY FUERTE"

    # Dirección: ±DI cuando hay tendencia; si no, precio vs SMA20.
    if plus_di is not None and minus_di is not None and adx is not None and adx >= 20:
        direction = "ALCISTA" if plus_di > minus_di else "BAJISTA"
    elif sma20 is not None:
        direction = "ALCISTA" if last > sma20 else "BAJISTA"
    else:
        direction = "NEUTRAL"

    if strength in ("SIN TENDENCIA", "—"):
        label = "RANGO / LATERAL"
    else:
        label = f"TENDENCIA {direction} {strength}"

    return {
        "label": label,
        "direction": direction,
        "strength": strength,
        "adx": adx,
        "plus_di": plus_di,
        "minus_di": minus_di,
        "sma20": sma20,
        "sma50": sma50,
        "price_vs_sma20_pct": _safe((last / sma20 - 1.0) * 100.0) if sma20 else None,
        "price_vs_sma50_pct": _safe((last / sma50 - 1.0) * 100.0) if sma50 else None,
    }


def _directional_bias(close: pd.Series, regime: dict, returns_by_h: list[dict]) -> tuple[str, int]:
    """Sesgo direccional por consenso de 5 confirmaciones alcistas independientes."""
    last = float(close.iloc[-1])
    sma20 = regime.get("sma20")
    sma50 = regime.get("sma50")
    ret_30 = next((r["pct"] for r in returns_by_h if r["h"] == 30), None)
    checks = [
        sma20 is not None and last > sma20,
        sma50 is not None and last > sma50,
        sma20 is not None and sma50 is not None and sma20 > sma50,
        ret_30 is not None and ret_30 > 0,
        regime.get("direction") == "ALCISTA",
    ]
    bull = sum(1 for c in checks if c)
    if bull >= 4:
        bias = "ALCISTA"
    elif bull <= 1:
        bias = "BAJISTA"
    else:
        bias = "NEUTRAL"
    return bias, bull


def _spark(close: pd.Series, points: int = 60) -> list[float]:
    """Últimos `points` cierres normalizados a [0, 1] para una mini-chispa."""
    tail = close.tail(points).to_numpy(dtype=float)
    if len(tail) < 2:
        return []
    lo, hi = float(tail.min()), float(tail.max())
    span = hi - lo
    if span == 0:
        return [0.5] * len(tail)
    return [round((float(v) - lo) / span, 4) for v in tail]
