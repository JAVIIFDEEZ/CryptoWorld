"""
test_multiple_testing_control.py — Control de multiplicidad (G1).

El *False Strategy Theorem* dice que el máximo Sharpe entre N pruebas crece con
N aunque ninguna estrategia tenga edge. Reportar un Sharpe sin decir cuántas
configuraciones se probaron es, por tanto, científicamente vacío.

Estos tests fijan las tres piezas que corrigen eso:
  · `expected_max_sharpe` — el umbral que produce el azar con N intentos;
  · `deflated_sharpe_ratio` con `n_trials` explícito — deflación por el nº REAL
    de pruebas, aunque solo se conserve una muestra de las series;
  · `effective_number_of_trials` — N independiente, agrupando los genomas casi
    idénticos que un GA produce en masa.

Y, sobre todo, el test que da sentido a todo el cambio: alimentar el DSR con
vecinos jitter (lo que hacía el motor) lo deja ≈1 para cualquier estrategia,
mientras que alimentarlo con pruebas reales y diversas sí discrimina.
"""

import numpy as np
import pytest

from core.domain.services import backtest_robustness as rb


def _returns(mean: float, sd: float, n: int, seed: int) -> list:
    return list(np.random.default_rng(seed).normal(mean, sd, n))


class TestExpectedMaxSharpe:
    """E[max SR₀]: el Sharpe que da el azar con N intentos."""

    @pytest.mark.unit
    def test_grows_with_number_of_trials(self):
        """Más pruebas → mejor máximo esperado sin edge alguno. Es el teorema."""
        low = rb.expected_max_sharpe(variance=0.01, n_trials=10)
        mid = rb.expected_max_sharpe(variance=0.01, n_trials=1_000)
        high = rb.expected_max_sharpe(variance=0.01, n_trials=100_000)
        assert 0 < low < mid < high

    @pytest.mark.unit
    def test_grows_with_dispersion_between_trials(self):
        """A igual N, pruebas más dispares producen máximos más altos por azar."""
        assert (rb.expected_max_sharpe(0.04, 500)
                > rb.expected_max_sharpe(0.01, 500))

    @pytest.mark.unit
    @pytest.mark.parametrize("variance,n", [(0.0, 500), (0.01, 1), (0.01, 0)])
    def test_degenerate_inputs_give_zero_threshold(self, variance, n):
        """Sin varianza o sin pruebas múltiples no hay nada que deflactar."""
        assert rb.expected_max_sharpe(variance, n) == 0.0


class TestDeflationByRealTrialCount:

    @pytest.mark.unit
    def test_declared_n_raises_the_threshold(self):
        """El mismo Sharpe, con las mismas series de muestra, se deflacta más si
        se declara que las pruebas fueron miles y no solo las muestreadas."""
        returns = _returns(0.004, 0.01, 500, seed=1)
        trials = [_returns(0.0, 0.01, 500, seed=s) for s in range(30)]

        sampled_only = rb.deflated_sharpe_ratio(returns, trials)
        declared = rb.deflated_sharpe_ratio(returns, trials, n_trials=5_000)

        assert declared["sr0_threshold"] > sampled_only["sr0_threshold"]
        assert declared["dsr"] <= sampled_only["dsr"]
        assert declared["n_trials"] == 5_000
        assert declared["n_trials_sampled"] == 30

    @pytest.mark.unit
    def test_declared_n_never_below_sample_size(self):
        """Declarar menos pruebas que series muestreadas es incoherente: se
        conserva el tamaño de la muestra en lugar de deflactar de menos."""
        trials = [_returns(0.0, 0.01, 200, seed=s) for s in range(20)]
        out = rb.deflated_sharpe_ratio(_returns(0.003, 0.01, 200, 99), trials, n_trials=5)
        assert out["n_trials"] == 20

    @pytest.mark.unit
    def test_omitting_n_preserves_previous_behaviour(self):
        """Compatibilidad: sin `n_trials` el N sigue siendo el nº de series."""
        trials = [_returns(0.0, 0.01, 200, seed=s) for s in range(12)]
        out = rb.deflated_sharpe_ratio(_returns(0.003, 0.01, 200, 7), trials)
        assert out["n_trials"] == 12

    @pytest.mark.unit
    def test_strong_edge_survives_heavy_deflation(self):
        """Deflactar no es castigar a todo el mundo: un edge grande aguanta."""
        strong = _returns(0.02, 0.01, 600, seed=3)          # Sharpe por periodo ~2
        trials = [_returns(0.0, 0.01, 600, seed=s) for s in range(40)]
        assert rb.deflated_sharpe_ratio(strong, trials, n_trials=10_000)["dsr"] > 0.9


