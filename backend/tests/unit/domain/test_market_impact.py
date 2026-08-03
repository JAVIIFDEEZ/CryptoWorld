"""
test_market_impact.py — Impacto de mercado y capacidad (G4).

Todo backtest supone que las órdenes se ejecutan al precio observado. Eso deja
de ser cierto exactamente cuando la estrategia empieza a gestionar dinero de
verdad: una con Sharpe 3 sobre 10 000 € puede tener Sharpe 0 sobre 10 millones
sin que nada haya cambiado salvo el tamaño.

La capacidad es, por tanto, una propiedad tan real de la estrategia como su
Sharpe — y la que ningún backtest retail reporta.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import market_impact as mi


def _trades(n=20):
    return [{"pnl_pct": 1.0} for _ in range(n)]


class TestImpactModel:

    @pytest.mark.unit
    def test_impact_grows_with_size(self):
        small = mi.impact_bps(1e4, adv=1e8, daily_volatility=0.03)
        large = mi.impact_bps(1e7, adv=1e8, daily_volatility=0.03)
        assert 0 < small < large

    @pytest.mark.unit
    def test_impact_follows_the_square_root_not_a_line(self):
        """Cuadruplicar el tamaño DUPLICA el impacto, no lo cuadruplica. Es el
        consenso empírico, y tiene consecuencias: no hay tamaño gratis, pero
        crecer tampoco cuesta proporcionalmente."""
        base = mi.impact_bps(1e6, adv=1e9, daily_volatility=0.02)
        quadruple = mi.impact_bps(4e6, adv=1e9, daily_volatility=0.02)
        assert quadruple == pytest.approx(base * 2, rel=1e-6)

    @pytest.mark.unit
    def test_a_deeper_market_absorbs_more(self):
        thin = mi.impact_bps(1e6, adv=1e7, daily_volatility=0.03)
        deep = mi.impact_bps(1e6, adv=1e10, daily_volatility=0.03)
        assert thin > deep

    @pytest.mark.unit
    def test_more_volatile_assets_cost_more_to_trade(self):
        calm = mi.impact_bps(1e6, adv=1e9, daily_volatility=0.005)
        wild = mi.impact_bps(1e6, adv=1e9, daily_volatility=0.08)
        assert wild > calm

    @pytest.mark.unit
    @pytest.mark.parametrize("notional,adv,vol", [(0, 1e9, 0.02), (1e6, 0, 0.02), (1e6, 1e9, 0)])
    def test_degenerate_inputs_give_zero(self, notional, adv, vol):
        assert mi.impact_bps(notional, adv, vol) == 0.0


class TestCapacity:

    @staticmethod
    def _returns(mean=0.004, sd=0.01, n=400, seed=1):
        return np.random.default_rng(seed).normal(mean, sd, n)

    @pytest.mark.unit
    def test_capacity_is_lower_in_a_thin_market(self):
        """El mismo edge admite mucho menos dinero en un activo poco líquido."""
        returns, trades = self._returns(), _trades()
        deep = mi.estimate_capacity(returns, trades, adv_usd=1e10, daily_volatility=0.02)
        thin = mi.estimate_capacity(returns, trades, adv_usd=1e6, daily_volatility=0.02)

        assert deep["capacity_usd"] is not None
        assert thin["capacity_usd"] is None or thin["capacity_usd"] < deep["capacity_usd"]

    @pytest.mark.unit
    def test_sharpe_degrades_as_aum_grows(self):
        out = mi.estimate_capacity(self._returns(), _trades(), adv_usd=1e8, daily_volatility=0.03)
        retained = [p["sharpe_retained_pct"] for p in out["curve"]]
        assert retained == sorted(retained, reverse=True)

    @pytest.mark.unit
    def test_flags_levels_that_exceed_the_participation_limit(self):
        """Por encima del límite de participación la orden deja de ser
        ejecutable en un día sin mover el mercado de forma evidente."""
        out = mi.estimate_capacity(self._returns(), _trades(), adv_usd=1e6, daily_volatility=0.02)
        assert any(p["feasible"] is False for p in out["curve"])

    @pytest.mark.unit
    def test_a_high_turnover_strategy_has_less_capacity(self):
        """Cada orden paga su impacto: operar mucho reduce la capacidad aunque
        el edge por operación sea el mismo."""
        returns = self._returns()
        quiet = mi.estimate_capacity(returns, _trades(5), adv_usd=1e8, daily_volatility=0.03)
        busy = mi.estimate_capacity(returns, _trades(200), adv_usd=1e8, daily_volatility=0.03)

        quiet_cap = quiet["capacity_usd"] or 0
        busy_cap = busy["capacity_usd"] or 0
        assert busy_cap <= quiet_cap

    @pytest.mark.unit
    def test_says_when_capacity_cannot_be_estimated(self):
        """Sin volumen ni volatilidad no hay estimación posible, y decirlo es
        mejor que devolver una capacidad inventada."""
        out = mi.estimate_capacity(self._returns(), _trades(), adv_usd=0, daily_volatility=0.02)
        assert out["capacity_usd"] is None
        assert "indeterminada" in out["note"]

    @pytest.mark.unit
    def test_no_trades_means_no_estimate(self):
        assert mi.estimate_capacity(self._returns(), [], 1e8, 0.02)["capacity_usd"] is None

    @pytest.mark.unit
    def test_an_edge_that_does_not_survive_execution_says_so(self):
        """Un edge diminuto en un mercado fino no sobrevive ni al nivel más
        bajo, y el informe debe decirlo en lugar de dar un número."""
        weak = self._returns(mean=0.00001, sd=0.02)
        out = mi.estimate_capacity(weak, _trades(300), adv_usd=5e4, daily_volatility=0.06)
        assert out["capacity_usd"] is None
        assert "no sobrevive" in out["note"]


class TestMarketInputs:

    @staticmethod
    def _df(n=60, price=100.0, volume=1000.0):
        close = np.full(n, price)
        return pd.DataFrame({
            "timestamp": range(n), "open": close, "high": close * 1.01,
            "low": close * 0.99, "close": close, "volume": np.full(n, volume),
        })

    @pytest.mark.unit
    def test_average_daily_volume_in_usd(self):
        assert mi.average_daily_volume_usd(self._df()) == pytest.approx(100_000.0)

    @pytest.mark.unit
    def test_zero_volume_series_gives_zero(self):
        assert mi.average_daily_volume_usd(self._df(volume=0.0)) == 0.0

    @pytest.mark.unit
    def test_daily_volatility_of_a_flat_series_is_zero(self):
        assert mi.daily_volatility_of(self._df()) == pytest.approx(0.0, abs=1e-12)

    @pytest.mark.unit
    def test_daily_volatility_detects_movement(self):
        rng = np.random.default_rng(2)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, 100)))
        df = pd.DataFrame({
            "timestamp": range(100), "open": close, "high": close, "low": close,
            "close": close, "volume": np.full(100, 1000.0),
        })
        assert mi.daily_volatility_of(df) > 0.01
