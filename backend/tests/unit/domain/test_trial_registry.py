"""
test_trial_registry.py — El registro de pruebas del generador (G1).

`TrialRegistry` es la pieza que conecta lo que la búsqueda hace de verdad con
los controles de sobreajuste. Antes, PBO y Deflated Sharpe se calculaban sobre
perturbaciones de la campeona ya elegida; ahora reciben las series de los
genomas realmente evaluados y el recuento real de pruebas.

Lo que se fija aquí:
  · el recuento cuenta genomas DISTINTOS (reevaluar un hash no es otra prueba);
  · el reservorio acota la memoria sin sesgar la muestra hacia los mejores;
  · el pipeline alimenta el gating con esos trials y lo declara en `source`;
  · sin trials, `gate_spec` sigue funcionando pero avisa de lo que mide.
"""

import numpy as np
import pandas as pd
import pytest

from core.application.use_cases.generate_strategies import (
    GenerationConfig, TrialRegistry, generate_strategies,
)
from core.domain.services import strategy_evaluation as ev
from core.domain.services.strategy_generator import GAConfig


def _mean_reverting_df(n=1000, seed=42):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    price = 100 + 22 * np.sin(t / 22.0) + 6 * np.sin(t / 7.0) + rng.normal(0, 0.5, n)
    price = np.maximum(price, 5.0)
    return pd.DataFrame({
        "timestamp": (1_600_000_000 + t * 86400) * 1000,
        "open": price, "high": price + 0.3, "low": price - 0.3,
        "close": price, "volume": [1000.0] * n,
    })


def _small_config():
    return GenerationConfig(
        holdout_fraction=0.2, top_k=3, max_gating_attempts=6,
        ga=GAConfig(population_size=20, generations=6, seed=7),
        gating=ev.GatingThresholds(wf_splits=3, pbo_neighbors=6, mc_sims=120, min_trades=10),
    )


def _series(n=50, seed=0):
    return list(np.random.default_rng(seed).normal(0.001, 0.01, n))


class TestTrialRegistry:

    @pytest.mark.unit
    def test_counts_distinct_genomes_only(self):
        """El GA cachea por hash: reevaluar el mismo genoma no es otra prueba,
        y contarlo inflaría la deflación sin motivo."""
        reg = TrialRegistry(capacity=10)
        reg.add("hash-a", _series(seed=1))
        reg.add("hash-a", _series(seed=1))
        reg.add("hash-b", _series(seed=2))

        assert reg.total_seen == 2
        assert len(reg.returns) == 2

    @pytest.mark.unit
    def test_counts_trials_without_usable_series(self):
        """Una estrategia degenerada (sin operaciones) es una prueba hecha
        aunque su serie no sirva para la varianza: cuenta para el N."""
        reg = TrialRegistry(capacity=10)
        reg.add("degenerada", [])
        reg.add("normal", _series(seed=3))

        assert reg.total_seen == 2
        assert len(reg.returns) == 1

    @pytest.mark.unit
    def test_reservoir_caps_memory_but_not_the_count(self):
        """El reservorio acota lo que se guarda; el recuento sigue creciendo,
        que es lo que deflacta el Sharpe."""
        reg = TrialRegistry(capacity=20, seed=5)
        for i in range(500):
            reg.add(f"hash-{i}", _series(seed=i))

        assert reg.total_seen == 500
        assert len(reg.returns) == 20
        assert reg.summary() == {"evaluated": 500, "sampled": 20, "capacity": 20}

    @pytest.mark.unit
    def test_reservoir_samples_across_the_whole_run(self):
        """Muestreo uniforme, no top-M: si el reservorio se quedara con los
        mejores subestimaría la varianza entre pruebas, que es justo el término
        que eleva el umbral del DSR — se reproduciría el sesgo optimista.

        Se comprueba con series cuya media crece de forma monótona: la muestra
        debe contener también pruebas tempranas, no solo las últimas.
        """
        reg = TrialRegistry(capacity=30, seed=11)
        for i in range(300):
            reg.add(f"hash-{i}", list(np.full(50, i * 0.001)))

        means = sorted(float(np.mean(s)) for s in reg.returns)
        assert means[0] < 0.100, "la muestra solo contiene pruebas tardías"
        assert len(set(means)) > 10, "la muestra no cubre el rango de la ejecución"

    @pytest.mark.unit
    def test_is_deterministic_for_a_given_seed(self):
        def run():
            reg = TrialRegistry(capacity=15, seed=99)
            for i in range(200):
                reg.add(f"hash-{i}", _series(seed=i))
            return [float(np.mean(s)) for s in reg.returns]

        assert run() == run()


