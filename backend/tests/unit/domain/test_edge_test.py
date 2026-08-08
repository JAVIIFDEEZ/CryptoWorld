"""
test_edge_test.py — Calibrar el árbitro antes de dejarle decidir qué se
construye.

`edge_test` no produce una estrategia: produce una DECISIÓN sobre a qué pregunta
dedicar el trabajo. Eso lo hace más peligroso que un backtest optimista, no
menos — un backtest malo se descubre operando, y un árbitro mal calibrado
redirige meses de esfuerzo antes de que nadie note nada.

Por eso los tests se ejecutan sobre series con la respuesta CONOCIDA de
antemano, no sobre datos reales:

  · **GARCH** — agrupamiento de volatilidad por construcción, sin edge
    direccional. La respuesta correcta es VOLATILITY.
  · **Homocedástica** — volatilidad constante, impredecible por definición. La
    respuesta correcta es NEITHER.

Los dos casos juntos son los que justifican este fichero, porque el criterio de
partida —«batir a la persistencia», que es el que propone el documento— falló en
LAS DOS direcciones, y eso solo se ve corriendo ambos:

  · sobre la homocedástica daba VOLATILITY, con R² relativo +0,45 y p < 0,001
    sobre una serie donde no hay absolutamente nada que predecir;
  · sobre las GARCH daba NEITHER en 7 de 9 combinaciones de tamaño y semilla,
    con correlaciones de 0,6–0,7 entre lo predicho y lo ocurrido.

Con un solo caso se habría corregido la mitad del problema. Y el falso negativo
es el más caro de los dos: habría archivado como «sin señal» justo la línea de
trabajo que el documento pide abrir.

El criterio corregido —hipótesis nula = media constante del entrenamiento, dos
candidatos con el alfa repartido— se barrió sobre 4 tamaños × 5 semillas para
cada familia de series antes de darlo por bueno: **20/20 y 20/20**. Los tests de
abajo fijan una combinación de cada una; el barrido está en el registro del
trabajo, no aquí, porque construir cuarenta series GARCH en cada suite costaría
más de lo que aporta.
"""

import numpy as np
import pandas as pd
import pytest

from core.application.use_cases.edge_test import (
    DEFAULT_HORIZON, DEFAULT_RV_WINDOW, _volatility_question, run_edge_test,
)


def _garch(n=3000, seed=1, omega=1e-6, alpha=0.09, beta=0.90):
    """Retornos CON agrupamiento de volatilidad y sin señal direccional."""
    rng = np.random.default_rng(seed)
    var = np.full(n, omega / (1 - alpha - beta))
    r = np.zeros(n)
    for i in range(1, n):
        var[i] = omega + alpha * r[i - 1] ** 2 + beta * var[i - 1]
        r[i] = rng.normal(0, np.sqrt(var[i]))
    return r


def _homoscedastic(n=3000, seed=2, sigma=0.012):
    """Retornos SIN agrupamiento: volatilidad constante en el tiempo."""
    return np.random.default_rng(seed).normal(0, sigma, n)


def _frame(returns, seed=9):
    """OHLCV con la forma que espera el motor, a partir de una serie de retornos."""
    close = 100.0 * np.exp(np.cumsum(returns))
    spread = np.abs(np.random.default_rng(seed).normal(0, 0.004, len(returns))) + 0.001
    return pd.DataFrame({
        "timestamp": np.arange(len(returns), dtype=np.int64) * 3_600_000,
        "open": close,
        "high": close * (1 + spread),
        "low": close * (1 - spread),
        "close": close,
        "volume": np.full(len(returns), 1e6),
    })


# Las dos series se reutilizan entre tests: construir una GARCH de 3.000 puntos
# es un bucle en Python y no hace falta repetirlo por cada aserción.
@pytest.fixture(scope="module")
def con_agrupamiento():
    return run_edge_test(_frame(_garch()), horizon=24, rv_window=24, n_splits=5)


