"""
quant_alert_providers.py — Cálculo de los valores de métrica en vivo.

Traduce la clave de métrica de una alerta al valor numérico actual, leyéndolo
de los subsistemas reales (terminal cuantitativa, dashboard técnico,
confluencia 360°, presión on-chain, riesgo de cartera, precio). Cada lectura
es best-effort: si la fuente no está disponible devuelve ``None`` y el
evaluador simplemente salta esa alerta esta ronda (sin romper el resto).

La clase acepta cachés por ronda para no recomputar la misma pipeline pesada
(p. ej. la terminal cuantitativa de un símbolo/marco) en alertas repetidas.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Símbolo de activo → cadena on-chain para las métricas de flujo/presión.
_SYMBOL_CHAIN = {
    "BTC": "bitcoin", "ETH": "ethereum", "BNB": "bsc", "MATIC": "polygon",
    "ARB": "arbitrum", "OP": "optimism", "AVAX": "avalanche", "BASE": "base",
}


class MetricProvider:
    """Resuelve el valor actual de una métrica para una alerta dada."""

    def __init__(self) -> None:
        self._quant: dict[tuple[str, str], dict] = {}
        self._dash: dict[tuple[str, str], dict] = {}
        self._confluence: dict[str, dict] = {}
        self._pressure: dict[str, dict] = {}
        self._risk: dict[int, dict] = {}

    # ── Punto de entrada ────────────────────────────────────────────
    def value(self, alert) -> Optional[float]:
        metric = alert.metric
        try:
            if metric in ("rsi", "macd_hist", "stoch_rsi"):
                return self._from_dashboard(alert, metric)
            if metric in ("adx", "realized_vol", "atr_pct", "range_pos"):
                return self._from_quant(alert, metric)
            if metric in ("price", "change_24h"):
                return self._from_price(alert, metric)
            if metric == "confluence_score":
                return self._from_confluence(alert)
            if metric in ("onchain_net_flow", "onchain_pressure"):
                return self._from_onchain(alert, metric)
            if metric.startswith("portfolio_"):
                return self._from_risk(alert, metric)
        except Exception as exc:  # noqa: BLE001 — una fuente caída no frena el motor
            logger.warning("MetricProvider(%s) fallo: %s", metric, exc)
        return None

    # ── Fuentes ─────────────────────────────────────────────────────
    def _quant_snapshot(self, symbol: str, interval: str) -> dict:
        key = (symbol, interval)
        if key not in self._quant:
            from core.application.use_cases.get_quant_snapshot import GetQuantSnapshotUseCase
            self._quant[key] = GetQuantSnapshotUseCase().execute(symbol, interval) or {}
        return self._quant[key]

    def _dashboard(self, symbol: str, interval: str) -> dict:
        key = (symbol, interval)
        if key not in self._dash:
            from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
            from core.domain.services.technical_analysis_service import calculate_signals_dashboard
            res = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=200)
            self._dash[key] = calculate_signals_dashboard(res.df) if res and not res.df.empty else {}
        return self._dash[key]

    def _from_dashboard(self, alert, metric: str) -> Optional[float]:
        if alert.asset is None:
            return None
        dash = self._dashboard(alert.asset.symbol, alert.timeframe)
        wanted = {"rsi": "RSI", "macd_hist": "MACD", "stoch_rsi": "Stoch RSI"}[metric]
        for ind in dash.get("indicators", []):
            if str(ind.get("name", "")).startswith(wanted):
                return _num(ind.get("value"))
        return None

    def _from_quant(self, alert, metric: str) -> Optional[float]:
        if alert.asset is None:
            return None
        snap = self._quant_snapshot(alert.asset.symbol, alert.timeframe)
        key = {"realized_vol": "volatility", "range_pos": "range_position"}.get(metric, metric)
        val = snap.get(key)
        if val is None and metric == "range_pos":
            val = snap.get("range_pos")
        return _num(val)

    @staticmethod
    def _from_price(alert, metric: str) -> Optional[float]:
        if alert.asset is None:
            return None
        field = "current_price" if metric == "price" else "price_change_24h"
        return _num(getattr(alert.asset, field, None))

    def _from_confluence(self, alert) -> Optional[float]:
        if alert.asset is None:
            return None
        symbol = alert.asset.symbol
        if symbol not in self._confluence:
            from core.application.use_cases.get_confluence import GetConfluenceUseCase
            self._confluence[symbol] = GetConfluenceUseCase().execute(symbol) or {}
        score = self._confluence[symbol].get("score")
        if score is None:
            return None
        # El score de confluencia vive en [-1, 1]; lo exponemos en [-100, 100].
        return round(float(score) * 100.0, 2) if abs(float(score)) <= 1.0 else float(score)

    def _from_onchain(self, alert, metric: str) -> Optional[float]:
        if alert.asset is None:
            return None
        chain = _SYMBOL_CHAIN.get(alert.asset.symbol)
        if chain is None:
            return None
        if chain not in self._pressure:
            from core.application.use_cases.onchain_pressure import OnChainPressureUseCase
            self._pressure[chain] = OnChainPressureUseCase().execute(chain=chain, hours=24) or {}
        p = self._pressure[chain]
        if metric == "onchain_pressure":
            return _num(p.get("pressure"))
        inflow = _num(p.get("inflow_usd")) or 0.0
        outflow = _num(p.get("outflow_usd")) or 0.0
        return round(inflow - outflow, 2)

    def _from_risk(self, alert, metric: str) -> Optional[float]:
        uid = alert.user_id
        if uid not in self._risk:
            from core.application.use_cases.portfolio_risk import PortfolioRiskUseCase
            self._risk[uid] = PortfolioRiskUseCase().execute(alert.user) or {}
        r = self._risk[uid]
        if r.get("status") != "OK":
            return None
        gross = _num(r.get("gross_usd")) or 0.0
        if metric == "portfolio_exposure":
            return round(gross, 2)
        if metric == "portfolio_concentration":
            return _num(r.get("top_concentration_pct"))
        var = r.get("var") or {}
        if var.get("status") != "OK" or gross <= 0:
            return None
        usd = _num(var.get("var95_usd" if metric == "portfolio_var" else "cvar95_usd"))
        return round(usd / gross * 100.0, 2) if usd is not None else None


def _num(v) -> Optional[float]:
    """Convierte a float de forma tolerante; None si no es numérico."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None   # descarta NaN
