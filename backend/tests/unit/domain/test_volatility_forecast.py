"""
test_volatility_forecast.py — El aparato con el que se decide a qué pregunta
alcanza la muestra.

Este módulo existe para responder si la volatilidad es predecible en unos datos
concretos. La tentación evidente es comprobar que dice «sí» sobre una serie
GARCH y darse por satisfecho. No basta: **un instrumento mal calibrado también
dice que sí**, y aquí decir que sí es lo que autoriza a construir encima.

Por eso los tests se reparten en tres frentes:

  1. **Causalidad** — que ninguna función mire hacia delante. Una volatilidad
     realizada que incluya la vela siguiente daría predicciones magníficas y
     falsas.
  2. **La línea base correcta** — que `oos_r2` compare contra lo que se le pasa
     y no contra la media de la muestra. Sobre una serie tan persistente como la
     volatilidad, el R² clásico es alto incluso para un predictor inútil.
  3. **Potencia** — que la tabla de tamaños muestrales reproduzca los números
     con los que se justifica el reencuadre entero. Si esa tabla estuviera mal,
     la decisión de perseguir volatilidad en vez de dirección no tendría base.
"""

import numpy as np
import pytest

from core.domain.services.volatility_forecast import (
    HAR_LAGS, HARModel, accuracy_edge_to_r, diebold_mariano, future_volatility,
    har_features, observations_needed, oos_r2, realized_volatility,
)


def _garch(n=2000, seed=1, omega=1e-6, alpha=0.09, beta=0.90):
    """Serie CON agrupamiento de volatilidad: el caso en que la respuesta es sí."""
    rng = np.random.default_rng(seed)
    var = np.full(n, omega / (1 - alpha - beta))
    r = np.zeros(n)
    for i in range(1, n):
        var[i] = omega + alpha * r[i - 1] ** 2 + beta * var[i - 1]
        r[i] = rng.normal(0, np.sqrt(var[i]))
    return r


def _homoscedastic(n=2000, seed=2, sigma=0.012):
    """Serie SIN agrupamiento: volatilidad constante, impredecible por definición."""
    return np.random.default_rng(seed).normal(0, sigma, n)


class TestRealizedVolatilityIsCausal:
    """
    Es la variable de la que cuelga todo lo demás. Si mira una sola vela hacia
    delante, todos los resultados posteriores son ficción.
    """

    @pytest.mark.unit
    def test_position_i_only_uses_up_to_i(self):
        """Cambiar el futuro no puede cambiar el pasado."""
        r = _homoscedastic(300, seed=4)
        original = realized_volatility(r, 24)
        alterado = r.copy()
        alterado[200:] *= 50.0
        movido = realized_volatility(alterado, 24)
        np.testing.assert_allclose(original[:200], movido[:200], rtol=1e-12)

    @pytest.mark.unit
    def test_the_first_window_is_nan_not_a_partial_window(self):
        """Rellenarlas con menos datos daría valores sistemáticamente bajos al
        principio, y el modelo aprendería «al principio hay poca volatilidad»:
        una fecha disfrazada de señal."""
        out = realized_volatility(_homoscedastic(100, seed=5), 24)
        assert np.isnan(out[:23]).all()
        assert np.isfinite(out[23:]).all()

    @pytest.mark.unit
    def test_it_is_the_root_of_the_sum_of_squares(self):
        r = np.array([0.01, -0.02, 0.03, 0.0, 0.01])
        out = realized_volatility(r, 3)
        assert out[2] == pytest.approx(np.sqrt(0.01**2 + 0.02**2 + 0.03**2))

    @pytest.mark.unit
    def test_a_series_shorter_than_the_window_returns_all_nan(self):
        assert np.isnan(realized_volatility(np.zeros(10), 24)).all()


class TestFutureVolatilityIsTheLabel:
    """
    La variable objetivo. Su horizonte es exactamente lo que hay que purgar: no
    son dos parámetros que haya que mantener sincronizados, es uno solo.
    """

    @pytest.mark.unit
    def test_position_i_covers_the_next_h_bars_and_not_i_itself(self):
        r = np.array([9.0, 0.01, -0.02, 0.03, 0.5])
        out = future_volatility(r, 3)
        # i=0 debe cubrir r[1..3] y NO r[0], que es enorme a propósito.
        assert out[0] == pytest.approx(np.sqrt(0.01**2 + 0.02**2 + 0.03**2))

    @pytest.mark.unit
    def test_the_last_h_positions_are_nan_because_their_future_has_not_happened(self):
        out = future_volatility(_homoscedastic(200, seed=6), 24)
        assert np.isnan(out[-24:]).all()
        assert np.isfinite(out[:-24]).all()

    @pytest.mark.unit
    def test_the_label_never_overlaps_the_bar_it_labels(self):
        """Si la etiqueta incluyera la vela `i`, el modelo vería parte de su
        propia respuesta entre las features."""
        r = np.zeros(50)
        r[10] = 1.0
        out = future_volatility(r, 5)
        assert out[10] == pytest.approx(0.0)      # su propio retorno no cuenta
        assert out[9] == pytest.approx(1.0)       # el de la vela siguiente sí


