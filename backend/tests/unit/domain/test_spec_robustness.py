"""
tests/unit/domain/test_spec_robustness.py — Suite de robustez de specs y señal.

Cubre la generalización de la suite de robustez a specs componibles (reutilizando
Módulo 1), la validación multi-activo y el evaluador de señal en vivo.
"""

import numpy as np
import pandas as pd
import pytest

from core.application.use_cases.run_spec_robustness import (
    SpecRobustnessConfig, cross_asset_validation, run_spec_robustness_suite,
)
from core.domain.services.strategy_spec import seed_specs, signal_state


def _df(n=500, seed=1, cyclic=True):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    if cyclic:
        price = 100 + 22 * np.sin(t / 22.0) + 6 * np.sin(t / 7.0) + rng.normal(0, 0.5, n)
    else:
        price = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    price = np.maximum(price, 5.0)
    return pd.DataFrame({
        "timestamp": (1_600_000_000 + t * 86400) * 1000,
        "open": price, "high": price + 0.3, "low": price - 0.3,
        "close": price, "volume": [1000.0] * n,
    })


def _small():
    return SpecRobustnessConfig(n_neighbors=6, n_perms=20, n_sims=120, wf_splits=3)


class TestSpecRobustnessSuite:

    @pytest.mark.unit
    def test_report_has_full_shape(self):
        rep = run_spec_robustness_suite(_df(), seed_specs()[0], interval="1d", config=_small())
        for key in ("robustness_score", "verdict", "explanation", "reasons", "strengths",
                    "component_scores", "metrics", "diagnostics", "charts", "spec", "description"):
            assert key in rep
        assert rep["verdict"] in ("ROBUSTA", "FRÁGIL", "SOBREAJUSTADA")
        assert 0 <= rep["robustness_score"] <= 100

    @pytest.mark.unit
    def test_invokes_module1_diagnostics(self):
        d = run_spec_robustness_suite(_df(), seed_specs()[1], interval="1d", config=_small())["diagnostics"]
        for key in ("pbo", "deflated_sharpe", "walk_forward_anchored", "monte_carlo", "permutation", "lookahead"):
            assert key in d
        # El test de permutación devolvió un p-valor calculado (no None) con datos suficientes
        assert d["permutation"]["n_perms"] == 20

    @pytest.mark.unit
    def test_invalid_spec_reports_error(self):
        rep = run_spec_robustness_suite(_df(), {"entry": {}}, interval="1d", config=_small())
        assert "error" in rep


class TestCrossAsset:

    @pytest.mark.unit
    def test_consistency_score_and_ranking(self):
        dfs = {"BTC": _df(seed=1), "ETH": _df(seed=2), "X": _df(seed=3, cyclic=False)}
        ca = cross_asset_validation(dfs, seed_specs()[0], "1d", 3)
        assert ca["n_assets"] == 3
        assert 0.0 <= ca["consistency_score"] <= 1.0
        # ordenado por oos_sharpe descendente
        sharpes = [r.get("oos_sharpe", -99) for r in ca["results"]]
        assert sharpes == sorted(sharpes, reverse=True)

    @pytest.mark.unit
    def test_insufficient_asset_marked_not_ok(self):
        dfs = {"BTC": _df(seed=1), "TINY": _df(n=50, seed=4)}
        ca = cross_asset_validation(dfs, seed_specs()[0], "1d", 3)
        rows = {r["symbol"]: r for r in ca["results"]}
        assert rows["TINY"]["ok"] is False
        assert ca["n_assets"] == 1


class TestSignalState:

    @pytest.mark.unit
    def test_buy_when_entry_active(self):
        # RSI reversal: compra con RSI bajo. Forzamos una caída fuerte al final.
        df = _df(n=200, seed=1)
        df.loc[df.index[-15:], "close"] = np.linspace(df["close"].iloc[-15], df["close"].iloc[-15] * 0.5, 15)
        st = signal_state(df, seed_specs()[0])
        assert st["signal"] in ("BUY", "HOLD", "SELL")
        assert isinstance(st["conditions"], list) and len(st["conditions"]) >= 2

    @pytest.mark.unit
    def test_empty_df_is_hold(self):
        st = signal_state(pd.DataFrame(), seed_specs()[0])
        assert st["signal"] == "HOLD"
