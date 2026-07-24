"""
market_regime.py — Caso de uso: correlaciones cross-asset y régimen de mercado.

Toma una cesta (top por capitalización), carga su histórico del almacén OHLCV,
calcula la matriz de correlación y clasifica el régimen combinando la
correlación media con la tendencia de BTC y la amplitud de la cesta.
"""

from __future__ import annotations

import logging

from core.domain.services import market_regime as regime
from core.domain.services import portfolio_risk as risk
from core.application.use_cases.portfolio_risk import PortfolioRiskUseCase

logger = logging.getLogger(__name__)


class MarketRegimeUseCase:
    """Correlaciones de la cesta y etiqueta de régimen de mercado."""

    _BASKET_SIZE = 10

    def execute(self) -> dict:
        from core.infrastructure.persistence.models import CryptoAsset

        symbols = list(
            CryptoAsset.objects.exclude(market_cap__isnull=True)
            .order_by("-market_cap").values_list("symbol", flat=True)[:self._BASKET_SIZE]
        )
        if len(symbols) < 2:
            return {"status": "INSUFICIENTE", "note": "Cesta de activos insuficiente."}

        closes = PortfolioRiskUseCase._load_history(symbols)
        returns_by = {s: risk.daily_returns(c) for s, c in closes.items()
                      if c is not None and len(c) > 1}
        correlations = regime.correlation_matrix(returns_by)
        if correlations["status"] != "OK":
            return {"status": "INSUFICIENTE",
                    "note": "Histórico solapado insuficiente para las correlaciones."}

        btc_trend = regime.trend_pct(closes.get("BTC"))
        breadth = regime.breadth_pct(closes)
        classification = regime.classify_regime(
            correlations["avg_correlation"], btc_trend, breadth,
        )

        return {
            "status": "OK",
            "correlations": correlations,
            "btc_trend_pct": btc_trend,
            "breadth_pct": breadth,
            "regime": classification,
            "basket": correlations["symbols"],
            "note": (
                "Correlación de Pearson de los retornos diarios de la cesta (top "
                "por capitalización) sobre el almacén OHLCV propio. El régimen "
                "combina correlación media, tendencia de BTC y amplitud. No es "
                "consejo financiero."
            ),
        }
