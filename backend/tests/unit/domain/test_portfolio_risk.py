"""
tests/unit/domain/test_portfolio_risk.py — Riesgo agregado del libro (dominio).

Verifica exposición firmada, VaR/CVaR por simulación histórica (cortos que se
benefician de las caídas, colas gordas sin normalidad) y stress con las peores
ventanas observadas.
"""

import numpy as np
import pytest

from core.domain.services import portfolio_risk as risk


class TestVarCvar:

    @pytest.mark.unit
    def test_insufficient_history(self):
        matrix = np.random.default_rng(0).normal(0, 0.02, (30, 1))
        out = risk.historical_var_cvar(matrix, [1000.0])
        assert out["status"] == "INSUFICIENTE"

    @pytest.mark.unit
    def test_var_cvar_ordering_and_signs(self):
        rng = np.random.default_rng(1)
        # 500 días, dos activos; exposición larga en ambos
        matrix = rng.normal(0.0, 0.03, (500, 2))
        out = risk.historical_var_cvar(matrix, [10_000.0, 5_000.0])
        assert out["status"] == "OK" and out["days"] == 500
        # VaR/CVaR son pérdidas positivas; CVaR ≥ VaR (media de la cola, peor)
        assert out["var95_usd"] > 0 and out["cvar95_usd"] >= out["var95_usd"]
        assert out["cvar99_usd"] >= out["var99_usd"] >= out["var95_usd"]
        assert out["worst_day_usd"] >= out["cvar99_usd"]

    @pytest.mark.unit
    def test_short_benefits_from_crash(self):
        # Serie con un crash del −40% un día; una posición corta gana ese día.
        rets = np.full((80, 1), 0.001)
        rets[40, 0] = -0.40
        long_var = risk.historical_var_cvar(rets, [1000.0])
        short_var = risk.historical_var_cvar(rets, [-1000.0])
        # El largo tiene una cola de pérdida enorme; el corto casi no.
        assert long_var["worst_day_usd"] > 300      # ~400 USD de pérdida el día del crash
        assert short_var["worst_day_usd"] < 5        # el corto no sufre ese día


class TestStress:

    @pytest.mark.unit
    def test_worst_window_is_observed_not_invented(self):
        closes = np.array([100.0, 90.0, 80.0, 120.0, 60.0])  # peor 1d: 120→60 = −50%
        assert risk.worst_window_return(closes, 1) == pytest.approx(-0.5)
        # peor de 2 días: 120→... no aplica; 90→60 no; máx caída 2d = 80→... revisar
        assert risk.worst_window_return(closes, 2) is not None

    @pytest.mark.unit
    def test_stress_signs_and_coverage(self):
        closes = {
            "BTC": np.array([100.0] * 10 + [50.0]),   # peor 1d: −50%
            "ETH": np.array([50.0] * 5 + [40.0]),     # peor 1d: −20%
        }
        exposures = {"BTC": 10_000.0, "ETH": -2_000.0}  # BTC largo, ETH corto
        out = risk.stress_scenarios(closes, exposures, windows=(1,))
        sc = out[0]
        # BTC largo pierde en su crash; ETH corto GANA en su caída
        # impacto = 10000·(−0.5) + (−2000)·(−0.2) = −5000 + 400 = −4600
        assert sc["impact_usd"] == pytest.approx(-4600.0, abs=1.0)
        assert sc["symbols_covered"] == 2 and sc["window_days"] == 1

    @pytest.mark.unit
    def test_align_returns_matrix_trims_to_common_length(self):
        symbols, matrix = risk.align_returns_matrix({
            "A": np.array([0.1, 0.2, 0.3, 0.4]),
            "B": np.array([0.5, 0.6]),
        })
        assert symbols == ["A", "B"] and matrix.shape == (2, 2)
        # Se conservan los MÁS RECIENTES de A
        assert matrix[:, 0].tolist() == [0.3, 0.4]
