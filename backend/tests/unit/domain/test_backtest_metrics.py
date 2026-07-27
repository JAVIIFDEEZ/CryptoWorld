"""
tests/unit/domain/test_backtest_metrics.py — Métricas de rendimiento/riesgo.

Entradas conocidas con resultado analítico cuando es posible; en otro caso
se verifican propiedades (signo, monotonía, relaciones entre métricas).
"""

import math

import pytest

from core.domain.services import backtest_metrics as bm


class TestRiskAdjustedRatios:

    @pytest.mark.unit
    def test_sharpe_known_value(self):
        # mean=0.02, std(ddof=1)=0.01 → Sharpe = 2 * sqrt(252)
        sharpe = bm.sharpe_ratio([0.01, 0.02, 0.03], periods_per_year=252)
        assert sharpe == pytest.approx(2 * math.sqrt(252), rel=1e-6)

    @pytest.mark.unit
    def test_sharpe_zero_when_no_variance(self):
        assert bm.sharpe_ratio([0.01, 0.01, 0.01], 252) == 0.0

    @pytest.mark.unit
    def test_sharpe_sign_follows_mean(self):
        assert bm.sharpe_ratio([0.02, -0.01, 0.03, 0.01], 252) > 0
        assert bm.sharpe_ratio([-0.02, 0.01, -0.03, -0.01], 252) < 0

    @pytest.mark.unit
    def test_sortino_uses_only_downside(self):
        # Con mismas medias, menos volatilidad bajista ⇒ Sortino ≥ Sharpe
        returns = [0.02, -0.01, 0.02, -0.01]
        assert bm.sortino_ratio(returns, 252) >= bm.sharpe_ratio(returns, 252)

    @pytest.mark.unit
    def test_calmar_positive_for_growing_equity(self):
        equity = [100, 110, 105, 130, 160]
        assert bm.calmar_ratio(equity, 365) > 0


class TestReturnAndDrawdown:

    @pytest.mark.unit
    def test_annualized_return_doubling_one_year(self):
        # 365 periodos a ppy=365 = 1 año; duplicar = +100%
        assert bm.annualized_return([100] + [None] * 0 + list(_ramp(100, 200, 365)), 365) == pytest.approx(100.0, rel=1e-6)

    @pytest.mark.unit
    def test_max_drawdown_known(self):
        # pico 120, valle 60 → 50%
        assert bm.max_drawdown([100, 120, 60, 90]) == pytest.approx(50.0)

    @pytest.mark.unit
    def test_max_drawdown_zero_when_monotonic(self):
        assert bm.max_drawdown([100, 110, 120, 130]) == 0.0


class TestTailRiskAndProfitFactor:

    @pytest.mark.unit
    def test_var_and_cvar_non_negative_and_ordered(self):
        returns = [-0.08, -0.05, -0.02, 0.0, 0.01, 0.02, 0.03, 0.05]
        var = bm.historical_var(returns, 0.95)
        cvar = bm.historical_cvar(returns, 0.95)
        assert var >= 0 and cvar >= 0
        assert cvar >= var  # la cola media es al menos tan grave como el cuantil

    @pytest.mark.unit
    def test_profit_factor_known(self):
        # ganancias 30, pérdidas 10 → 3.0
        assert bm.profit_factor([10, -5, 20, -5]) == pytest.approx(3.0)

    @pytest.mark.unit
    def test_profit_factor_infinite_without_losses(self):
        assert math.isinf(bm.profit_factor([5, 10, 2]))


class TestAnnualizationAndAggregate:

    @pytest.mark.unit
    def test_annualization_factor_by_interval(self):
        assert bm.annualization_factor("1d") == 365
        assert bm.annualization_factor("1h") == 8760
        assert bm.annualization_factor("desconocido") == 365

    @pytest.mark.unit
    def test_compute_metrics_serializable(self):
        full = {
            "bar_returns": [0.01, -0.005, 0.02, 0.0, -0.01, 0.015],
            "equity_curve": [100, 101, 100.5, 102.5, 102.5, 101.5, 103.0],
            "trades": [{"pnl_pct": 5}, {"pnl_pct": -2}, {"pnl_pct": 3}],
            "exposure_pct": 50.0,
            "max_drawdown_pct": 1.9,
        }
        m = bm.compute_metrics(full, periods_per_year=365)
        for key in ("sharpe", "sortino", "calmar", "var_95_pct", "cvar_95_pct",
                    "profit_factor", "exposure_pct", "max_drawdown_pct"):
            assert key in m
        assert m["profit_factor"] == pytest.approx(4.0)  # 8 / 2


def _ramp(start, end, n):
    """Serie geométrica de start a end en n pasos (crecimiento compuesto)."""
    factor = (end / start) ** (1 / n)
    v = start
    out = []
    for _ in range(n):
        v *= factor
        out.append(v)
    return out
