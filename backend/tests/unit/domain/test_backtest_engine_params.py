"""
tests/unit/domain/test_backtest_engine_params.py — Motor parametrizable.

Verifica que parametrizar las estrategias no rompe la salida pública del
motor (compatibilidad) y que run_backtest_full expone equity, retornos y
todas las operaciones para la suite de robustez.
"""

import math

import pandas as pd
import pytest

from core.domain.services.technical_analysis_service import (
    STRATEGIES,
    run_backtest,
    run_backtest_full,
    strategy_defaults,
    strategy_param_space,
)

_PUBLIC_KEYS = {
    "strategy", "strategy_key", "description", "initial_capital", "final_capital",
    "total_return_pct", "buy_hold_return_pct", "start_date", "end_date",
    "candles_count", "total_trades", "win_rate_pct", "avg_win_pct",
    "avg_loss_pct", "max_drawdown_pct", "trades",
}


def _df(n=300):
    closes = [100 + 0.2 * i + 10 * math.sin(2 * math.pi * i / 25) for i in range(n)]
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(n)],
        "open": [c * 0.99 for c in closes], "high": [c * 1.02 for c in closes],
        "low": [c * 0.98 for c in closes], "close": closes, "volume": [1000.0] * n,
    })


class TestParamSpace:

    @pytest.mark.unit
    def test_every_strategy_exposes_param_space(self):
        for key in STRATEGIES:
            space = strategy_param_space(key)
            assert space, f"{key} sin param_space"
            for p in space:
                assert {"name", "type", "low", "high", "default"} <= set(p)
                assert p["low"] <= p["default"] <= p["high"]
                assert p["type"] in ("int", "float")


class TestBackwardCompatibility:

    @pytest.mark.unit
    def test_public_output_keys_unchanged(self):
        out = run_backtest(_df(), "rsi_reversal")
        assert set(out.keys()) == _PUBLIC_KEYS
        # No filtra datos internos pesados al endpoint clásico
        assert "equity_curve" not in out and "bar_returns" not in out

    @pytest.mark.unit
    def test_trades_truncated_to_last_20(self):
        out = run_backtest(_df(), "sma_crossover")
        assert len(out["trades"]) <= 20

    @pytest.mark.unit
    def test_unknown_strategy_returns_error(self):
        assert "error" in run_backtest(_df(), "no_existe")

    @pytest.mark.unit
    def test_insufficient_data_returns_error(self):
        assert "error" in run_backtest(_df(n=30), "rsi_reversal")


class TestFullOutput:

    @pytest.mark.unit
    def test_full_exposes_equity_and_returns(self):
        df = _df()
        full = run_backtest_full(df, "rsi_reversal")
        assert len(full["equity_curve"]) == len(df) + 1
        assert len(full["bar_returns"]) == len(df)
        assert full["total_trades"] == len(full["trades"])  # todas las operaciones
        assert "exposure_pct" in full and "params" in full

    @pytest.mark.unit
    def test_params_alter_results(self):
        df = _df()
        default = run_backtest_full(df, "rsi_reversal")
        tuned = run_backtest_full(df, "rsi_reversal", params={"window": 7, "oversold": 25, "overbought": 75})
        assert default["params"] != tuned["params"]
        # Distintos parámetros → distinto comportamiento (señales/resultado)
        assert (default["total_trades"], default["total_return_pct"]) != (
            tuned["total_trades"], tuned["total_return_pct"]
        )

    @pytest.mark.unit
    def test_defaults_reproduce_classic(self):
        df = _df()
        implicit = run_backtest_full(df, "rsi_reversal")
        explicit = run_backtest_full(df, "rsi_reversal", params=strategy_defaults("rsi_reversal"))
        assert implicit["total_return_pct"] == explicit["total_return_pct"]
        assert implicit["total_trades"] == explicit["total_trades"]
