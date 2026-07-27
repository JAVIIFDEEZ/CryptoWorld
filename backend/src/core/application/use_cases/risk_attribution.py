"""
risk_attribution.py — Caso de uso: atribución del riesgo del libro completo.

Reutiliza la agregación de exposición y la carga de histórico del caso de uso
de riesgo de cartera, alinea la matriz de retornos y aplica la descomposición
del dominio (por componentes + por factor de mercado BTC).
"""

from __future__ import annotations

import logging

import numpy as np

from core.domain.services import portfolio_risk as risk
from core.domain.services import risk_attribution as attribution
from core.application.use_cases.portfolio_risk import PortfolioRiskUseCase

logger = logging.getLogger(__name__)

_FACTOR_SYMBOL = "BTC"   # factor de mercado


class RiskAttributionUseCase:
    """Atribuye el riesgo de cola del libro por posición y por factor."""

    def execute(self, owner) -> dict:
        exposures = PortfolioRiskUseCase._aggregate_exposures(owner)
        if not exposures:
            return {"status": "EMPTY", "components": [], "factor": {"status": "EMPTY"},
                    "note": "Sin posiciones abiertas en ningún libro."}

        closes = PortfolioRiskUseCase._load_history(list(exposures))
        returns_by = {s: risk.daily_returns(c) for s, c in closes.items()
                      if c is not None and len(c) > 1}
        symbols, matrix = risk.align_returns_matrix(returns_by)
        if not symbols or matrix.shape[0] < risk.MIN_OVERLAP_DAYS:
            return {"status": "INSUFICIENTE", "components": [], "factor": {"status": "INSUFICIENTE"},
                    "note": f"Se necesitan ≥ {risk.MIN_OVERLAP_DAYS} días de histórico solapado."}

        exp_vector = [float(exposures[s]["net_usd"]) for s in symbols]
        components = attribution.component_tail_risk(matrix, exp_vector, symbols)

        # ── Factor de mercado (BTC) alineado a las mismas T filas ──
        factor = {"status": "INSUFICIENTE"}
        btc_returns = returns_by.get(_FACTOR_SYMBOL)
        if btc_returns is None:
            btc_hist = PortfolioRiskUseCase._load_history([_FACTOR_SYMBOL])
            closes_btc = btc_hist.get(_FACTOR_SYMBOL)
            if closes_btc is not None and len(closes_btc) > 1:
                btc_returns = risk.daily_returns(closes_btc)
        if btc_returns is not None:
            t = matrix.shape[0]
            btc_returns = np.asarray(btc_returns, dtype=float)
            if btc_returns.size >= t:
                factor = attribution.factor_attribution(
                    matrix, exp_vector, symbols, btc_returns[-t:],
                )

        return {
            "status": "OK",
            "components": components,
            "factor": factor,
            "gross_usd": round(sum(abs(v) for v in exp_vector), 2),
            "note": (
                "Riesgo de cola (CVaR 95% histórico) repartido por posición "
                "mediante descomposición de Euler — las contribuciones suman el "
                "riesgo total. El factor de mercado (BTC) separa la varianza en "
                "sistemática (beta) e idiosincrásica. No es consejo financiero."
            ),
        }