class TestHarFeatures:

    @pytest.mark.unit
    def test_the_lags_are_the_ones_corsi_uses(self):
        """Diario, semanal, mensual: los tres horizontes de operador del modelo
        original. Cambiarlos sin motivo convertiría una referencia de la
        literatura en un modelo propio sin validar."""
        assert HAR_LAGS == (1, 5, 22)

    @pytest.mark.unit
    def test_the_first_column_is_the_series_itself(self):
        rv = np.array([1.0, 2.0, 3.0, 4.0])
        assert har_features(rv, (1,))[:, 0] == pytest.approx(rv)

    @pytest.mark.unit
    def test_each_column_is_a_backward_mean(self):
        rv = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        col = har_features(rv, (3,))[:, 0]
        assert col[2] == pytest.approx(2.0)     # (1+2+3)/3
        assert col[4] == pytest.approx(4.0)     # (3+4+5)/3
        assert np.isnan(col[:2]).all()

    @pytest.mark.unit
    def test_it_does_not_look_forward(self):
        rv = _homoscedastic(300, seed=7) ** 2
        antes = har_features(rv)
        despues = rv.copy()
        despues[150:] += 99.0
        np.testing.assert_allclose(antes[:150], har_features(despues)[:150],
                                   rtol=1e-12, equal_nan=True)


class TestHarModel:

    @pytest.mark.unit
    def test_it_recovers_a_linear_relation_it_was_given(self):
        rng = np.random.default_rng(8)
        X = rng.normal(size=(400, 3))
        y = 0.5 + 2.0 * X[:, 0] - 1.0 * X[:, 1] + 0.25 * X[:, 2]
        coef = HARModel().fit(X, y).coef_
        assert coef == pytest.approx([0.5, 2.0, -1.0, 0.25], abs=1e-8)

    @pytest.mark.unit
    def test_predicting_before_fitting_fails_loudly(self):
        """Devolver ceros en silencio daría un R² plausible y sin sentido."""
        with pytest.raises(ValueError):
            HARModel().predict(np.zeros((5, 3)))


class TestOosR2IsMeasuredAgainstTheBaselineGiven:
    """
    El punto entero del módulo. Un R² de 0,45 sobre volatilidad no significa
    nada hasta que se dice contra qué.
    """

    @pytest.mark.unit
    def test_beating_the_baseline_gives_a_positive_number(self):
        actual = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert oos_r2(actual, actual + 0.1, actual + 1.0) > 0

    @pytest.mark.unit
    def test_being_worse_than_the_baseline_gives_a_negative_number(self):
        actual = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert oos_r2(actual, actual + 1.0, actual + 0.1) < 0

    @pytest.mark.unit
    def test_a_perfect_prediction_gives_one(self):
        actual = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        assert oos_r2(actual, actual, actual + 1.0) == pytest.approx(1.0)

    @pytest.mark.unit
    def test_the_same_predictor_scores_differently_against_different_baselines(self):
        """La demostración de que el número no es una propiedad del modelo sino
        de la comparación — y de por qué reportarlo sin la base es engañoso."""
        rng = np.random.default_rng(11)
        actual = np.abs(rng.normal(1.0, 0.2, 500))
        pred = actual + rng.normal(0, 0.1, 500)
        contra_mala = oos_r2(actual, pred, np.zeros(500))
        contra_buena = oos_r2(actual, pred, actual + rng.normal(0, 0.1, 500))
        assert contra_mala > 0.9
        assert contra_buena < 0.3

    @pytest.mark.unit
    def test_too_few_finite_points_returns_nan_instead_of_a_number(self):
        assert np.isnan(oos_r2([1.0, np.nan], [1.0, 1.0], [2.0, 2.0]))


