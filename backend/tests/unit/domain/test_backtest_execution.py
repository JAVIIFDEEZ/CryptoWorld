"""
tests/unit/domain/test_backtest_execution.py — Motor de ejecución realista.

Verifica costes de transacción (comisión + deslizamiento) y gestión de riesgo
(stop-loss / take-profit / trailing), y que con costes nulos y sin riesgo el
resultado es idéntico al motor histórico.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services.backtest_execution import CostModel, RiskModel, simulate
from core.domain.services.technical_analysis_service import backtest_signals


def _df(close, high=None, low=None):
    close = np.asarray(close, dtype=float)
    high = close if high is None else np.asarray(high, dtype=float)
    low = close if low is None else np.asarray(low, dtype=float)
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(len(close))],
        "open": close, "high": high, "low": low, "close": close, "volume": [1.0] * len(close),
    })


class TestCosts:

    @pytest.mark.unit
    def test_zero_cost_matches_legacy_behaviour(self):
        # Una compra y una venta: sin costes, el retorno es el del precio.
        close = [100, 110, 120, 90]
        signals = np.array([1, 0, -1, 0])
        bt = backtest_signals(_df(close), signals)
        assert bt["total_trades"] == 1
        assert bt["trades"][0]["pnl_pct"] == pytest.approx(20.0, abs=0.01)  # 100→120
        assert bt["total_commission_pct"] == 0.0

    @pytest.mark.unit
    def test_commission_reduces_return(self):
        close = [100, 120]
        signals = np.array([1, -1])
        free = backtest_signals(_df(close), signals)
        costed = backtest_signals(_df(close), signals, costs=CostModel(commission_bps=50))
        assert costed["total_return_pct"] < free["total_return_pct"]
        assert costed["total_commission_pct"] > 0

    @pytest.mark.unit
    def test_overtrading_is_penalised_by_costs(self):
        # Precio plano: sin costes el retorno es 0; con costes y muchas operaciones, negativo.
        close = [100, 100, 100, 100, 100, 100, 100, 100]
        churn = np.array([1, -1, 1, -1, 1, -1, 1, -1])
        flat = backtest_signals(_df(close), churn)
        costed = backtest_signals(_df(close), churn, costs=CostModel(commission_bps=20, slippage_bps=10))
        assert flat["total_return_pct"] == pytest.approx(0.0, abs=0.01)
        assert costed["total_return_pct"] < 0          # las comisiones erosionan el capital
        assert costed["turnover"] > 1                  # rotó varias veces el capital


class TestRisk:

    @pytest.mark.unit
    def test_stop_loss_exits_at_stop(self):
        # Entra a 100; la vela 2 cae a low=90 → stop al 5% (95) salta.
        close = [100, 100, 96, 96]
        low = [100, 99, 90, 96]
        high = [100, 101, 100, 97]
        signals = np.array([1, 0, 0, 0])
        bt = backtest_signals(_df(close, high, low), signals, risk=RiskModel(stop_loss_pct=0.05))
        assert bt["trades"][0]["exit_reason"] == "stop_loss"
        assert bt["trades"][0]["exit_index"] == 2
        assert bt["exit_reasons"].get("stop_loss") == 1

    @pytest.mark.unit
    def test_take_profit_exits_at_target(self):
        close = [100, 100, 112, 112]
        high = [100, 101, 115, 113]
        low = [100, 99, 108, 111]
        signals = np.array([1, 0, 0, 0])
        bt = backtest_signals(_df(close, high, low), signals, risk=RiskModel(take_profit_pct=0.10))
        assert bt["trades"][0]["exit_reason"] == "take_profit"
        assert bt["trades"][0]["pnl_pct"] == pytest.approx(10.0, abs=0.1)

    @pytest.mark.unit
    def test_stop_takes_priority_over_target_same_bar(self):
        # Vela con low<stop y high>tp: la convención conservadora aplica el stop.
        close = [100, 100, 100]
        high = [100, 101, 120]
        low = [100, 99, 90]
        signals = np.array([1, 0, 0])
        bt = backtest_signals(_df(close, high, low), signals,
                              risk=RiskModel(stop_loss_pct=0.05, take_profit_pct=0.10))
        assert bt["trades"][0]["exit_reason"] == "stop_loss"

    @pytest.mark.unit
    def test_trailing_stop_locks_in_gains(self):
        # Sube a 130 y luego cae; el trailing del 10% sale cerca del máximo, no en pérdidas.
        close = [100, 120, 130, 110]
        high = [100, 122, 132, 125]
        low = [100, 118, 128, 110]
        signals = np.array([1, 0, 0, 0])
        bt = backtest_signals(_df(close, high, low), signals, risk=RiskModel(trailing_stop_pct=0.10))
        assert bt["trades"][0]["exit_reason"] == "trailing_stop"
        assert bt["trades"][0]["pnl_pct"] > 0


class TestSimulateDirect:

    @pytest.mark.unit
    def test_equity_curve_length(self):
        close = np.array([100.0, 101, 102, 103])
        sim = simulate(close, close, close, np.array([1, 0, 0, -1]))
        assert len(sim["equity_curve"]) == len(close) + 1


class TestRunBacktestIntegration:
    """Costes y riesgo accesibles desde el backtest clásico de las 5 estrategias."""

    @pytest.mark.unit
    def test_costs_reduce_named_strategy_return(self):
        from core.domain.services.technical_analysis_service import run_backtest_full
        import math
        n = 300
        close = [100 + 0.1 * i + 12 * math.sin(2 * math.pi * i / 30) for i in range(n)]
        df = pd.DataFrame({
            "timestamp": [1700000000000 + i * 86400000 for i in range(n)],
            "open": close, "high": [c * 1.01 for c in close], "low": [c * 0.99 for c in close],
            "close": close, "volume": [1.0] * n,
        })
        free = run_backtest_full(df, "rsi_reversal")
        costed = run_backtest_full(df, "rsi_reversal", costs=CostModel(commission_bps=30, slippage_bps=10))
        assert costed["total_return_pct"] <= free["total_return_pct"]
        assert costed["total_commission_pct"] > 0
        assert "turnover" in costed and "exit_reasons" in costed