class TestGateSpecSource:
    """`gate_spec` debe declarar de dónde salen sus números."""

    @pytest.fixture
    def df_and_spec(self):
        from core.domain.services.strategy_spec import seed_specs
        return _mean_reverting_df(400), seed_specs()[0]

    @pytest.mark.unit
    def test_without_trials_falls_back_and_says_so(self, df_and_spec):
        """Uso suelto (sin buscador detrás): sigue funcionando, pero deja claro
        que mide estabilidad paramétrica y no sobreajuste de selección."""
        df, spec = df_and_spec
        out = ev.gate_spec(df, spec, ev.GatingThresholds(wf_splits=3, pbo_neighbors=4, mc_sims=60))

        block = out["metrics"]["overfitting"]
        assert block["source"] == "parameter_jitter"
        assert "NO" in block["note"]

    @pytest.mark.unit
    def test_with_trials_uses_them_and_deflates_by_real_n(self, df_and_spec):
        df, spec = df_and_spec
        trials = [_series(n=120, seed=s) for s in range(25)]

        out = ev.gate_spec(
            df, spec, ev.GatingThresholds(wf_splits=3, pbo_neighbors=4, mc_sims=60),
            trial_returns=trials, n_evaluations=4_000,
        )

        block = out["metrics"]["overfitting"]
        assert block["source"] == "search_trials"
        assert block["deflated_sharpe"]["n_trials"] == 4_000
        assert block["deflated_sharpe"]["n_trials_sampled"] == 25
        assert out["metrics"]["deflated_sharpe"] is not None

    @pytest.mark.unit
    def test_deflated_sharpe_does_not_gate(self, df_and_spec):
        """Decisión de producto: el DSR se reporta, no bloquea. El gating sigue
        decidiéndose por los checks de siempre."""
        df, spec = df_and_spec
        trials = [_series(n=120, seed=s) for s in range(25)]
        out = ev.gate_spec(
            df, spec, ev.GatingThresholds(wf_splits=3, pbo_neighbors=4, mc_sims=60),
            trial_returns=trials, n_evaluations=50_000,
        )

        assert "deflated_sharpe" not in out["checks"]
        assert set(out["checks"]) == {
            "min_trades", "no_lookahead", "wf_efficiency", "pbo", "mc_p5_positive",
        }


class TestPipelineWiring:

    @pytest.mark.unit
    def test_report_carries_the_multiplicity_context(self):
        """El informe debe decir cuántas pruebas se hicieron y qué Sharpe da el
        azar con ese número: sin ese contexto, el Sharpe no es comparable."""
        report = generate_strategies(_mean_reverting_df(), interval="1d", config=_small_config())

        control = report["overfitting_control"]
        assert control["evaluated"] > 0
        assert control["sampled"] > 0
        assert control["effective_trials"] >= 1
        assert control["evaluated"] == report["ga_evolution"]["evaluations"]

        curve = control["expected_max_sharpe_curve"]
        assert len(curve["curve"]) >= 2
        assert curve["n_trials"] == control["evaluated"]

    @pytest.mark.unit
    def test_finalists_are_gated_against_real_search_trials(self):
        report = generate_strategies(_mean_reverting_df(), interval="1d", config=_small_config())
        finalists = report["ranking"] or report["finalists"]
        assert finalists, "se necesita al menos una finalista para la comprobación"

        block = finalists[0]["gating"]["metrics"]["overfitting"]
        assert block["source"] == "search_trials"
        # El N que deflacta es el de la búsqueda, no el puñado de vecinos jitter.
        assert block["deflated_sharpe"]["n_trials"] >= report["overfitting_control"]["sampled"]
