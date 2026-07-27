"""
test_market_regime.py — Correlaciones cross-asset y régimen de mercado.
"""

import numpy as np
import pytest

from core.domain.services.market_regime import (
    correlation_matrix, classify_regime, trend_pct, breadth_pct,
)


class TestCorrelations:
    def test_positively_correlated_basket(self):
        base = np.linspace(-0.03, 0.03, 40)
        rb = {"AAA": base, "BBB": base * 0.9 + 0.001}   # casi idénticos
        out = correlation_matrix(rb)
        assert out["status"] == "OK"
        assert out["avg_correlation"] > 0.9
        assert out["matrix"][0][0] == 1.0                # diagonal
        assert out["symbols"] == ["AAA", "BBB"]

    def test_insufficient_with_one_series(self):
        assert correlation_matrix({"AAA": np.linspace(0, 1, 40)})["status"] == "INSUFICIENTE"

    def test_insufficient_with_short_history(self):
        assert correlation_matrix({"A": np.ones(5), "B": np.ones(5)})["status"] == "INSUFICIENTE"


class TestRegime:
    def test_risk_off(self):
        r = classify_regime(0.82, -5.0, 30.0)
        assert r["regime"] == "RISK_OFF" and r["correlation_state"] == "alta"

    def test_risk_on(self):
        assert classify_regime(0.55, 4.0, 72.0)["regime"] == "RISK_ON"

    def test_rotation(self):
        assert classify_regime(0.30, 1.0, 45.0)["regime"] == "ROTACION"

    def test_neutral(self):
        assert classify_regime(0.55, -1.0, 40.0)["regime"] == "NEUTRAL"

    def test_unknown_without_data(self):
        assert classify_regime(None, 0.0, 0.0)["regime"] == "UNKNOWN"


class TestHelpers:
    def test_trend_pct(self):
        assert trend_pct(np.array([100.0, 110.0]), window=1) == 10.0

    def test_breadth_pct(self):
        up = np.concatenate([np.full(20, 100.0), [130.0]])     # último > media
        down = np.concatenate([np.full(20, 100.0), [70.0]])    # último < media
        assert breadth_pct({"UP": up, "DOWN": down}, window=20) == 50.0


@pytest.mark.django_db
class TestApi:
    def test_endpoint_insufficient_without_assets(self, authenticated_client):
        r = authenticated_client.get("/api/market/regime/")
        assert r.status_code == 200
        assert r.data["status"] in ("INSUFICIENTE", "OK")

    def test_use_case_insufficient(self, test_user):
        from core.application.use_cases.market_regime import MarketRegimeUseCase
        out = MarketRegimeUseCase().execute()
        assert out["status"] == "INSUFICIENTE"