@pytest.fixture(scope="module")
def sin_agrupamiento():
    return run_edge_test(_frame(_homoscedastic()), horizon=24, rv_window=24, n_splits=5)


@pytest.fixture(scope="module")
def vol_homo():
    return _volatility_question(_frame(_homoscedastic()), horizon=24, rv_window=24,
                                n_splits=5)


@pytest.fixture(scope="module")
def vol_garch():
    return _volatility_question(_frame(_garch()), horizon=24, rv_window=24, n_splits=5)


class TestTheFalsePositiveThePersistenceCriterionProduced:
    """
    Sobre una serie homocedástica —volatilidad constante, es decir, la hipótesis
    del documento FALSA por construcción— el criterio de partida respondía
    VOLATILITY, con R² relativo de +0,45 frente a la persistencia y p < 0,001.

    No era un bug: era que «batir a la persistencia» no es una hipótesis nula.
    La persistencia es un estimador RUIDOSO de una constante, y cualquier
    promedio la mejora encogiendo hacia la media, sin usar una sola pizca de
    información temporal. Eso es una mejora de predicción en sentido estricto, y
    no es lo que afirma la hipótesis.
    """

    @pytest.mark.unit
    def test_a_constant_volatility_series_is_not_declared_predictable(self, vol_homo):
        assert not vol_homo["predictable"]
        assert vol_homo["best_predictor"] is None

    @pytest.mark.unit
    def test_and_har_still_beats_persistence_there_which_is_exactly_the_point(self, vol_homo):
        """Si este test empezara a fallar, el falso positivo habría desaparecido
        por otro motivo y la corrección del criterio dejaría de estar justificada
        por evidencia. Se deja para que el día que cambie, se note."""
        assert vol_homo["har_beats_persistence"]
        assert vol_homo["oos_r2_har_vs_persistence"] > 0.2

    @pytest.mark.unit
    def test_no_candidate_beats_the_constant_mean_there(self, vol_homo):
        """La hipótesis nula correcta. La persistencia, además, sale MUCHO peor
        que la media: es exactamente el ruido que HAR estaba «mejorando»."""
        assert not any(c["beats_constant"] for c in vol_homo["candidates"].values())
        assert vol_homo["candidates"]["persistence"]["oos_r2_vs_constant"] < 0

    @pytest.mark.unit
    def test_no_candidate_correlates_enough_to_matter(self, vol_homo):
        """Segunda red, independiente de la primera: un predictor que acierta el
        nivel pero no el momento no sirve para nada de lo que se construiría
        encima. Aquí ninguno pasa de |0,15|."""
        for c in vol_homo["candidates"].values():
            assert abs(c["correlation"]) < 0.15

    @pytest.mark.unit
    def test_neither_condition_alone_would_be_enough(self, vol_homo):
        """Sobre esta serie, la persistencia llega a mostrar una correlación de
        +0,07 estadísticamente significativa —con 2.400 observaciones, un efecto
        minúsculo se distingue de cero— y es económicamente nula. Que la
        significancia sola no baste es el motivo de exigir además batir a la
        media constante, que ahí sale en −0,74.

        Es el mismo argumento que el módulo de significancia aplica al edge
        direccional: un p-valor pequeño no es un efecto grande."""
        for c in vol_homo["candidates"].values():
            assert not c["works"]
        assert not any(c["beats_constant"] for c in vol_homo["candidates"].values())

    @pytest.mark.unit
    def test_the_whole_test_answers_neither_on_that_series(self, sin_agrupamiento):
        assert sin_agrupamiento["verdict"] == "NEITHER"


