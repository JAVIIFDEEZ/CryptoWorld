"""
test_significance.py — Intervalos de confianza y PSR (G9d).

«Sharpe 1.8» no es una afirmación completa. Un Sharpe de 1.8 sobre 60 velas y
otro sobre 3 000 son cosas distintas: el primero es compatible con que el Sharpe
verdadero sea 0, el segundo no. Reportar solo la magnitud invita a leer como
sólido lo que es ruido.

Los tests que más importan aquí son los que fijan que la incertidumbre responde
a lo que debe: al tamaño de la muestra y a la forma de la distribución.
"""

import numpy as np
import pytest

from core.domain.services import significance as sig


def _returns(mean=0.003, sd=0.01, n=500, seed=0):
    return np.random.default_rng(seed).normal(mean, sd, n)


class TestStandardError:

    @pytest.mark.unit
    def test_shrinks_with_more_observations(self):
        """Más histórico, menos incertidumbre. Es la razón por la que el tamaño
        de la muestra tiene que acompañar a la métrica."""
        short = sig.sharpe_standard_error(_returns(n=60, seed=1))
        long = sig.sharpe_standard_error(_returns(n=2000, seed=1))
        assert short > long > 0

    @pytest.mark.unit
    def test_negative_skew_widens_the_error(self):
        """Asimetría negativa —ganancias pequeñas y pérdidas grandes, el perfil
        de vender volatilidad— hace el Sharpe MENOS fiable de lo que su magnitud
        sugiere. Asumir normalidad lo esconde justo donde más importa."""
        rng = np.random.default_rng(4)
        symmetric = rng.normal(0.002, 0.01, 800)
        # Mismo Sharpe aproximado, pero con cola izquierda pesada.
        skewed = symmetric.copy()
        skewed[::40] -= 0.09
        skewed += (symmetric.mean() - skewed.mean())

        assert sig.sharpe_standard_error(skewed) > sig.sharpe_standard_error(symmetric)

    @pytest.mark.unit
    @pytest.mark.parametrize("series", [np.array([0.01, 0.02]), np.zeros(100)])
    def test_degenerate_series_report_none(self, series):
        """Sobre algo que no varía no hay incertidumbre que estimar, y un cero
        sugeriría certeza."""
        assert sig.sharpe_standard_error(series) is None


class TestConfidenceInterval:

    @pytest.mark.unit
    def test_interval_brackets_the_estimate(self):
        out = sig.sharpe_confidence_interval(_returns())
        assert out["ci_lower"] < out["sharpe"] < out["ci_upper"]

    @pytest.mark.unit
    def test_a_short_series_cannot_rule_out_zero(self):
        """El caso que da sentido a todo el módulo: un Sharpe alto medido sobre
        pocas velas no permite descartar que no haya edge."""
        out = sig.sharpe_confidence_interval(_returns(mean=0.004, n=25, seed=7))
        assert out["excludes_zero"] is False
        assert "incluye el cero" in out["note"]

    @pytest.mark.unit
    def test_a_long_series_with_a_real_edge_excludes_zero(self):
        out = sig.sharpe_confidence_interval(_returns(mean=0.006, sd=0.01, n=1500, seed=2))
        assert out["excludes_zero"] is True
        assert out["ci_lower"] > 0

    @pytest.mark.unit
    def test_higher_confidence_gives_a_wider_interval(self):
        r = _returns()
        narrow = sig.sharpe_confidence_interval(r, confidence=0.80)
        wide = sig.sharpe_confidence_interval(r, confidence=0.99)
        assert wide["ci_upper"] - wide["ci_lower"] > narrow["ci_upper"] - narrow["ci_lower"]

    @pytest.mark.unit
    def test_reports_instead_of_crashing_on_a_flat_series(self):
        assert sig.sharpe_confidence_interval(np.zeros(50))["sharpe"] is None


class TestProbabilisticSharpe:

    @pytest.mark.unit
    def test_strong_long_track_record_is_confident(self):
        out = sig.probabilistic_sharpe_ratio(_returns(mean=0.006, n=1500, seed=3))
        assert out["psr"] > 0.95

    @pytest.mark.unit
    def test_weak_evidence_is_not(self):
        out = sig.probabilistic_sharpe_ratio(_returns(mean=0.001, n=40, seed=5))
        assert out["psr"] < 0.95
        assert "no basta" in out["note"]

    @pytest.mark.unit
    def test_a_harder_benchmark_lowers_the_probability(self):
        """PSR contra 0 responde «¿hay edge?»; contra un umbral mayor,
        «¿supera a lo que ya tengo?»."""
        r = _returns(mean=0.004, n=800, seed=6)
        easy = sig.probabilistic_sharpe_ratio(r, benchmark_sharpe=0.0)
        hard = sig.probabilistic_sharpe_ratio(r, benchmark_sharpe=8.0)
        assert hard["psr"] < easy["psr"]

    @pytest.mark.unit
    def test_says_how_much_history_would_be_needed(self):
        """Convierte «¿es fiable?» en «¿cuánto falta?», que es accionable."""
        out = sig.probabilistic_sharpe_ratio(_returns(mean=0.002, sd=0.01, n=60, seed=8))
        assert out["min_track_record_length"] is not None
        assert out["min_track_record_length"] > 0

    @pytest.mark.unit
    def test_no_excess_over_the_benchmark_means_no_track_record_helps(self):
        out = sig.probabilistic_sharpe_ratio(_returns(mean=0.0, n=500), benchmark_sharpe=5.0)
        assert out["min_track_record_length"] is None


class TestAnnotate:

    @pytest.mark.unit
    def test_bundles_interval_and_psr(self):
        out = sig.annotate(_returns(mean=0.006, n=1500, seed=9))
        assert out["significant"] is True
        assert "confidence_interval" in out and "probabilistic_sharpe" in out

    @pytest.mark.unit
    def test_marks_weak_evidence_as_not_significant(self):
        out = sig.annotate(_returns(mean=0.002, n=30, seed=10))
        assert out["significant"] is False
        assert "podría ser ruido" in out["note"]
