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


class TestMultiObjective:

    @pytest.mark.unit
    def test_nsga_returns_pareto_frontier(self):
        cfg = GenerationConfig(
            holdout_fraction=0.2, top_k=3, max_gating_attempts=6, optimizer="nsga",
            ga=GAConfig(population_size=18, generations=5, seed=7),
            gating=ev.GatingThresholds(wf_splits=3, pbo_neighbors=6, mc_sims=100, min_trades=8),
        )
        report = generate_strategies(_mean_reverting_df(), interval="1d", config=cfg)
        assert report["optimizer"] == "nsga"
        assert "pareto_frontier" in report and len(report["pareto_frontier"]) >= 1
        # Cada punto del frente trae sus tres objetivos
        for p in report["pareto_frontier"]:
            assert "oos_sharpe" in p and "max_drawdown_pct" in p and "overfit_gap" in p


class TestLiveTelemetry:
    """Telemetría en vivo del generador: fases, convergencia y curvas de equity."""

    @pytest.mark.unit
    def test_progress_phases_and_equity_curves(self):
        snapshots = []
        generate_strategies(_mean_reverting_df(700), interval="1d",
                            config=_small_config(), progress_cb=snapshots.append)
        phases = [s["phase"] for s in snapshots]
        # Evoluciona → gatea → termina, en ese orden
        assert phases[0] == "evolving"
        assert "gating" in phases
        assert phases[-1] == "done"
        assert phases.index("gating") > phases.index("evolving")

        evolving = [s for s in snapshots if s["phase"] == "evolving"]
        assert len(evolving) == 6                      # una por generación
        last = evolving[-1]
        # Convergencia acumulada y candidatas visualizables con su curva
        assert len(last["history"]) == 6
        assert 0 < len(last["top"]) <= 6
        for card in last["top"]:
            eq = card["equity"]
            assert 2 <= len(eq) <= 120                 # submuestreada
            assert eq[0] == pytest.approx(1.0)         # base normalizada
            assert {"hash", "description", "fitness", "total_return_pct",
                    "n_trades"} <= set(card)

        gating = [s for s in snapshots if s["phase"] == "gating"]
        assert all(g["gating"]["current"] <= g["gating"]["total"] for g in gating)

    @pytest.mark.unit
    def test_equity_curve_helper(self):
        df = _mean_reverting_df(500)
        out = ev.equity_curve(df, seed_specs()[0], points=80)
        assert out["equity"][0] == pytest.approx(1.0)
        assert len(out["equity"]) <= 80
        assert "total_return_pct" in out and "n_trades" in out

    @pytest.mark.unit
    def test_report_includes_hall_of_fame_and_islands(self):
        from dataclasses import replace
        cfg = replace(_small_config(),
                      ga=GAConfig(population_size=20, generations=6, seed=7, islands=2))
        report = generate_strategies(_mean_reverting_df(700), config=cfg)
        assert report["ga_evolution"]["islands"] == 2
        assert len(report["hall_of_fame"]) > 0
        assert {"spec_hash", "description", "fitness"} <= set(report["hall_of_fame"][0])


class TestParsimony:
    """Presión de simplicidad al estilo StrategyQuant."""

    @pytest.mark.unit
    def test_complexity_penalty_lowers_fitness_of_complex_specs(self):
        df = _mean_reverting_df(600)
        # Spec artificialmente complejo: duplicamos condiciones de una semilla
        spec = seed_specs()[0]
        complex_spec = {
            "entry": {"combine": spec["entry"]["combine"],
                      "conditions": spec["entry"]["conditions"] * 3},
            "exit": spec["exit"],
        }
        base = ev.evaluate_fitness(df, complex_spec, n_splits=3, parsimony=0.0)
        penal = ev.evaluate_fitness(df, complex_spec, n_splits=3, parsimony=0.05)
        n_conds = ev.spec_complexity(complex_spec)
        assert n_conds > 3
        assert penal["fitness"] == pytest.approx(
            base["fitness"] - 0.05 * (n_conds - 3), abs=1e-6)
        assert base["complexity"] == n_conds