class TestTheFalseNegativeThePersistenceCriterionProduced:
    """
    El otro lado del mismo error, y el más caro: sobre series GARCH —volatilidad
    agrupada POR CONSTRUCCIÓN— el criterio de partida decía NEITHER en 7 de 9
    combinaciones de tamaño y semilla, con correlaciones de 0,6–0,7 entre lo
    predicho y lo ocurrido.

    El motivo tampoco era un bug: en un GARCH casi integrado (α+β = 0,99) la
    persistencia YA ES una predicción casi óptima. Exigir batirla es exigir ganar
    un concurso de modelos, no responder si hay señal. La pregunta del documento
    es si la volatilidad se puede anticipar, no si HAR es la mejor forma de
    hacerlo.
    """

    @pytest.mark.unit
    def test_a_garch_series_is_declared_predictable(self, vol_garch):
        assert vol_garch["predictable"]

    @pytest.mark.unit
    def test_and_har_does_not_beat_persistence_there_which_is_the_point(self, vol_garch):
        """El caso que el criterio de partida archivaba: hay señal evidente y el
        modelo de la literatura no bate al predictor trivial, porque el trivial ya
        es casi óptimo."""
        assert not vol_garch["har_beats_persistence"]

    @pytest.mark.unit
    def test_persistence_alone_is_what_carries_the_verdict(self, vol_garch):
        """Y es una respuesta perfectamente válida: si la volatilidad de las
        próximas horas es la de las últimas, la volatilidad ES predecible y el
        predictor es la persistencia."""
        assert vol_garch["candidates"]["persistence"]["works"]
        assert vol_garch["best_predictor"] == "persistence"

    @pytest.mark.unit
    def test_it_beats_the_constant_mean_by_a_wide_margin(self, vol_garch):
        assert vol_garch["oos_r2_vs_constant"] > 0.2


class TestItStillDetectsWhatIsThere:
    """
    La otra mitad de la calibración. Un árbitro que nunca dice que sí no es
    prudente: es inútil. Si estos tests fallaran, el NEITHER de arriba no
    significaría nada.
    """

    @pytest.mark.unit
    def test_a_garch_series_is_declared_predictable(self, con_agrupamiento):
        assert con_agrupamiento["volatility"]["predictable"]

    @pytest.mark.unit
    def test_the_multiplicity_of_two_candidates_is_paid_for(self, con_agrupamiento):
        """Declarar predecible «si alguno de los dos funciona» son dos
        oportunidades de acertar por azar. Cobrarlas a 0,05 cada una daría un
        10 % de falsos positivos anunciando un 5 %."""
        assert con_agrupamiento["volatility"]["alpha_per_candidate"] == pytest.approx(0.025)

    @pytest.mark.unit
    def test_the_correlation_is_of_the_size_the_literature_reports(self, con_agrupamiento):
        """Los HAR-RV publicados reportan correlaciones del orden de 0,4–0,7. Un
        valor muy por encima sería sospechoso de fuga, no una buena noticia."""
        assert 0.35 < con_agrupamiento["volatility"]["correlation"] < 0.90

    @pytest.mark.unit
    def test_the_verdict_is_volatility(self, con_agrupamiento):
        assert con_agrupamiento["verdict"] == "VOLATILITY"

    @pytest.mark.unit
    def test_the_two_series_are_told_apart(self, con_agrupamiento, sin_agrupamiento):
        """El resumen de la calibración: mismo arnés, mismos parámetros, dos
        series que solo se diferencian en si la volatilidad se agrupa."""
        assert con_agrupamiento["verdict"] != sin_agrupamiento["verdict"]


