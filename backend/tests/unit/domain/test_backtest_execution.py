"""
tests/unit/domain/test_backtest_execution.py — Motor de ejecución realista.

Verifica costes de transacción (comisión + deslizamiento), gestión de riesgo
(stop-loss / take-profit / trailing) y la convención de ejecución: una señal de
la vela `i` se rellena a la APERTURA de la vela `i+1`, no al cierre que la
originó.

Las series de estos tests son deliberadamente cortas, así que el desplazamiento
de una vela se nota entero — por eso varias fijan el precio de la vela de
ejecución: lo que se comprueba es el mecanismo, no una rentabilidad.
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
        """Con el relleno histórico (misma vela) el motor sigue dando lo de antes.

        Se pide explícitamente `fill_next_bar=False`: este test existe para
        comprobar la equivalencia con el motor anterior, no para medir
        rendimiento."""
        close = np.array([100, 110, 120, 90], dtype=float)
        signals = np.array([1, 0, -1, 0])
        sim = simulate(close, close, close, signals, fill_next_bar=False)
        assert len(sim["trades"]) == 1
        assert sim["trades"][0]["pnl_pct"] == pytest.approx(20.0, abs=0.01)  # 100→120
        assert sim["total_commission"] == 0.0

    @pytest.mark.unit
    def test_signal_fills_at_the_next_bar_open(self):
        """La señal de la vela i se rellena a la apertura de la i+1.

        Con apertura distinta del cierre se ve sin ambigüedad de qué precio sale
        la ejecución: entra a 105 (apertura de la vela 1), no a 100."""
        df = pd.DataFrame({
            "timestamp": [1700000000000 + i * 86400000 for i in range(4)],
            "open":  [100.0, 105.0, 118.0, 130.0],
            "high":  [100.0, 112.0, 122.0, 132.0],
            "low":   [100.0, 104.0, 117.0, 129.0],
            "close": [100.0, 110.0, 120.0, 131.0],
            "volume": [1.0] * 4,
        })
        bt = backtest_signals(df, np.array([1, 0, -1, 0]))
        trade = bt["trades"][0]
        assert trade["entry_price"] == pytest.approx(105.0)   # apertura de la vela 1
        assert trade["exit_price"] == pytest.approx(130.0)    # apertura de la vela 3
        assert trade["entry_index"] == 1 and trade["exit_index"] == 3

    @pytest.mark.unit
    def test_signal_on_the_last_bar_is_never_executed(self):
        """No hay vela siguiente en la que rellenar: la orden no llega a existir.

        Es la consecuencia deliberada del desplazamiento — no se puede operar
        sobre información que llega justo cuando se acaban los datos."""
        bt = backtest_signals(_df([100, 110, 120]), np.array([0, 0, 1]))
        assert bt["total_trades"] == 0

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
        """Sube y luego cae; el trailing del 10% sale cerca del máximo, en ganancias.

        La vela 1 es plana a 100 porque ahí es donde entra la orden (la señal es
        de la vela 0): así la subida posterior es ganancia del trade y no un
        salto que la entrada se pierde."""
        close = [100, 100, 130, 110]
        high = [100, 100, 132, 125]
        low = [100, 100, 128, 110]
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


class TestSizing:
    """Dimensionamiento de posición (fraction / risk), con 'full' como base."""

    @pytest.mark.unit
    def test_full_equals_no_sizing(self):
        from core.domain.services.backtest_execution import SizingModel
        close = [100, 120, 110, 130]
        signals = np.array([1, 0, -1, 0])
        base = backtest_signals(_df(close), signals)
        full = backtest_signals(_df(close), signals, sizing=SizingModel(mode="full"))
        assert base["total_return_pct"] == pytest.approx(full["total_return_pct"], abs=1e-6)

    @pytest.mark.unit
    def test_fraction_dampens_return_and_drawdown(self):
        from core.domain.services.backtest_execution import SizingModel
        close = [100, 150, 90, 140]   # gran sube/baja
        signals = np.array([1, 0, 0, -1])
        full = backtest_signals(_df(close), signals)
        half = backtest_signals(_df(close), signals, sizing=SizingModel(mode="fraction", fraction=0.5))
        # Invertir la mitad reduce tanto la ganancia como el drawdown
        assert abs(half["total_return_pct"]) < abs(full["total_return_pct"])
        assert half["max_drawdown_pct"] <= full["max_drawdown_pct"] + 1e-6

    @pytest.mark.unit
    def test_risk_sizing_caps_at_capital(self):
        from core.domain.services.backtest_execution import SizingModel, RiskModel
        # Cuatro velas: la señal de la 0 entra a la apertura de la 1 (100) y la
        # de la 2 sale a la apertura de la 3 (110). Con relleno desplazado hace
        # falta una vela más que antes para completar el viaje de ida y vuelta.
        close = [100, 100, 105, 110]
        signals = np.array([1, 0, -1, 0])
        bt = backtest_signals(
            _df(close), signals,
            sizing=SizingModel(mode="risk", risk_pct=0.02),
            risk=RiskModel(stop_loss_pct=0.05),
        )
        # notional = 2%/5% = 40% del capital → exposición parcial, retorno positivo pero menor
        assert 0 < bt["total_return_pct"] < 10


class TestNewExits:
    """Salida por tiempo y stop por ATR (estilo StrategyQuant)."""

    @pytest.mark.unit
    def test_time_exit_closes_after_max_bars(self):
        close = np.full(50, 100.0)
        signals = np.zeros(50); signals[2] = 1   # compra y nunca llega señal de venta
        out = simulate(close, close, close, signals, risk=RiskModel(max_bars=7))
        assert len(out["trades"]) >= 1
        t = out["trades"][0]
        assert t["exit_reason"] == "time_exit"
        assert t["exit_index"] - t["entry_index"] == 7

    @pytest.mark.unit
    def test_atr_stop_triggers_at_entry_atr_multiple(self):
        n = 30
        close = np.full(n, 100.0); close[20:] = 89.0   # caída del 11%
        low = close.copy(); high = close.copy()
        atr = np.full(n, 2.0)                          # ATR constante de 2.0
        signals = np.zeros(n); signals[5] = 1
        out = simulate(close, high, low, signals, risk=RiskModel(atr_stop_mult=3.0), atr=atr)
        t = out["trades"][0]
        # stop = 100 − 3×2 = 94: salta en la vela de la caída, al precio del stop
        assert t["exit_reason"] == "atr_stop"
        assert abs(t["exit_price"] - 94.0) < 1e-6
