"""
test_lead_lag.py — Señales lead-lag entre activos.
"""

import numpy as np
import pytest

from core.domain.services.lead_lag import cross_lag_correlation, lead_lag_matrix


def _signal(n=80):
    return np.sin(np.linspace(0, 12, n)) * 0.02


class TestCrossLag:
    def test_detects_leader(self):
        a = _signal()
        b = np.concatenate([[0.0, 0.0], a[:-2]])   # b_t = a_{t-2} ⇒ a adelanta a b en 2
        out = cross_lag_correlation(a, b, max_lag=5)
        assert out is not None
        assert out["best_lag"] == 2 and out["best_corr"] > 0.99

    def test_zero_lag_when_aligned(self):
        a = _signal()
        out = cross_lag_correlation(a, a.copy(), max_lag=5)
        assert out["best_lag"] == 0

    def test_none_when_too_short(self):
        assert cross_lag_correlation(np.ones(10), np.ones(10), max_lag=5) is None


class TestMatrix:
    def test_leader_ranked_first(self):
        a = _signal()
        b = np.concatenate([[0.0, 0.0], a[:-2]])   # AAA adelanta a BBB
        out = lead_lag_matrix({"AAA": a, "BBB": b}, max_lag=5)
        assert out["status"] == "OK"
        assert out["leaders"][0]["symbol"] == "AAA" and out["leaders"][0]["leads"] == 1
        assert out["pairs"][0]["leader"] == "AAA" and out["pairs"][0]["lag"] == 2

    def test_insufficient(self):
        assert lead_lag_matrix({"AAA": _signal()})["status"] == "INSUFICIENTE"


@pytest.mark.django_db
class TestApi:
    def test_endpoint(self, authenticated_client):
        r = authenticated_client.get("/api/market/lead-lag/")
        assert r.status_code == 200 and r.data["status"] in ("INSUFICIENTE", "OK")

    def test_use_case_insufficient(self, test_user):
        from core.application.use_cases.lead_lag import LeadLagUseCase
        assert LeadLagUseCase().execute()["status"] == "INSUFICIENTE"
