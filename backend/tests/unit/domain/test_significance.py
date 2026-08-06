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


class TestProportionSignificance:
    """
    «Edge del 4 % sobre el azar» es una magnitud sin escala.

    Con 500 muestras el error estándar de una proporción cerca de 0,5 ronda el
    2,2 %: cuatro puntos son 1,8 desviaciones típicas, que no alcanza la
    significancia ni en un contraste de una cola. Con 5000 muestras el mismo
    4 % sí es señal. El número es idéntico y significa cosas opuestas — por eso
    el veredicto no puede compararlo contra un umbral fijo.
    """

    @pytest.mark.unit
    def test_the_same_edge_means_opposite_things_at_different_sample_sizes(self):
        small = sig.edge_significance(int(0.54 * 500), 500, 0.50)
        large = sig.edge_significance(int(0.54 * 5000), 5000, 0.50)
        assert small["edge"] == large["edge"] == pytest.approx(0.04, abs=1e-3)
        assert not small["significant"]
        assert large["significant"]

    @pytest.mark.unit
    def test_a_four_point_edge_on_five_hundred_samples_is_not_significant(self):
        """El umbral que había. Sobre 500 muestras declaraba EDGE algo cuyo
        intervalo cruza el cero."""
        out = sig.edge_significance(int(0.54 * 500), 500, 0.50)
        assert out["edge"] >= 0.04
        assert out["edge_low"] < 0

    @pytest.mark.unit
    def test_the_interval_brackets_the_point_estimate(self):
        out = sig.edge_significance(280, 500, 0.50)
        assert out["edge_low"] < out["edge"] < out["edge_high"]

    @pytest.mark.unit
    def test_wilson_stays_inside_zero_one_at_the_extremes(self):
        """Es la razón de usar Wilson y no el intervalo de Wald de los manuales:
        con proporciones extremas, Wald produce extremos fuera de [0, 1]."""
        for successes, n in ((0, 30), (30, 30), (1, 200)):
            out = sig.wilson_interval(successes, n)
            assert 0.0 <= out["low"] <= out["high"] <= 1.0

    @pytest.mark.unit
    def test_more_samples_narrow_the_interval(self):
        narrow = sig.wilson_interval(1000, 2000)
        wide = sig.wilson_interval(50, 100)
        assert (narrow["high"] - narrow["low"]) < (wide["high"] - wide["low"])

    @pytest.mark.unit
    def test_no_samples_gives_no_interval_instead_of_a_fake_one(self):
        """Devolver [0, 1] fingiría una medición. `None` dice que no la hay."""
        out = sig.wilson_interval(0, 0)
        assert out["point"] is None and out["low"] is None

    @pytest.mark.unit
    def test_an_edge_below_the_baseline_is_never_significant(self):
        out = sig.edge_significance(int(0.45 * 1000), 1000, 0.50)
        assert out["edge"] < 0 and not out["significant"]


class TestMultipleTestingCorrection:
    """
    Un usuario consulta veinte activos y se queda con los que dicen que hay
    señal. Con edge verdadero cero y veinte pruebas al 5 %, se espera ver varios
    positivos por azar: sin corrección, el producto **fabrica falsos positivos
    como funcionalidad**.
    """

    @pytest.mark.unit
    def test_a_lone_strong_result_survives(self):
        out = sig.benjamini_hochberg([0.001])
        assert out["n_significant"] == 1

    @pytest.mark.unit
    def test_the_same_p_value_can_die_in_a_large_family(self):
        """Es el efecto que se busca: el mismo p-valor significa menos cuando es
        el mejor de muchas pruebas."""
        alone = sig.benjamini_hochberg([0.04])
        crowd = sig.benjamini_hochberg([0.04] + [0.5] * 40)
        assert alone["n_significant"] == 1
        assert crowd["n_significant"] == 0

    @pytest.mark.unit
    def test_it_is_less_brutal_than_bonferroni(self):
        """Con veinte activos, Bonferroni exigiría 0,25 % por prueba y no
        sobreviviría ninguna señal real moderada. BH acota la proporción de
        falsos entre los positivos anunciados, que es la pregunta correcta."""
        p_values = [0.001, 0.002, 0.003] + [0.6] * 17
        out = sig.benjamini_hochberg(p_values, fdr=0.10)
        bonferroni = sum(1 for p in p_values if p <= 0.05 / len(p_values))
        assert out["n_significant"] >= bonferroni

    @pytest.mark.unit
    def test_results_come_back_in_the_order_they_went_in(self):
        """Se ordenan para decidir el corte, pero devolverlos ordenados
        rompería la correspondencia con los activos consultados."""
        p_values = [0.9, 0.001, 0.5]
        out = sig.benjamini_hochberg(p_values)
        assert [r["p_value"] for r in out["results"]] == p_values
        assert out["results"][1]["significant"]

    @pytest.mark.unit
    def test_an_empty_family_is_not_an_error(self):
        assert sig.benjamini_hochberg([])["n_significant"] == 0
