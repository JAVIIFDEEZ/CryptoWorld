"""
test_feature_study.py — Validar el instrumento antes de creerse su veredicto.

Este estudio existe para responder a una pregunta cuya respuesta más probable es
«no»: ¿aportan las variables exógenas información que las técnicas no tengan? Y
ahí aparece el problema de fondo de todo resultado negativo: **un detector roto
también dice que no**.

Por eso el test central de este fichero no comprueba que el estudio diga NO_EDGE
sobre ruido —eso lo haría igual si estuviera midiendo mal— sino que **detecte
una señal plantada a propósito**. Un `NO_EDGE` de un instrumento que nunca ha
dicho que sí no es un resultado: es un instrumento sin calibrar.

Los tests usan un clasificador deliberadamente pequeño: lo que se está probando
es la maquinaria de medición, no la capacidad del modelo.
"""

import numpy as np
import pandas as pd
import pytest
from sklearn.tree import DecisionTreeClassifier

from core.application.use_cases.feature_study import (
    CLUSTER_THRESHOLD, _cluster_columns, compare_feature_sets, mda_by_cluster,
)
from core.domain.services.exogenous_features import AVAILABLE_SUFFIX


def _tree():
    return DecisionTreeClassifier(max_depth=4, random_state=0)


def _noise_frame(n=600, cols=4, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({f"ruido_{i}": rng.normal(size=n) for i in range(cols)})


class TestClustering:
    """
    Con features correlacionadas, el MDA individual reparte la importancia entre
    ellas y las hunde todas: si dos columnas dicen lo mismo, permutar una apenas
    mueve la precisión porque la otra la sustituye.
    """

    @pytest.mark.unit
    def test_two_copies_of_the_same_column_land_together(self):
        rng = np.random.default_rng(1)
        base = rng.normal(size=300)
        frame = pd.DataFrame({
            "a": base,
            "a_casi_igual": base + rng.normal(0, 0.01, 300),
            "independiente": rng.normal(size=300),
        })
        clusters = _cluster_columns(frame)
        pareja = [c for c in clusters if "a" in c][0]
        assert set(pareja) == {"a", "a_casi_igual"}
        assert ["independiente"] in clusters

    @pytest.mark.unit
    def test_independent_columns_stay_apart(self):
        clusters = _cluster_columns(_noise_frame(400, cols=5, seed=2))
        assert len(clusters) == 5

    @pytest.mark.unit
    def test_the_threshold_is_the_one_the_book_uses(self):
        """Mismo listón que el filtro de decorrelación del libro de estrategias:
        por debajo de 0,7 dos series todavía aportan variación propia."""
        assert CLUSTER_THRESHOLD == 0.7

    @pytest.mark.unit
    def test_a_single_column_does_not_break_it(self):
        assert _cluster_columns(pd.DataFrame({"sola": [1.0, 2.0, 3.0]})) == [["sola"]]


class TestMdaDetectsWhatItShould:
    """
    La calibración del instrumento. Si el MDA no encuentra una columna que SÍ
    determina la etiqueta, su silencio sobre las exógenas no significa nada.
    """

    @staticmethod
    def _planted(n=800, seed=3):
        """Una columna que decide la etiqueta y tres que no."""
        rng = np.random.default_rng(seed)
        signal = rng.normal(size=n)
        y = (signal > 0).astype(int)
        frame = _noise_frame(n, cols=3, seed=seed + 1)
        frame["la_que_informa"] = signal
        return frame, y

    @pytest.mark.unit
    def test_the_informative_column_comes_out_on_top(self):
        frame, y = self._planted()
        out = mda_by_cluster(frame, y, _tree, horizon=1, n_splits=3)
        assert out["clusters"][0]["columns"] == ["la_que_informa"]
        assert out["clusters"][0]["significant"]

    @pytest.mark.unit
    def test_noise_columns_do_not_come_out_significant(self):
        frame, y = self._planted()
        out = mda_by_cluster(frame, y, _tree, horizon=1, n_splits=3)
        for cluster in out["clusters"]:
            if "la_que_informa" not in cluster["columns"]:
                assert not cluster["significant"]

    @pytest.mark.unit
    def test_pure_noise_produces_no_significant_cluster(self):
        rng = np.random.default_rng(5)
        frame = _noise_frame(700, cols=4, seed=5)
        y = rng.integers(0, 2, 700)
        out = mda_by_cluster(frame, y, _tree, horizon=1, n_splits=3)
        assert not any(c["significant"] for c in out["clusters"])

    @pytest.mark.unit
    def test_importance_carries_its_own_uncertainty(self):
        """Una media de 0,01 con desviación 0,05 no es importancia, es ruido. Sin
        el error estándar no se pueden distinguir."""
        frame, y = self._planted()
        out = mda_by_cluster(frame, y, _tree, horizon=1, n_splits=3)
        for cluster in out["clusters"]:
            assert "std_error" in cluster and "significant" in cluster

    @pytest.mark.unit
    def test_it_uses_purged_folds(self):
        """Medir importancia sobre una partición con fuga sería medir la fuga."""
        frame, y = self._planted(n=400)
        wide = mda_by_cluster(frame, y, _tree, horizon=60, n_splits=3)
        assert wide["n_folds"] <= 3


class TestTheComparison:

    @staticmethod
    def _sets(n=900, seed=7, exogenous_informs=True):
        rng = np.random.default_rng(seed)
        exo_signal = rng.normal(size=n)
        tech = _noise_frame(n, cols=4, seed=seed + 1)
        exo = pd.DataFrame({
            "exo_a": exo_signal,
            "exo_b": exo_signal + rng.normal(0, 0.02, n),
            f"grupo{AVAILABLE_SUFFIX}": np.ones(n),
        })
        y = ((exo_signal > 0) if exogenous_informs
             else (rng.normal(size=n) > 0)).astype(int)
        return tech, exo, y

    @pytest.mark.unit
    def test_it_finds_the_exogenous_block_when_the_block_informs(self):
        """La prueba de que el veredicto negativo, cuando llegue, valdrá algo."""
        tech, exo, y = self._sets(exogenous_informs=True)
        out = compare_feature_sets(tech, exo, y, _tree, horizon=1, n_splits=3)
        assert out["verdict"] == "EXOGENOUS_HELPS"
        assert out["exogenous_clusters_in_top_third"]
        assert out["edge_delta"] > 0

    @pytest.mark.unit
    def test_it_says_no_when_the_exogenous_block_is_noise(self):
        tech, exo, y = self._sets(exogenous_informs=False)
        out = compare_feature_sets(tech, exo, y, _tree, horizon=1, n_splits=3)
        assert out["verdict"] == "NO_EDGE"

    @pytest.mark.unit
    def test_the_availability_flags_never_become_features(self):
        """Dejarlas dentro permitiría aprender «cuando hay dato de funding
        estamos en 2025»: una fecha disfrazada de variable predictiva."""
        tech, exo, y = self._sets()
        out = compare_feature_sets(tech, exo, y, _tree, horizon=1, n_splits=3)
        every_column = [c for cl in out["importance"]["clusters"] for c in cl["columns"]]
        assert not any(c.endswith(AVAILABLE_SUFFIX) for c in every_column)

    @pytest.mark.unit
    def test_both_sets_are_measured_on_the_same_rows(self):
        """Si el conjunto ampliado se midiera sobre menos filas —las que tienen
        exógena— la comparación mezclaría dos efectos: el de las variables y el
        del cambio de muestra."""
        tech, exo, y = self._sets()
        out = compare_feature_sets(tech, exo, y, _tree, horizon=1, n_splits=3)
        assert out["technical_only"]["n"] == out["technical_plus_exogenous"]["n"]

    @pytest.mark.unit
    def test_the_criterion_declares_itself_frozen(self):
        """Fijarlo por escrito es lo que impide el movimiento clásico: mirar los
        números, encontrar algo que sobresalga y declarar que era lo que se
        buscaba."""
        tech, exo, y = self._sets()
        out = compare_feature_sets(tech, exo, y, _tree, horizon=1, n_splits=3)
        assert "CONGELADO" in out["criterion"]

    @pytest.mark.unit
    def test_the_result_admits_the_criterion_was_rewritten(self):
        """El criterio se reescribió dos veces durante la calibración. Callarlo
        sería exactamente el patrón que este módulo critica en otros; decirlo,
        junto con SOBRE QUÉ DATOS se hizo —sintéticos, con la respuesta conocida
        de antemano— es lo que separa calibrar un instrumento de ajustarlo al
        resultado que se busca."""
        tech, exo, y = self._sets()
        out = compare_feature_sets(tech, exo, y, _tree, horizon=1, n_splits=3)
        assert "SINTÉTICAS" in out["criterion_history"]
        assert "descartadas" in out["criterion_history"]

    @pytest.mark.unit
    def test_too_few_rows_says_so_instead_of_guessing(self):
        tech, exo, y = self._sets(n=60)
        out = compare_feature_sets(tech, exo, y, _tree, horizon=1, n_splits=3)
        assert out["verdict"] == "INSUFFICIENT_DATA"

    @pytest.mark.unit
    def test_rows_with_missing_exogenous_are_dropped_not_imputed(self):
        """Una imputación silenciosa daría más filas y menos verdad: el modelo
        aprendería del relleno."""
        tech, exo, y = self._sets()
        exo.loc[:200, "exo_a"] = np.nan
        out = compare_feature_sets(tech, exo, y, _tree, horizon=1, n_splits=3)
        assert out["n_samples"] < len(tech)
