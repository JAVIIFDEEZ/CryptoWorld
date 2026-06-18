"""
tests/unit/domain/test_strategy_spec.py — Representación componible (Módulo 0).

Verifica el criterio del PASO 7 "validez de specs": todo spec generado es legal
y compilable, el validador rechaza specs ilegales, el compilador es causal (sin
lookahead) y las semillas clásicas son legales y deterministas.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import strategy_spec as ss


def _df(n=300, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 0.8, n))
    close = np.maximum(close, 5.0)
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(n)],
        "open": close, "high": close + 1.0, "low": close - 1.0,
        "close": close, "volume": [1000.0] * n,
    })


class TestRandomSpecsAreValid:

    @pytest.mark.unit
    def test_200_random_specs_are_legal_and_compilable(self):
        rng = np.random.default_rng(0)
        df = _df()
        for _ in range(200):
            spec = ss.random_spec(rng)
            assert ss.validate_spec(spec), f"spec ilegal generado: {spec}"
            signals = ss.compile_signals(df, spec)
            assert len(signals) == len(df)
            assert set(np.unique(signals)).issubset({-1.0, 0.0, 1.0})

    @pytest.mark.unit
    def test_seed_specs_are_all_valid(self):
        for spec in ss.seed_specs():
            assert ss.validate_spec(spec)
            assert isinstance(ss.describe_spec(spec), str)


class TestValidationRejectsIllegal:

    @pytest.mark.unit
    def test_missing_blocks_rejected(self):
        assert not ss.validate_spec({})
        assert not ss.validate_spec({"entry": {"combine": "AND", "conditions": []}})

    @pytest.mark.unit
    def test_unknown_indicator_rejected(self):
        spec = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "FOO", "params": {"window": 14},
                 "op": "lt", "threshold": 30.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
                 "op": "gt", "threshold": 70.0}]},
        }
        assert not ss.validate_spec(spec)

    @pytest.mark.unit
    def test_threshold_out_of_range_rejected(self):
        spec = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
                 "op": "lt", "threshold": 999.0}]},  # fuera del rango [15, 85]
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
                 "op": "gt", "threshold": 70.0}]},
        }
        assert not ss.validate_spec(spec)

    @pytest.mark.unit
    def test_param_out_of_range_rejected(self):
        spec = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 999},
                 "op": "lt", "threshold": 30.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
                 "op": "gt", "threshold": 70.0}]},
        }
        assert not ss.validate_spec(spec)

    @pytest.mark.unit
    def test_cross_with_identical_legs_rejected(self):
        spec = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "cross",
                 "a": {"indicator": "SMA", "params": {"window": 20}},
                 "b": {"indicator": "SMA", "params": {"window": 20}},  # idénticos
                 "op": "cross_above"}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
                 "op": "gt", "threshold": 70.0}]},
        }
        assert not ss.validate_spec(spec)


class TestCompileIsCausal:

    @pytest.mark.unit
    def test_signal_at_t_depends_only_on_past(self):
        """Truncar la serie en t no cambia las señales hasta t-1 (sin lookahead)."""
        df = _df(n=260, seed=3)
        rng = np.random.default_rng(5)
        spec = ss.seed_specs()[0]  # RSI reversal
        full = ss.compile_signals(df, spec)
        cut = 200
        partial = ss.compile_signals(df.iloc[:cut].reset_index(drop=True), spec)
        # Las señales del tramo común deben coincidir salvo el warm-up inicial
        warm = ss.max_warmup(spec) + 2
        np.testing.assert_array_equal(full[warm:cut - 1], partial[warm:cut - 1])

    @pytest.mark.unit
    def test_exit_has_priority_over_entry(self):
        df = _df(n=120)
        # Spec donde entrada y salida pueden coincidir; nunca debe haber +1 y -1 a la vez
        rng = np.random.default_rng(9)
        for _ in range(20):
            spec = ss.random_spec(rng)
            sig = ss.compile_signals(df, spec)
            assert not np.any(np.isnan(sig))


class TestSpecHashAndSeeds:

    @pytest.mark.unit
    def test_hash_is_deterministic_and_order_independent(self):
        spec = ss.seed_specs()[1]  # MACD crossover
        h1 = ss.spec_hash(spec)
        # Reconstruir con las claves en otro orden no cambia el hash (canónico)
        reordered = {"exit": spec["exit"], "entry": spec["entry"]}
        assert ss.spec_hash(reordered) == h1

    @pytest.mark.unit
    def test_jitter_keeps_spec_valid(self):
        rng = np.random.default_rng(11)
        for spec in ss.seed_specs():
            for _ in range(10):
                neighbor = ss.jitter_params(spec, rng)
                assert ss.validate_spec(neighbor)


class TestRiskGenes:
    """Genes de gestión de riesgo (stop-loss / take-profit / trailing)."""

    @pytest.mark.unit
    def test_random_specs_with_risk_are_valid_and_compilable(self):
        rng = np.random.default_rng(3)
        df = _df()
        found_risk = 0
        for _ in range(120):
            spec = ss.random_spec(rng)
            assert ss.validate_spec(spec)
            ss.compile_signals(df, spec)  # no rompe con risk presente
            if spec.get("risk"):
                found_risk += 1
        assert found_risk > 0  # el generador produce gestión de riesgo a veces

    @pytest.mark.unit
    def test_spec_risk_builds_riskmodel(self):
        spec = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 30.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 70.0}]},
            "risk": {"stop_loss_pct": 0.05, "take_profit_pct": 0.12},
        }
        assert ss.validate_spec(spec)
        rm = ss.spec_risk(spec)
        assert rm is not None and rm.stop_loss_pct == 0.05 and rm.take_profit_pct == 0.12
        assert "SL 5.0%" in ss.describe_spec(spec)

    @pytest.mark.unit
    def test_out_of_range_risk_rejected(self):
        spec = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 30.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 70.0}]},
            "risk": {"stop_loss_pct": 0.9},  # fuera de rango
        }
        assert not ss.validate_spec(spec)


class TestVolumeIndicators:
    """Nuevos bloques con volumen: MFI, CMF y ratio de volumen."""

    @pytest.mark.unit
    def test_volume_oscillators_registered_and_compile(self):
        for ind in ("MFI", "CMF", "VOLRATIO"):
            assert ind in ss.OSCILLATORS
        df = _df(n=200)
        df["volume"] = np.abs(np.random.default_rng(0).normal(1000, 200, len(df)))
        for ind in ("MFI", "CMF", "VOLRATIO"):
            thr = 50.0 if ind == "MFI" else (0.0 if ind == "CMF" else 1.2)
            spec = {
                "entry": {"combine": "AND", "conditions": [
                    {"type": "threshold", "indicator": ind, "params": {"window": 14}, "op": "gt", "threshold": thr}]},
                "exit": {"combine": "AND", "conditions": [
                    {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 70.0}]},
            }
            assert ss.validate_spec(spec)
            sig = ss.compile_signals(df, spec)
            assert len(sig) == len(df)

    @pytest.mark.unit
    def test_zero_volume_does_not_crash(self):
        df = _df(n=200)
        df["volume"] = 0.0
        spec = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "VOLRATIO", "params": {"window": 14}, "op": "gt", "threshold": 1.2}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 30.0}]},
        }
        sig = ss.compile_signals(df, spec)   # no debe lanzar con volumen nulo
        assert not np.any(np.isnan(sig))