class TestDieboldMariano:
    """
    El contraste emparejado. Compara los dos predictores SOBRE LAS MISMAS
    observaciones, en vez de mirar dos agregados por separado — el mismo motivo
    por el que la comparación de conjuntos de features usa McNemar.
    """

    @pytest.mark.unit
    def test_a_clearly_better_predictor_is_declared_better(self):
        rng = np.random.default_rng(12)
        malo = rng.normal(0, 1.0, 500)
        bueno = rng.normal(0, 0.3, 500)
        out = diebold_mariano(malo, bueno, horizon=1)
        assert out["better"] and out["p_value"] < 0.01

    @pytest.mark.unit
    def test_two_equivalent_predictors_are_not_declared_different(self):
        rng = np.random.default_rng(13)
        a = rng.normal(0, 1.0, 800)
        b = rng.normal(0, 1.0, 800)
        assert not diebold_mariano(a, b, horizon=1)["better"]

    @pytest.mark.unit
    def test_it_is_one_sided_so_a_worse_predictor_is_never_better(self):
        rng = np.random.default_rng(14)
        bueno = rng.normal(0, 0.3, 500)
        malo = rng.normal(0, 1.0, 500)
        out = diebold_mariano(bueno, malo, horizon=1)   # argumentos al revés
        assert not out["better"] and out["p_value"] > 0.9

    @pytest.mark.unit
    def test_the_overlap_correction_makes_the_test_more_conservative(self):
        """Con horizonte h las predicciones comparten h−1 velas de futuro y sus
        errores están autocorrelacionados por construcción. Ignorarlo subestima
        la varianza y fabrica significancia: es la falta de purga cometida en el
        otro extremo del cálculo."""
        rng = np.random.default_rng(15)
        base = rng.normal(0, 1.0, 1000)
        # Errores suavizados: autocorrelación positiva, como la que induce el
        # solapamiento de un horizonte largo.
        suave_a = np.convolve(base, np.ones(24) / 24, mode="same")
        suave_b = np.convolve(rng.normal(0, 0.95, 1000), np.ones(24) / 24, mode="same")
        sin_correccion = diebold_mariano(suave_a, suave_b, horizon=1)
        con_correccion = diebold_mariano(suave_a, suave_b, horizon=24)
        assert abs(con_correccion["statistic"]) < abs(sin_correccion["statistic"])

    @pytest.mark.unit
    def test_too_few_observations_says_so_instead_of_guessing(self):
        out = diebold_mariano(np.zeros(5), np.ones(5), horizon=1)
        assert out["statistic"] is None and not out["better"]


class TestThePowerTable:
    """
    Los números que justifican el reencuadre. Si esta tabla estuviera mal, la
    decisión de perseguir volatilidad en vez de dirección no tendría base.
    """

    @pytest.mark.unit
    def test_a_directional_edge_of_two_points_needs_thousands_of_observations(self):
        n = observations_needed(accuracy_edge_to_r(0.02))
        assert 3_500 <= n <= 4_500

    @pytest.mark.unit
    def test_the_one_sided_number_is_smaller_than_the_published_two_sided_one(self):
        """La divulgación cita 4.905 observaciones para un edge del 2 %; aquí
        salen 3.863. No es optimismo: los dos contrastes que este motor ejecuta
        —Wilson contra la base y Diebold-Mariano— son de una cola, y dimensionar
        con dos gastaría la mitad del alfa en detectar que el modelo es PEOR que
        la base, que es información que no se usa.

        La relación entre ambos es exactamente `((1,96+z_β)/(1,645+z_β))²`."""
        from scipy.stats import norm
        una_cola = observations_needed(accuracy_edge_to_r(0.02))
        z_beta = float(norm.ppf(0.80))
        ratio = ((1.959964 + z_beta) / (1.644854 + z_beta)) ** 2
        assert una_cola * ratio == pytest.approx(4_905, rel=0.02)

    @pytest.mark.unit
    def test_a_directional_edge_of_one_point_needs_four_times_more(self):
        """La potencia escala con el cuadrado del efecto: bajar el edge a la
        mitad multiplica por cuatro la muestra necesaria."""
        uno = observations_needed(accuracy_edge_to_r(0.01))
        dos = observations_needed(accuracy_edge_to_r(0.02))
        assert uno / dos == pytest.approx(4.0, rel=0.05)

    @pytest.mark.unit
    def test_a_volatility_correlation_of_045_needs_dozens(self):
        """El número que cambia la conversación: la misma muestra que no alcanza
        para la dirección sobra para la volatilidad."""
        assert observations_needed(0.45) < 40

    @pytest.mark.unit
    def test_a_volatility_correlation_of_030_still_needs_under_a_hundred(self):
        assert observations_needed(0.30) < 100

    @pytest.mark.unit
    def test_the_two_questions_differ_by_two_orders_of_magnitude(self):
        """La afirmación central del reencuadre, comprobada en vez de citada."""
        direccion = observations_needed(accuracy_edge_to_r(0.02))
        volatilidad = observations_needed(0.45)
        assert direccion / volatilidad > 100

    @pytest.mark.unit
    def test_a_zero_or_impossible_effect_has_no_answer(self):
        assert observations_needed(0.0) is None
        assert observations_needed(1.5) is None

    @pytest.mark.unit
    def test_more_power_demands_more_sample(self):
        assert observations_needed(0.30, power=0.95) > observations_needed(0.30, power=0.80)

    @pytest.mark.unit
    def test_the_edge_conversion_puts_both_questions_on_one_scale(self):
        """Un 2 % de precisión sobre clases equilibradas es un phi de 0,04. Sin
        esta conversión las dos preguntas no se pueden comparar."""
        assert accuracy_edge_to_r(0.02) == pytest.approx(0.04)


