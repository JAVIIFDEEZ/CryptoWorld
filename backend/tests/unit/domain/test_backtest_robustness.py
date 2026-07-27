"""
tests/unit/domain/test_backtest_robustness.py — Diagnósticos de robustez.

Incluye los casos sintéticos exigidos: uno claramente SOBREAJUSTADO (PBO alto,
DSR bajo) y uno ROBUSTO (lo contrario), con construcciones deterministas.
"""

import math

import numpy as np
import pandas as pd
import pytest

from core.domain.services import backtest_robustness as rb


def _df(n=320, seed=None, drift=0.15, wave=12.0, period=30):
    if seed is not None:
        rng = np.random.default_rng(seed)
        closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    else:
        closes = np.array([100 + drift * i + wave * math.sin(2 * math.pi * i / period) for i in range(n)])
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(n)],
        "open": closes * 0.99, "high": closes * 1.02,
        "low": closes * 0.98, "close": closes, "volume": [1000.0] * n,
    })


# ── PBO (CSCV) ─────────────────────────────────────────────────────

class TestPBO:

    @pytest.mark.unit
    def test_pbo_low_when_one_config_dominates(self):
        rng = np.random.default_rng(1)
        M = rng.normal(0, 0.01, (120, 8))
        M[:, 0] += 0.02  # un trial mejor en TODAS las filas → robusto
        result = rb.probability_of_backtest_overfitting(M, n_partitions=10)
        assert result["pbo"] < 0.1

    @pytest.mark.unit
    def test_pbo_high_for_lucky_block_overfit(self):
        # Cada trial solo destaca en su propio bloque: el mejor IS es del
        # montón OOS → sobreajuste claro.
        rng = np.random.default_rng(1)
        S, block, N = 10, 14, 10
        M = rng.normal(0, 0.004, (S * block, N))
        for j in range(N):
            M[j * block:(j + 1) * block, j] += 0.05
        result = rb.probability_of_backtest_overfitting(M, n_partitions=10)
        assert result["pbo"] > 0.7

    @pytest.mark.unit
    def test_pbo_none_with_single_config(self):
        assert rb.probability_of_backtest_overfitting(np.zeros((100, 1)))["pbo"] is None


# ── Deflated Sharpe Ratio ──────────────────────────────────────────

class TestDeflatedSharpe:

    @pytest.mark.unit
    def test_dsr_high_for_strong_sharpe_few_trials(self):
        rng = np.random.default_rng(2)
        returns = rng.normal(0.02, 0.01, 250)            # Sharpe/periodo alto
        trials = [rng.normal(0.02, 0.01, 250) for _ in range(3)]
        assert rb.deflated_sharpe_ratio(returns, trials)["dsr"] > 0.7

    @pytest.mark.unit
    def test_dsr_low_for_modest_sharpe_many_trials(self):
        rng = np.random.default_rng(2)
        returns = rng.normal(0.003, 0.02, 250)           # Sharpe/periodo bajo
        trials = [rng.normal(rng.normal(0, 0.015), 0.02, 250) for _ in range(60)]
        assert rb.deflated_sharpe_ratio(returns, trials)["dsr"] < 0.3

    @pytest.mark.unit
    def test_dsr_none_for_short_series(self):
        assert rb.deflated_sharpe_ratio([0.01, 0.02], [[0.01, 0.02]])["dsr"] is None


# ── Monte Carlo ────────────────────────────────────────────────────

class TestMonteCarlo:

    @pytest.mark.unit
    def test_percentiles_ordered_and_prob_in_range(self):
        pnls = [3.0, -2.0, 5.0, -1.0, 4.0, -3.0, 2.0, 1.5]
        mc = rb.monte_carlo_simulation(pnls, n_sims=500, seed=3)
        assert mc["n_sims"] == 500
        r = mc["return_pct"]
        assert r["p5"] <= r["p50"] <= r["p95"]
        assert 0 <= mc["prob_profit_pct"] <= 100
        assert len(mc["return_distribution"]) == 500

    @pytest.mark.unit
    def test_deterministic_with_seed(self):
        pnls = [2.0, -1.0, 3.0, -2.0, 1.0]
        a = rb.monte_carlo_simulation(pnls, n_sims=200, seed=9)
        b = rb.monte_carlo_simulation(pnls, n_sims=200, seed=9)
        assert a["return_pct"] == b["return_pct"]

    @pytest.mark.unit
    def test_insufficient_trades(self):
        assert rb.monte_carlo_simulation([1.0], n_sims=100)["n_sims"] == 0


# ── Permutation test ───────────────────────────────────────────────

class TestPermutation:

    @pytest.mark.unit
    def test_returns_valid_p_value(self):
        df = _df(seed=7)  # random walk: edge dudoso
        res = rb.permutation_test(
            df, "rsi_reversal", {"window": 14, "oversold": 30, "overbought": 70},
            observed_sharpe=0.5, n_perms=30, seed=1,
        )
        assert 0 < res["p_value"] <= 1
        assert res["n_perms"] == 30


# ── Optimización (Optuna) ──────────────────────────────────────────

class TestOptimization:

    @pytest.mark.unit
    def test_optimize_returns_trials_matrix(self):
        df = _df()
        opt = rb.optimize_parameters(df, "rsi_reversal", n_trials=10, seed=4)
        assert opt["n_trials"] >= 1
        assert set(opt["best_params"]) == {"window", "oversold", "overbought"}
        # cada trial guarda sus retornos por vela (necesarios para PBO/DSR)
        assert all(len(t["bar_returns"]) == len(df) for t in opt["trials"])
        assert len(opt["ranking"]) >= 1


# ── Walk-forward ───────────────────────────────────────────────────

class TestWalkForward:

    @pytest.mark.unit
    def test_walk_forward_reports_oos_and_efficiency(self):
        df = _df(n=320)
        wf = rb.walk_forward_analysis(df, "rsi_reversal", n_splits=3, anchored=True, n_trials=6, seed=5)
        assert wf["n_splits"] >= 1
        assert wf["efficiency"] is not None
        assert wf["mean_oos_sharpe"] is not None
        for fold in wf["folds"]:
            assert "oos_sharpe" in fold and "best_params" in fold
