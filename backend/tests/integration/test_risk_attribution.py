"""
test_risk_attribution.py — Atribución de riesgo institucional.

Verifica la coherencia de la descomposición por componentes (Euler: las
contribuciones suman el riesgo de cola) y del factor de mercado (sistemática vs
idiosincrásica), más el contrato del endpoint.
"""

import numpy as np
import pytest

from core.domain.services.risk_attribution import component_tail_risk, factor_attribution


# ── Descomposición por componentes ──────────────────────────────────

class TestComponentAttribution:
    def test_components_sum_to_tail_risk(self):
        # Dos activos con retornos distintos, 40 días.
        rng = np.linspace(-0.05, 0.05, 40)
        a = rng
        b = -0.5 * rng + 0.01
        matrix = np.column_stack([a, b])
        exposures = [10_000.0, 5_000.0]
        out = component_tail_risk(matrix, exposures, ["AAA", "BBB"], tail_pct=10.0)
        assert out["status"] == "OK"
        total = sum(c["component_usd"] for c in out["components"])
        assert abs(total - out["tail_cvar_usd"]) < 0.5   # Euler: suman el total
        assert abs(sum(c["pct"] for c in out["components"]) - 100.0) < 1.0

    def test_bigger_exposure_bigger_contribution(self):
        r = np.linspace(-0.04, 0.04, 40)
        matrix = np.column_stack([r, r])          # mismos retornos
        out = component_tail_risk(matrix, [20_000.0, 2_000.0], ["BIG", "SMALL"])
        top = out["components"][0]
        assert top["symbol"] == "BIG"             # más exposición → más riesgo

    def test_insufficient_returns(self):
        out = component_tail_risk(np.empty((0, 0)), [], [])
        assert out["status"] == "INSUFICIENTE"


# ── Atribución por factor de mercado ────────────────────────────────

class TestFactorAttribution:
    def test_perfectly_systematic(self):
        factor = np.sin(np.linspace(0, 6, 60)) * 0.02
        matrix = factor.reshape(-1, 1)            # el activo ES el factor
        out = factor_attribution(matrix, [1_000.0], ["AAA"], factor)
        assert out["status"] == "OK"
        assert out["systematic_pct"] > 95.0       # casi todo sistemático
        assert out["r_squared"] > 0.95

    def test_idiosyncratic_when_uncorrelated(self):
        factor = np.sin(np.linspace(0, 6, 60)) * 0.02
        asset = np.cos(np.linspace(0, 6, 60)) * 0.02   # ortogonal al factor
        out = factor_attribution(asset.reshape(-1, 1), [1_000.0], ["AAA"], factor)
        assert out["status"] == "OK"
        assert out["idiosyncratic_pct"] > 50.0

    def test_insufficient_history(self):
        out = factor_attribution(np.ones((10, 1)), [1.0], ["AAA"], np.ones(10))
        assert out["status"] == "INSUFICIENTE"


# ── API / caso de uso ───────────────────────────────────────────────

@pytest.mark.django_db
class TestApi:
    def test_empty_when_no_positions(self, authenticated_client):
        r = authenticated_client.get("/api/portfolio/risk/attribution/")
        assert r.status_code == 200
        assert r.data["status"] in ("EMPTY", "INSUFICIENTE")

    def test_use_case_empty(self, test_user):
        from core.application.use_cases.risk_attribution import RiskAttributionUseCase
        out = RiskAttributionUseCase().execute(owner=test_user)
        assert out["status"] == "EMPTY"
        assert out["components"] == []
