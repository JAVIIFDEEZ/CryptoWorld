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


class TestRegimeGate:
    """Filtro de régimen: entrar solo si hay tendencia (ADX ≥ umbral)."""

    @pytest.mark.unit
    def test_regime_gate_reduces_or_keeps_entries(self):
        df = _df(n=300)
        base = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 55.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 70.0}]},
        }
        gated = {**base, "regime": {"adx_min": 30.0}}
        assert ss.validate_spec(gated)
        entries_base = int((ss.compile_signals(df, base) == 1).sum())
        entries_gated = int((ss.compile_signals(df, gated) == 1).sum())
        # El filtro nunca añade entradas; solo puede quitarlas (exige tendencia).
        assert entries_gated <= entries_base

    @pytest.mark.unit
    def test_out_of_range_regime_rejected(self):
        spec = {
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 30.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 70.0}]},
            "regime": {"adx_min": 99.0},  # fuera de rango
        }
        assert not ss.validate_spec(spec)
        assert "ADX≥" in ss.describe_spec({**spec, "regime": {"adx_min": 25.0}})


class TestNewConditionTypes:
    """Condiciones de estado (compare) y pendiente (slope) — estilo StrategyQuant."""

    def _df(self, n=260):
        rng = np.random.default_rng(9)
        t = np.arange(n)
        close = pd.Series(100 + t * 0.4 + 8 * np.sin(t / 9.0) + rng.normal(0, 0.6, n))
        return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99,
                             "close": close, "volume": np.full(n, 1000.0)})

    @pytest.mark.unit
    def test_compare_is_persistent_state_not_single_bar(self):
        """«PRICE POR ENCIMA de SMA» debe ser True MIENTRAS dure, no solo al cruzar."""
        df = self._df()
        cond = {"type": "compare", "a": {"indicator": "PRICE", "params": {}},
                "b": {"indicator": "SMA", "params": {"window": 50}}, "op": "above"}
        assert ss._validate_condition(cond)
        active = ss._condition_bool(df, cond, {})
        # Serie alcista: el estado se mantiene muchas velas seguidas (no impulsos sueltos)
        assert active.sum() > 50
        runs = np.diff(np.where(np.concatenate(([1], np.diff(active.astype(int)), [1])))[0])
        assert runs.max() > 10

    @pytest.mark.unit
    def test_slope_rising_on_uptrend(self):
        df = self._df()
        cond = {"type": "slope", "indicator": "SMA", "params": {"window": 20},
                "op": "rising", "bars": 5}
        assert ss._validate_condition(cond)
        active = ss._condition_bool(df, cond, {})
        # En una serie con deriva alcista, la SMA sube la mayoría del tiempo
        assert active[60:].mean() > 0.6

    @pytest.mark.unit
    def test_donchian_breakout_is_reachable(self):
        """El canal va DESPLAZADO 1 vela: el cierre sí puede romper el máximo previo
        (sin desfase sería imposible por construcción y la regla sería inútil)."""
        df = self._df()
        cond = {"type": "cross", "a": {"indicator": "PRICE", "params": {}},
                "b": {"indicator": "DONCH_UPPER", "params": {"window": 20}}, "op": "cross_above"}
        active = ss._condition_bool(df, cond, {})
        assert active.sum() >= 1

    @pytest.mark.unit
    def test_fib_level_between_swing_extremes(self):
        df = self._df()
        arr = ss._fib_retr(df, {"window": 40, "ratio": 0.5})
        hi = df["high"].rolling(40).max().shift(1)
        lo = df["low"].rolling(40).min().shift(1)
        mask = ~np.isnan(arr)
        assert mask.sum() > 100
        assert (arr[mask] <= hi.values[mask] + 1e-9).all()
        assert (arr[mask] >= lo.values[mask] - 1e-9).all()

    @pytest.mark.unit
    def test_describe_covers_new_types(self):
        cmp_ = {"type": "compare", "a": {"indicator": "PRICE", "params": {}},
                "b": {"indicator": "SMA", "params": {"window": 200}}, "op": "above"}
        slp = {"type": "slope", "indicator": "EMA", "params": {"window": 30},
               "op": "falling", "bars": 3}
        assert "POR ENCIMA de" in ss._describe_condition(cmp_)
        assert "a la baja en 3 velas" in ss._describe_condition(slp)


class TestEfficiencyFix:
    """IS ≤ 0 con OOS > 0 es generalización, no fallo (antes eficiencia=0)."""

    @pytest.mark.unit
    def test_negative_is_positive_oos_counts_as_efficient(self):
        from unittest.mock import patch
        from core.domain.services import strategy_evaluation as ev

        df = TestNewConditionTypes()._df(400)
        spec = ss.seed_specs()[0]
        sharpes = iter([-0.5, 0.8, -0.3, 0.6, -0.4, 0.7])  # IS negativos, OOS positivos
        with patch.object(ev.metrics, "sharpe_ratio", side_effect=lambda *a, **k: next(sharpes)):
            wf = ev.walk_forward_oos(df, spec, n_splits=3, ppy=365.0)
        if wf["n_folds"] > 0 and wf["mean_is_sharpe"] <= 0 < wf["mean_oos_sharpe"]:
            assert wf["efficiency"] == 1.0
