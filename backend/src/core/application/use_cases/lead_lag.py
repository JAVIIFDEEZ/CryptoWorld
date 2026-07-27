"""
lead_lag.py — Caso de uso: señales lead-lag de la cesta.

Carga el histórico de la cesta (top por capitalización), calcula los retornos
diarios y aplica el análisis lead-lag del dominio para saber qué activos
adelantan a cuáles.
"""

from __future__ import annotations

import logging

from core.domain.services import lead_lag
from core.domain.services import portfolio_risk as risk
from core.application.use_cases.portfolio_risk import PortfolioRiskUseCase

logger = logging.getLogger(__name__)


class LeadLagUseCase:
    """Relaciones lead-lag y ranking de liderazgo de la cesta."""

    _BASKET_SIZE = 10
    _MAX_LAG = 5   # barras (días) de desfase exploradas

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
        result = lead_lag.lead_lag_matrix(returns_by, max_lag=self._MAX_LAG)
        if result["status"] != "OK":
            return {"status": "INSUFICIENTE",
                    "note": "Histórico solapado insuficiente para el análisis lead-lag."}

        result["note"] = (
            "Correlación cruzada de los retornos diarios a distintos desfases: "
            "un desfase positivo del líder significa que sus retornos anticipan "
            "los del seguidor en esas barras. Sobre el almacén OHLCV propio. No "
            "es consejo financiero."
        )
        return result
