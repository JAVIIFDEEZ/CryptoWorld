"""
test_robustness_headline.py — Honestidad del Camino A (G9).

La suite de las 5 estrategias corría SIN costes: sus métricas y su veredicto
salían de una simulación en la que operar era gratis, y la optimización de
Optuna premiaba rotaciones que en real sangran en comisiones. Además, el
titular que se leía primero era el Sharpe in-sample, que por construcción es la
cota superior optimista.

Se fija aquí:
  · los costes se aplican a TODA la suite (búsqueda incluida);
  · la respuesta trae un titular fuera de muestra y deflactado;
  · el disclaimer de resultados simulados viaja siempre.
"""

import numpy as np
import pandas as pd
import pytest

from core.application.use_cases.run_robust_backtest import (
    RobustnessConfig, run_robustness_suite,
)


def _trending_df(n=400, seed=3):
    """Serie con tendencia y ruido: da operaciones suficientes para medir."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0015, 0.02, n)))
    return pd.DataFrame({
        "timestamp": [1_600_000_000_000 + i * 86400000 for i in range(n)],
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": [1000.0] * n,
    })


@pytest.fixture(scope="module")
def suite():
    """Suite con presupuesto mínimo (la real son cientos de backtests)."""
    cfg = RobustnessConfig(n_trials=6, wf_splits=2, wf_trials=4, n_perms=10, n_sims=60)
    return run_robustness_suite(_trending_df(), "rsi_reversal", interval="1d", config=cfg)


class TestHeadline:

    @pytest.mark.unit
    def test_headline_leads_with_out_of_sample(self, suite):
        head = suite["headline"]
        assert "oos_sharpe" in head
        assert "deflated_sharpe" in head
        # El in-sample sigue disponible, pero etiquetado como lo que es.
        assert "in_sample_sharpe" in head

    @pytest.mark.unit
    def test_headline_declares_the_number_of_trials(self, suite):
        """Un Sharpe sin decir cuántas configuraciones se probaron no es
        interpretable."""
        head = suite["headline"]
        assert head["n_trials"] >= 1
        assert head["expected_max_sharpe_by_chance"] is not None

    @pytest.mark.unit
    def test_headline_declares_the_costs_applied(self, suite):
        head = suite["headline"]
        assert head["costs_applied"] is True
        assert head["commission_bps"] > 0
        assert head["slippage_bps"] > 0
        assert "NETAS de costes" in head["note"]

    @pytest.mark.unit
    def test_simulated_results_disclaimer_travels_with_the_report(self, suite):
        assert "SIMULADOS" in suite["disclaimer"]


class TestCostsAreApplied:

    @pytest.mark.unit
    def test_costs_reduce_the_reported_return(self):
        """Comprobación directa: la misma suite con costes altos no puede
        rendir igual que sin ellos. Si saliera lo mismo, los costes no se
        estarían aplicando de verdad."""
        df = _trending_df()
        base = RobustnessConfig(n_trials=4, wf_splits=2, wf_trials=3, n_perms=5, n_sims=40)

        free = run_robustness_suite(
            df, "rsi_reversal", interval="1d",
            config=RobustnessConfig(**{**base.__dict__, "commission_bps": 0.0, "slippage_bps": 0.0}),
        )
        expensive = run_robustness_suite(
            df, "rsi_reversal", interval="1d",
            config=RobustnessConfig(**{**base.__dict__, "commission_bps": 100.0, "slippage_bps": 50.0}),
        )

        assert (expensive["metrics"]["annualized_return_pct"]
                < free["metrics"]["annualized_return_pct"])

    @pytest.mark.unit
    def test_default_config_charges_costs(self):
        cfg = RobustnessConfig()
        assert cfg.commission_bps > 0 and cfg.slippage_bps > 0