class TestGenerateUntilTarget:
    """Búsqueda hasta objetivo: rondas con semilla fresca hasta llenar el cupo."""

    @pytest.mark.unit
    def test_noise_exhausts_all_restarts(self):
        from dataclasses import replace
        cfg = replace(_small_config(), max_restarts=2, top_k=2, max_gating_attempts=3)
        snapshots = []
        report = generate_strategies(_noise_df(600), config=cfg,
                                     progress_cb=snapshots.append)
        # En ruido puro no se llena el cupo ⇒ se consumen las dos rondas
        assert report["summary"]["restarts"] == 2
        assert len(report["restarts"]) == 2
        assert report["restarts"][0]["seed"] != report["restarts"][1]["seed"]
        # La telemetría anuncia la ronda y la historia encadena generaciones
        evolving = [s for s in snapshots if s["phase"] == "evolving"]
        assert {s["restart"] for s in evolving} == {1, 2}
        gens = [h["generation"] for h in evolving[-1]["history"]]
        assert gens == sorted(gens) and len(set(gens)) == len(gens)

    @pytest.mark.unit
    def test_restart_stops_early_when_quota_filled(self):
        from dataclasses import replace
        # Cupo mínimo (top_k=1 + colchón) sobre serie con señal clara
        cfg = replace(_small_config(), max_restarts=3, top_k=1, max_gating_attempts=6)
        report = generate_strategies(_mean_reverting_df(700), config=cfg)
        if report["summary"]["passed_gating_total"] >= 3:   # cupo 1+2 lleno en ronda 1
            assert report["summary"]["restarts"] < 3


class TestDecorrelatedBook:
    """El ranking es un libro decorrelacionado, no clones del mismo edge."""

    @pytest.mark.unit
    def test_clones_are_dropped_best_kept(self):
        from core.application.use_cases.generate_strategies import decorrelate_finalists
        rng = np.random.default_rng(0)
        base = rng.normal(0, 0.01, 300)
        series = {
            "A": base,                                   # fitness alto
            "B": base * 1.0001 + 1e-7,                   # clon de A (ρ≈1)
            "C": rng.normal(0, 0.01, 300),               # independiente
        }
        passed = [
            {"spec_hash": "A", "description": "a", "fitness": 1.0},
            {"spec_hash": "B", "description": "b", "fitness": 0.9},
            {"spec_hash": "C", "description": "c", "fitness": 0.5},
        ]
        kept, dropped = decorrelate_finalists(
            passed, lambda f: series[f["spec_hash"]], threshold=0.7)
        assert [k["spec_hash"] for k in kept] == ["A", "C"]   # el clon B cae
        assert dropped[0]["spec_hash"] == "B"
        assert dropped[0]["correlated_with"]["kept_hash"] == "A"
        assert abs(dropped[0]["correlated_with"]["corr"]) >= 0.7

    @pytest.mark.unit
    def test_zero_variance_series_never_clash(self):
        from core.application.use_cases.generate_strategies import decorrelate_finalists
        flat = np.zeros(100)
        passed = [
            {"spec_hash": "A", "description": "a", "fitness": 1.0},
            {"spec_hash": "B", "description": "b", "fitness": 0.9},
        ]
        kept, dropped = decorrelate_finalists(passed, lambda f: flat, threshold=0.7)
        assert len(kept) == 2 and not dropped

    @pytest.mark.unit
    def test_report_includes_correlation_filter(self):
        report = generate_strategies(_mean_reverting_df(700), config=_small_config())
        assert "correlation_filter" in report
        assert report["correlation_filter"]["threshold"] == pytest.approx(0.7)
        assert "correlated_dropped" in report["summary"]


class TestRefinement:
    """Refinamiento local: vecinos jitter re-gateados de cada finalista."""

    @pytest.mark.unit
    def test_refined_finalists_stay_validated(self):
        from dataclasses import replace
        cfg = replace(_small_config(), refine_neighbors=4)
        snapshots = []
        report = generate_strategies(_mean_reverting_df(700), config=cfg,
                                     progress_cb=snapshots.append)
        assert report["summary"]["refined"] >= 0
        for f in report["ranking"]:
            assert f["passed_gating"] is True               # jamás sin validar
            if f.get("refined"):
                assert f["fitness_gain"] > 0
                assert f["refined_from"] != f["spec_hash"]
        # Si hubo finalistas, la fase de refinamiento se anunció en vivo
        if report["summary"]["passed_gating_total"] > 0:
            assert any(s["phase"] == "refining" for s in snapshots)
