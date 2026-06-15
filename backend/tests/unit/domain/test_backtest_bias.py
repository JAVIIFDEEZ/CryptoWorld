"""
tests/unit/domain/test_backtest_bias.py — Detectores de sesgo del backtest.
"""

import math

import numpy as np
import pandas as pd
import pytest

from core.domain.services import backtest_bias as bias
from core.domain.services.technical_analysis_service import (
    generate_signals,
    strategy_indicator_series,
)


def _df(n=300):
    closes = [100 + 0.2 * i + 10 * math.sin(2 * math.pi * i / 25) for i in range(n)]
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(n)],
        "open": [c * 0.99 for c in closes], "high": [c * 1.02 for c in closes],
        "low": [c * 0.98 for c in closes], "close": closes, "volume": [1000.0] * n,
    })


class TestLookahead:

    @pytest.mark.unit
    def test_engine_strategy_has_no_lookahead(self):
        df = _df()
        result = bias.detect_lookahead_bias(
            df, lambda d: generate_signals(d, "rsi_reversal"), seed=1
        )
        assert result["is_leaky"] is False
        assert result["leaks"] == 0
        assert result["checked"] > 0

    @pytest.mark.unit
    def test_detects_deliberate_future_leak(self):
        df = _df()

        def leaky(d):
            c = d["close"].values
            s = np.zeros(len(c))
            for i in range(len(c) - 1):
                if c[i + 1] > c[i]:   # mira la vela SIGUIENTE → fuga del futuro
                    s[i] = 1
            return s

        result = bias.detect_lookahead_bias(df, leaky, seed=1)
        assert result["is_leaky"] is True
        assert result["leaks"] > 0


class TestRecursiveInstability:

    @pytest.mark.unit
    def test_sma_is_stable(self):
        df = _df()
        result = bias.detect_recursive_instability(
            df, lambda d: strategy_indicator_series(d, "sma_crossover")
        )
        # La SMA no es recursiva: no debe derivar al cambiar el histórico inicial
        assert result["max_rel_drift"] < 1e-6
        assert result["is_unstable"] is False

    @pytest.mark.unit
    def test_ema_drifts_more_than_sma(self):
        df = _df()
        ema = bias.detect_recursive_instability(
            df, lambda d: strategy_indicator_series(d, "ema_trend")
        )
        sma = bias.detect_recursive_instability(
            df, lambda d: strategy_indicator_series(d, "sma_crossover")
        )
        # La EMA es recursiva: arrastra el seed → deriva > SMA
        assert ema["max_rel_drift"] > sma["max_rel_drift"]