class TestTheDirectionQuestion:

    @pytest.mark.unit
    def test_a_series_without_directional_signal_is_not_declared_significant(
            self, con_agrupamiento, sin_agrupamiento):
        assert not con_agrupamiento["direction"]["significant"]
        assert not sin_agrupamiento["direction"]["significant"]

    @pytest.mark.unit
    def test_it_reports_how_much_sample_the_observed_edge_would_need(self, con_agrupamiento):
        """La cifra que convierte «no hay edge» en «no se puede saber», que son
        conclusiones opuestas."""
        d = con_agrupamiento["direction"]
        assert "observations_needed" in d and "n_oos" in d

    @pytest.mark.unit
    def test_answerable_is_not_the_same_as_significant(self, sin_agrupamiento):
        """Un edge puede ser significativo por casualidad sobre poca muestra;
        `answerable` dice si la muestra alcanzaba para preguntarlo siquiera."""
        d = sin_agrupamiento["direction"]
        assert "answerable" in d and "significant" in d

    @pytest.mark.unit
    def test_an_edge_confidence_interval_is_always_reported(self, con_agrupamiento):
        low, high = con_agrupamiento["direction"]["edge_ci"]
        assert low <= con_agrupamiento["direction"]["edge"] <= high

    @pytest.mark.unit
    def test_too_short_a_series_says_so_instead_of_answering(self):
        out = run_edge_test(_frame(_homoscedastic(150, seed=3)), horizon=24,
                            rv_window=24, n_splits=5)
        assert not out["direction"]["answerable"]
        assert not out["volatility"]["answerable"]
        assert out["verdict"] == "NEITHER"


class TestTheProtocolIsStated:
    """
    Un veredicto sin su protocolo es una opinión. Quien lo lea dentro de seis
    meses tiene que poder saber contra qué se midió sin abrir el código.
    """

    @pytest.mark.unit
    def test_the_report_names_the_null_hypothesis_it_tested_against(self, con_agrupamiento):
        protocolo = con_agrupamiento["protocol"]
        assert "MEDIA CONSTANTE" in protocolo
        assert "correlacione" in protocolo
        assert "alfa" in protocolo

    @pytest.mark.unit
    def test_it_admits_the_criterion_was_changed_and_why(self, con_agrupamiento):
        """Callar que el criterio cambió DESPUÉS de ver los resultados sería el
        mismo patrón que este motor critica en otros. Decirlo —junto con sobre
        qué datos se descubrió, sintéticos y con la respuesta conocida de
        antemano— es lo que separa calibrar de ajustar al resultado."""
        protocolo = con_agrupamiento["protocol"]
        assert "descartó" in protocolo
        assert "homocedástica" in protocolo     # el falso positivo
        assert "GARCH" in protocolo             # el falso negativo

    @pytest.mark.unit
    def test_the_power_table_travels_with_the_verdict(self, con_agrupamiento):
        """Sin ella, un `NEITHER` direccional se lee como «no hay edge» cuando
        lo que dice es «con esta muestra no se puede saber»."""
        ref = con_agrupamiento["power_reference"]
        assert ref["direction_edge_2pct"] > 1000
        assert ref["volatility_r045"] < 100

    @pytest.mark.unit
    def test_both_questions_are_measured_under_the_same_protocol(self, con_agrupamiento):
        """Comparar dos preguntas validadas de forma distinta no compararía las
        preguntas: compararía las validaciones."""
        assert con_agrupamiento["horizon_bars"] == 24
        assert con_agrupamiento["n_splits"] == 5

    @pytest.mark.unit
    def test_the_verdict_carries_a_conclusion_in_words(self, con_agrupamiento):
        assert len(con_agrupamiento["conclusion"]) > 40

    @pytest.mark.unit
    def test_the_defaults_are_a_day_of_hourly_candles(self):
        """24 velas horarias es la escala en la que el agrupamiento de
        volatilidad está documentado. El horizonte y la purga son el MISMO
        parámetro: separarlos permitiría desincronizarlos."""
        assert DEFAULT_RV_WINDOW == 24 and DEFAULT_HORIZON == 24