class TestOnSeriesWithKnownProperties:
    """
    La calibración de verdad: series construidas con la respuesta conocida de
    antemano, no datos reales donde no hay contra qué contrastar.
    """

    @pytest.mark.unit
    def test_har_beats_persistence_on_a_garch_series(self):
        r = _garch(2000, seed=1)
        rv = realized_volatility(r, 24)
        y = future_volatility(r, 24)
        X = har_features(rv)
        ok = np.isfinite(y) & np.isfinite(rv) & np.isfinite(X).all(axis=1)
        X, y, persist = X[ok], y[ok], rv[ok]
        corte = int(len(y) * 0.6)
        pred = HARModel().fit(X[:corte], y[:corte]).predict(X[corte:])
        assert oos_r2(y[corte:], pred, persist[corte:]) > 0

    @pytest.mark.unit
    def test_har_also_beats_persistence_on_a_constant_volatility_series(self):
        """El resultado incómodo, dejado por escrito a propósito: sobre una serie
        homocedástica —volatilidad constante, impredecible POR CONSTRUCCIÓN— HAR
        bate a la persistencia con holgura.

        No es un fallo del modelo ni del test. La persistencia es un estimador
        RUIDOSO de una constante, y cualquier promedio la mejora encogiendo hacia
        la media, sin usar información temporal. Por eso `edge_test` no acepta
        «bate a la persistencia» como prueba de predictibilidad."""
        r = _homoscedastic(2000, seed=2)
        rv = realized_volatility(r, 24)
        y = future_volatility(r, 24)
        X = har_features(rv)
        ok = np.isfinite(y) & np.isfinite(rv) & np.isfinite(X).all(axis=1)
        X, y, persist = X[ok], y[ok], rv[ok]
        corte = int(len(y) * 0.6)
        pred = HARModel().fit(X[:corte], y[:corte]).predict(X[corte:])
        assert oos_r2(y[corte:], pred, persist[corte:]) > 0.2

    @pytest.mark.unit
    def test_but_it_does_not_beat_the_constant_mean_there(self):
        """La base que sí distingue las dos situaciones."""
        r = _homoscedastic(2000, seed=2)
        rv = realized_volatility(r, 24)
        y = future_volatility(r, 24)
        X = har_features(rv)
        ok = np.isfinite(y) & np.isfinite(rv) & np.isfinite(X).all(axis=1)
        X, y = X[ok], y[ok]
        corte = int(len(y) * 0.6)
        pred = HARModel().fit(X[:corte], y[:corte]).predict(X[corte:])
        constante = np.full(len(y) - corte, float(y[:corte].mean()))
        assert oos_r2(y[corte:], pred, constante) < 0.05

    @pytest.mark.unit
    def test_predictions_correlate_with_reality_only_when_there_is_clustering(self):
        """La tercera condición, y la más directa: un predictor que acierta el
        nivel medio pero no el momento no sirve para nada de lo que se quiere
        construir encima."""
        def _corr(r):
            rv = realized_volatility(r, 24)
            y = future_volatility(r, 24)
            X = har_features(rv)
            ok = np.isfinite(y) & np.isfinite(rv) & np.isfinite(X).all(axis=1)
            X, y = X[ok], y[ok]
            corte = int(len(y) * 0.6)
            pred = HARModel().fit(X[:corte], y[:corte]).predict(X[corte:])
            return float(np.corrcoef(y[corte:], pred)[0, 1])

        assert _corr(_garch(2000, seed=1)) > 0.4
        assert abs(_corr(_homoscedastic(2000, seed=2))) < 0.15
