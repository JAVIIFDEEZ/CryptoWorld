"""
backtest_metrics.py — Métricas de rendimiento y riesgo de un backtest.

Funciones puras y deterministas que operan sobre la curva de equity y la
serie de retornos por vela que produce run_backtest_full() del motor. No
acceden a BD ni a HTTP ni dependen de ningún framework.

Principio aplicado: Domain Service (Arquitectura Hexagonal).
"""

import numpy as np

# Velas por año según el intervalo, para anualizar (Sharpe, volatilidad…).
_PERIODS_PER_YEAR = {
    "1m": 525_600, "5m": 105_120, "15m": 35_040, "30m": 17_520,
    "1h": 8_760, "2h": 4_380, "4h": 2_190, "6h": 1_460, "12h": 730,
    "1d": 365, "1w": 52,
}


def annualization_factor(interval: str) -> float:
    """Número de velas del intervalo que caben en un año."""
    return float(_PERIODS_PER_YEAR.get(interval, 365))


def sharpe_ratio(returns, periods_per_year: float, risk_free: float = 0.0) -> float:
    """Sharpe anualizado a partir de los retornos por vela."""
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    excess = r - risk_free / periods_per_year
    sd = excess.std(ddof=1)
    if sd == 0:
        return 0.0
    return float(excess.mean() / sd * np.sqrt(periods_per_year))


def sortino_ratio(returns, periods_per_year: float, risk_free: float = 0.0) -> float:
    """Sortino anualizado: penaliza solo la volatilidad a la baja."""
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    excess = r - risk_free / periods_per_year
    downside = excess[excess < 0]
    dd = np.sqrt(np.mean(downside ** 2)) if downside.size else 0.0
    if dd == 0:
        return 0.0
    return float(excess.mean() / dd * np.sqrt(periods_per_year))


def annualized_volatility(returns, periods_per_year: float) -> float:
    """Desviación típica anualizada de los retornos (fracción, no %)."""
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    return float(r.std(ddof=1) * np.sqrt(periods_per_year))


def annualized_return(equity_curve, periods_per_year: float) -> float:
    """CAGR (%) a partir de la curva de equity."""
    eq = np.asarray(equity_curve, dtype=float)
    if eq.size < 2 or eq[0] <= 0:
        return 0.0
    total_growth = eq[-1] / eq[0]
    if total_growth <= 0:
        return -100.0
    years = (eq.size - 1) / periods_per_year
    if years <= 0:
        return 0.0
    return float((total_growth ** (1 / years) - 1) * 100)


def max_drawdown(equity_curve) -> float:
    """Máxima caída pico-valle (%) de la curva de equity."""
    eq = np.asarray(equity_curve, dtype=float)
    if eq.size == 0:
        return 0.0
    peak = eq[0]
    mdd = 0.0
    for v in eq:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > mdd:
                mdd = dd
    return float(mdd)


def calmar_ratio(equity_curve, periods_per_year: float) -> float:
    """Calmar = retorno anualizado / max drawdown."""
    mdd = max_drawdown(equity_curve)
    if mdd == 0:
        return 0.0
    return float(annualized_return(equity_curve, periods_per_year) / mdd)


def historical_var(returns, level: float = 0.95) -> float:
    """VaR histórico (% de pérdida) al nivel de confianza dado."""
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    q = np.percentile(r, (1 - level) * 100)
    return float(max(0.0, -q) * 100)


def historical_cvar(returns, level: float = 0.95) -> float:
    """CVaR / Expected Shortfall (% de pérdida media en la cola)."""
    r = np.asarray(returns, dtype=float)
    if r.size == 0:
        return 0.0
    threshold = np.percentile(r, (1 - level) * 100)
    tail = r[r <= threshold]
    if tail.size == 0:
        return 0.0
    return float(max(0.0, -tail.mean()) * 100)


def profit_factor(trade_pnls) -> float:
    """Beneficio bruto / pérdida bruta. inf si no hay pérdidas."""
    pnls = np.asarray(trade_pnls, dtype=float)
    if pnls.size == 0:
        return 0.0
    gains = pnls[pnls > 0].sum()
    losses = -pnls[pnls < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def compute_metrics(full_backtest: dict, periods_per_year: float) -> dict:
    """
    Resumen de métricas a partir de la salida de run_backtest_full().
    Devuelve valores serializables (inf de profit factor → None).
    """
    bar_returns = full_backtest.get("bar_returns", [])
    equity = full_backtest.get("equity_curve", [])
    trade_pnls = [t["pnl_pct"] for t in full_backtest.get("trades", [])]

    pf = profit_factor(trade_pnls)
    return {
        "sharpe": round(sharpe_ratio(bar_returns, periods_per_year), 3),
        "sortino": round(sortino_ratio(bar_returns, periods_per_year), 3),
        "calmar": round(calmar_ratio(equity, periods_per_year), 3),
        "annualized_return_pct": round(annualized_return(equity, periods_per_year), 2),
        "annualized_volatility_pct": round(annualized_volatility(bar_returns, periods_per_year) * 100, 2),
        "var_95_pct": round(historical_var(bar_returns, 0.95), 3),
        "cvar_95_pct": round(historical_cvar(bar_returns, 0.95), 3),
        "profit_factor": (round(pf, 3) if np.isfinite(pf) else None),
        "exposure_pct": full_backtest.get("exposure_pct", round(0.0, 2)),
        "max_drawdown_pct": full_backtest.get(
            "max_drawdown_pct", round(max_drawdown(equity), 2)
        ),
    }
