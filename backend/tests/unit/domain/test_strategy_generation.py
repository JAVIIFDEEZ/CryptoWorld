"""
tests/unit/domain/test_strategy_generation.py — Caso de uso del generador.

Cubre los criterios del PASO 7:
  · el gating de robustez descarta estrategias que solo ajustan ruido,
  · la partición de validación final NUNCA se filtra en la evolución.
"""

import numpy as np
import pandas as pd
import pytest

from core.application.use_cases.generate_strategies import (
    GenerationConfig, generate_strategies,
)
from core.domain.services import strategy_evaluation as ev
from core.domain.services.strategy_generator import GAConfig
from core.domain.services.strategy_spec import seed_specs


def _mean_reverting_df(n=1000, seed=42):
    """Serie con señal real: ciclos sinusoidales + poco ruido (reversión)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    price = 100 + 22 * np.sin(t / 22.0) + 6 * np.sin(t / 7.0) + rng.normal(0, 0.5, n)
    price = np.maximum(price, 5.0)
    return pd.DataFrame({
        "timestamp": (1_600_000_000 + t * 86400) * 1000,
        "open": price, "high": price + 0.3, "low": price - 0.3,
        "close": price, "volume": [1000.0] * n,
    })


def _noise_df(n=900, seed=7):
    """Random walk puro: NINGUNA estrategia debería ser robusta aquí."""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    return pd.DataFrame({
        "timestamp": [1_600_000_000_000 + i * 86400000 for i in range(n)],
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": [1000.0] * n,
    })


def _small_config():
    return GenerationConfig(
        holdout_fraction=0.2, top_k=3, max_gating_attempts=6,
        ga=GAConfig(population_size=20, generations=6, seed=7),
        gating=ev.GatingThresholds(wf_splits=3, pbo_neighbors=6, mc_sims=120, min_trades=10),
    )


class TestRanking:

    @pytest.mark.unit
    def test_generates_ranking_of_robust_finalists(self):
        report = generate_strategies(_mean_reverting_df(), interval="1d", config=_small_config())
        ranking = report["ranking"]
        assert len(ranking) >= 1, "debería encontrar al menos una estrategia robusta"
        # Cada finalista del ranking pasó TODOS los checks del gating
        for f in ranking:
            assert f["passed_gating"] is True
            assert all(f["gating"]["checks"].values())
            assert "holdout_validation" in f
        # El ranking está ordenado por fitness descendente y numerado
        fits = [f["fitness"] for f in ranking]
        assert fits == sorted(fits, reverse=True)
        assert [f["rank"] for f in ranking] == list(range(1, len(ranking) + 1))


class TestGatingDiscardsOverfit:

    @pytest.mark.unit
    def test_pure_noise_yields_no_robust_strategy(self):
        """Sobre ruido, el gating no debe dejar pasar ninguna estrategia: lo que
        brilla in-sample es casualidad y no supera PBO/eficiencia/Monte Carlo."""
        report = generate_strategies(_noise_df(), interval="1d", config=_small_config())
        assert report["summary"]["passed_gating"] == 0
        assert report["ranking"] == []

    @pytest.mark.unit
    def test_gate_spec_rejects_low_trade_strategy(self):
        """Una estrategia que casi nunca opera falla el umbral de nº de trades."""
        df = _mean_reverting_df(n=500)
        rare = {  # entrada casi imposible (RSI < 16 Y RSI > 84 a la vez nunca)
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 7},
                 "op": "lt", "threshold": 16.0},
                {"type": "threshold", "indicator": "RSI", "params": {"window": 7},
                 "op": "gt", "threshold": 84.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 7},
                 "op": "gt", "threshold": 70.0}]},
        }
        gate = ev.gate_spec(df, rare, ev.GatingThresholds(min_trades=12, mc_sims=120, pbo_neighbors=6))
        assert gate["passed"] is False
        assert gate["checks"]["min_trades"] is False


class TestHoldoutNeverLeaks:

    @pytest.mark.unit
    def test_changing_holdout_does_not_change_evolution(self):
        """
        Prueba directa del anti data-snooping: si alteramos SOLO el tramo de
        validación final, la evolución del GA (historia de fitness) debe quedar
        idéntica — porque ese tramo no se usa para evolucionar. Solo cambian las
        métricas de holdout reportadas.
        """
        base = _mean_reverting_df(n=800, seed=1)
        cfg = _small_config()

        # Copia con el holdout (último 20%) reemplazado por datos distintos
        poisoned = base.copy()
        split = int(round(len(base) * (1 - cfg.holdout_fraction)))
        rng = np.random.default_rng(999)
        tampered = 100 * np.exp(np.cumsum(rng.normal(0, 0.05, len(base) - split)))
        poisoned.loc[split:, "close"] = tampered
        poisoned.loc[split:, "open"] = tampered
        poisoned.loc[split:, "high"] = tampered * 1.01
        poisoned.loc[split:, "low"] = tampered * 0.99

        r_base = generate_strategies(base, interval="1d", config=cfg)
        r_pois = generate_strategies(poisoned, interval="1d", config=cfg)

        # La evolución (fitness por generación) NO cambia: el holdout no se ve.
        assert r_base["ga_evolution"]["history"] == r_pois["ga_evolution"]["history"]
        assert r_base["ga_evolution"]["best_fitness"] == r_pois["ga_evolution"]["best_fitness"]
        # El mismo conjunto de specs es evaluado en evolución (mismos hashes/orden)
        assert ([f["spec_hash"] for f in r_base["ranking"]]
                == [f["spec_hash"] for f in r_pois["ranking"]])

    @pytest.mark.unit
    def test_partition_reserves_recent_segment_intact(self):
        df = _mean_reverting_df(n=700)
        report = generate_strategies(df, interval="1d", config=_small_config())
        part = report["data_partition"]
        assert part["evolution_candles"] + part["holdout_candles"] == len(df)
        assert part["holdout_candles"] > 0
        # El holdout son las velas más recientes (split al ~80%)
        assert part["split_index"] == part["evolution_candles"]
