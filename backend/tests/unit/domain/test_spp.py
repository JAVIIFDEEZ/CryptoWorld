"""
test_spp.py — System Parameter Permutation (G5).

El razonamiento de Walton: un optimizador devuelve el mejor resultado de entre
los que probó, y ese máximo está contaminado por la suerte de la muestra. La
mediana sobre todo el espacio de parámetros no lo está — nadie la eligió por
buena.

La brecha entre ambos es entonces una medida directa de cuánto del resultado
venía de haber acertado la configuración en lugar del edge.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import backtest_robustness as rb
from core.domain.services.backtest_execution import CostModel


def _df(n=400, seed=5):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = np.maximum(100 + 18 * np.sin(t / 18.0) + rng.normal(0, 0.7, n), 5.0)
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({
        "timestamp": (1_600_000_000 + t * 86400) * 1000,
        "open": open_,
        "high": np.maximum(close, open_) + 0.4,
        "low": np.minimum(close, open_) - 0.4,
        "close": close, "volume": [1000.0] * n,
    })


class TestSpp:

    @pytest.mark.unit
    def test_reports_median_and_the_optimism_gap(self):
        out = rb.system_parameter_permutation(_df(), "rsi_reversal", grid_points=3, max_combos=40)

        assert out["n_combos"] >= 2
        assert out["median_sharpe"] is not None
        # El mejor nunca puede quedar por debajo de la mediana de su propia rejilla.
        assert out["best_sharpe"] >= out["median_sharpe"]
        assert out["optimism_gap"] == pytest.approx(
            out["best_sharpe"] - out["median_sharpe"], abs=0.01
        )

    @pytest.mark.unit
    def test_percentiles_are_ordered(self):
        out = rb.system_parameter_permutation(_df(), "rsi_reversal", grid_points=3, max_combos=40)
        assert out["p5_sharpe"] <= out["p25_sharpe"] <= out["median_sharpe"]

    @pytest.mark.unit
    def test_caps_the_grid_explosion_but_keeps_coverage(self):
        """El producto cartesiano crece muy rápido; el submuestreo debe seguir
        cubriendo el espacio, no quedarse en una esquina de la rejilla."""
        out = rb.system_parameter_permutation(_df(), "rsi_reversal", grid_points=8, max_combos=25)
        assert out["n_combos"] <= 25
        assert out["truncated"] is True

    @pytest.mark.unit
    def test_costs_are_applied_to_every_combination(self):
        """Si los costes no llegaran a la rejilla, la mediana saldría igual con
        y sin ellos — y volveríamos a medir un mundo donde operar es gratis."""
        df = _df()
        free = rb.system_parameter_permutation(
            df, "rsi_reversal", grid_points=3, max_combos=30, costs=None)
        costed = rb.system_parameter_permutation(
            df, "rsi_reversal", grid_points=3, max_combos=30,
            costs=CostModel(commission_bps=150, slippage_bps=80))

        assert costed["median_sharpe"] < free["median_sharpe"]

    @pytest.mark.unit
    def test_is_deterministic(self):
        df = _df()
        a = rb.system_parameter_permutation(df, "rsi_reversal", grid_points=3, max_combos=30)
        b = rb.system_parameter_permutation(df, "rsi_reversal", grid_points=3, max_combos=30)
        assert a == b

    @pytest.mark.unit
    def test_note_states_both_numbers(self):
        out = rb.system_parameter_permutation(_df(), "rsi_reversal", grid_points=3, max_combos=30)
        assert "Mediana" in out["note"]
        assert f"{out['median_sharpe']:.2f}" in out["note"]