class TestTheVerdictLogic:
    """
    Los cuatro caminos, sin tener que fabricar una serie para cada uno: la
    lógica de veredicto se comprueba sobre resultados ya calculados.
    """

    @staticmethod
    def _verdict(monkeypatch, *, predictable, significant):
        import core.application.use_cases.edge_test as mod
        monkeypatch.setattr(mod, "_volatility_question",
                            lambda *a, **k: {"predictable": predictable, "n_oos": 500})
        monkeypatch.setattr(mod, "_direction_question",
                            lambda *a, **k: {"significant": significant, "n_oos": 500})
        return mod.run_edge_test(_frame(_homoscedastic(400, seed=4)))["verdict"]

    @pytest.mark.unit
    def test_volatility_only(self, monkeypatch):
        assert self._verdict(monkeypatch, predictable=True, significant=False) == "VOLATILITY"

    @pytest.mark.unit
    def test_direction_only(self, monkeypatch):
        assert self._verdict(monkeypatch, predictable=False, significant=True) == "DIRECTION"

    @pytest.mark.unit
    def test_both(self, monkeypatch):
        assert self._verdict(monkeypatch, predictable=True, significant=True) == "BOTH"

    @pytest.mark.unit
    def test_neither(self, monkeypatch):
        assert self._verdict(monkeypatch, predictable=False, significant=False) == "NEITHER"

    @pytest.mark.unit
    def test_a_directional_only_result_is_treated_as_suspicious(self, monkeypatch):
        """Es lo contrario de lo que predice la literatura. Que el veredicto lo
        celebre en vez de mandar a buscar el error sería el fallo más caro que
        puede cometer esta herramienta."""
        import core.application.use_cases.edge_test as mod
        monkeypatch.setattr(mod, "_volatility_question",
                            lambda *a, **k: {"predictable": False, "n_oos": 500})
        monkeypatch.setattr(mod, "_direction_question",
                            lambda *a, **k: {"significant": True, "n_oos": 500})
        out = mod.run_edge_test(_frame(_homoscedastic(400, seed=4)))
        assert "error" in out["conclusion"]

    @pytest.mark.unit
    def test_both_questions_signalling_also_raises_an_eyebrow(self, monkeypatch):
        import core.application.use_cases.edge_test as mod
        monkeypatch.setattr(mod, "_volatility_question",
                            lambda *a, **k: {"predictable": True, "n_oos": 500})
        monkeypatch.setattr(mod, "_direction_question",
                            lambda *a, **k: {"significant": True, "n_oos": 500})
        out = mod.run_edge_test(_frame(_homoscedastic(400, seed=4)))
        assert "artefacto" in out["conclusion"]


class TestItDoesNotCheat:

    @pytest.mark.unit
    def test_the_constant_baseline_uses_the_training_mean_never_the_test_mean(self):
        """Usar la media del tramo que se va a predecir le regalaría la respuesta
        a la línea base — y como la base es la que decide el veredicto, sería
        fuga a favor de decir NO, que es el error más difícil de detectar."""
        import core.application.use_cases.edge_test as mod
        vistos = []
        real = mod.vf.HARModel

        class Espia(real):
            def fit(self, X, y):
                vistos.append(len(y))
                return super().fit(X, y)

        mod.vf.HARModel = Espia
        try:
            out = _volatility_question(_frame(_garch(1200, seed=5)),
                                       horizon=24, rv_window=24, n_splits=5)
        finally:
            mod.vf.HARModel = real
        # Ventana expansiva: cada tramo de entrenamiento es mayor que el anterior.
        assert vistos == sorted(vistos)
        assert out["n_oos"] > 0

    @pytest.mark.unit
    def test_the_folds_are_purged(self):
        """Con horizonte 24 la etiqueta de la fila k se resuelve 24 velas
        después; sin purga, las últimas 24 filas de cada entrenamiento contienen
        ya información del tramo de test."""
        r = _garch(1500, seed=6)
        estrecho = _volatility_question(_frame(r), horizon=1, rv_window=24, n_splits=5)
        ancho = _volatility_question(_frame(r), horizon=200, rv_window=24, n_splits=5)
        assert ancho["n_oos"] < estrecho["n_oos"]

    @pytest.mark.unit
    def test_the_report_says_how_many_candles_it_saw(self, con_agrupamiento):
        assert con_agrupamiento["candles"] == 3000