class TestJitterVersusRealTrials:
    """El núcleo del hallazgo: con qué se alimenta el DSR decide si mide algo."""

    @pytest.mark.unit
    def test_near_identical_trials_make_dsr_meaningless(self):
        """Vecinos jitter son casi clones: su varianza de Sharpe tiende a 0, el
        umbral se desploma y el DSR sale ≈1 incluso para un Sharpe mediocre.
        Esto es exactamente lo que hacía el motor antes de la corrección."""
        mediocre = _returns(0.0015, 0.01, 400, seed=11)
        base = np.array(_returns(0.0015, 0.01, 400, seed=11))
        clones = [list(base + np.random.default_rng(s).normal(0, 1e-6, 400))
                  for s in range(12)]

        out = rb.deflated_sharpe_ratio(mediocre, clones, n_trials=12)
        assert out["sr0_threshold"] < 0.01
        assert out["dsr"] > 0.95           # aprueba a un Sharpe que no lo merece

    @pytest.mark.unit
    def test_diverse_real_trials_discriminate(self):
        """Con pruebas realmente distintas, el mismo Sharpe mediocre ya no pasa."""
        mediocre = _returns(0.0015, 0.01, 400, seed=11)
        diverse = [_returns(rng_mean, 0.01, 400, seed=100 + i)
                   for i, rng_mean in enumerate(np.linspace(-0.003, 0.003, 30))]

        out = rb.deflated_sharpe_ratio(mediocre, diverse, n_trials=3_000)
        assert out["sr0_threshold"] > 0.01
        assert out["dsr"] < 0.9


class TestEffectiveTrials:

    @pytest.mark.unit
    def test_clones_collapse_into_one_effective_trial(self):
        """Un GA que explora un vecindario estrecho no ha hecho N pruebas
        independientes; contarlas como tales deflactaría de más."""
        base = np.array(_returns(0.002, 0.01, 300, seed=5))
        clones = [list(base + np.random.default_rng(s).normal(0, 1e-8, 300))
                  for s in range(10)]

        out = rb.effective_number_of_trials(clones)
        assert out["n_trials"] == 10
        assert out["effective_trials"] == 1
        assert out["clustered"] is True

    @pytest.mark.unit
    def test_independent_trials_stay_independent(self):
        independent = [_returns(0.0, 0.01, 300, seed=s) for s in range(8)]
        out = rb.effective_number_of_trials(independent)
        assert out["effective_trials"] == 8
        assert out["clustered"] is False

    @pytest.mark.unit
    def test_handles_empty_and_single(self):
        assert rb.effective_number_of_trials([])["effective_trials"] == 0
        assert rb.effective_number_of_trials([[0.1, 0.2]])["effective_trials"] == 1

    @pytest.mark.unit
    def test_constant_series_do_not_crash(self):
        """Una estrategia que no opera da retornos constantes: no correlaciona
        con nada y debe contarse como su propio grupo, no romper el cálculo."""
        out = rb.effective_number_of_trials([[0.0] * 50, _returns(0.001, 0.01, 50, 2)])
        assert out["effective_trials"] == 2


class TestExpectedMaxSharpeCurve:
    """La curva que sitúa a la campeona frente a lo que da el azar."""

    @pytest.mark.unit
    def test_curve_is_monotonic_and_bounded_by_n(self):
        out = rb.expected_max_sharpe_curve(variance=0.01, n_trials=2_000)
        values = [p["expected_max_sharpe"] for p in out["curve"]]
        assert values == sorted(values)
        assert out["curve"][-1]["trials"] <= 2_000

    @pytest.mark.unit
    def test_reports_when_chance_matches_the_observed_sharpe(self):
        """Un Sharpe modesto se alcanza por azar con suficientes intentos, y la
        curva dice a partir de cuántos."""
        out = rb.expected_max_sharpe_curve(variance=0.04, n_trials=100_000,
                                           observed_sharpe=0.3)
        assert out["trials_to_match_by_chance"] is not None

    @pytest.mark.unit
    def test_strong_sharpe_is_never_matched_by_chance(self):
        out = rb.expected_max_sharpe_curve(variance=0.01, n_trials=5_000,
                                           observed_sharpe=5.0)
        assert out["trials_to_match_by_chance"] is None

    @pytest.mark.unit
    def test_zero_variance_gives_flat_zero_curve(self):
        out = rb.expected_max_sharpe_curve(variance=0.0, n_trials=1_000)
        assert all(p["expected_max_sharpe"] == 0.0 for p in out["curve"])
