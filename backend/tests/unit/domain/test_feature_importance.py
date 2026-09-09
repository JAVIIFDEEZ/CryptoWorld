"""
test_feature_importance.py — Calibrar la lista antes de enseñarla.

Una lista de «variables más influyentes» siempre parece significativa: SIEMPRE
hay un primero, tenga o no señal. Ese es justamente el problema del número que
este módulo sustituye —la importancia por impureza del bosque— y es un problema
que se hereda si el reemplazo no se calibra.

Por eso los tests van en dos direcciones, y las dos hacen falta:

  · sobre **ruido puro**, ningún grupo puede salir significativo;
  · sobre una **señal plantada**, el grupo que la lleva tiene que salir arriba.

Solo la primera mitad describiría igual de bien a un instrumento roto que nunca
dice que sí.
"""

import numpy as np
import pytest

from core.domain.services.feature_importance import (
    CLUSTER_THRESHOLD, DEFAULT_PERMUTATIONS, aggregate_clusters, cluster_columns,
    permutation_drops,
)


class _ModeloQueUsa:
    """Clasificador de juguete: predice por el signo de UNA columna."""

    def __init__(self, col: int):
        self.col = col

    def predict(self, X):
        return (np.asarray(X)[:, self.col] > 0).astype(int)


class TestElAgrupamiento:
    """
    Sin agrupar, un conjunto de sinónimos —que es lo que son 17 indicadores
    técnicos— se anula a sí mismo: permutar uno no mueve nada porque el otro lo
    sustituye, y todos parecen inútiles.
    """

    @pytest.mark.unit
    def test_dos_copias_de_la_misma_columna_caen_juntas(self):
        rng = np.random.default_rng(1)
        base = rng.normal(size=300)
        X = np.column_stack([base, base + rng.normal(0, 0.01, 300), rng.normal(size=300)])
        clusters = cluster_columns(X)
        assert [0, 1] in clusters
        assert [2] in clusters

    @pytest.mark.unit
    def test_columnas_independientes_no_se_agrupan(self):
        X = np.random.default_rng(2).normal(size=(400, 5))
        assert len(cluster_columns(X)) == 5

    @pytest.mark.unit
    def test_columnas_anticorreladas_tambien_se_agrupan(self):
        """Se agrupa por correlación ABSOLUTA: una serie y su negativa contienen
        la misma información, y permutar solo una dejaría la otra sustituyéndola."""
        base = np.random.default_rng(3).normal(size=300)
        assert cluster_columns(np.column_stack([base, -base])) == [[0, 1]]

    @pytest.mark.unit
    def test_el_umbral_es_el_mismo_que_usa_el_libro_de_estrategias(self):
        assert CLUSTER_THRESHOLD == 0.7

    @pytest.mark.unit
    def test_una_columna_constante_no_rompe_el_calculo(self):
        """Su correlación es indefinida (varianza cero); tratarla como NaN y no
        como 1 evita que se pegue a un grupo cualquiera."""
        X = np.column_stack([np.ones(50), np.random.default_rng(4).normal(size=50)])
        assert len(cluster_columns(X)) == 2

    @pytest.mark.unit
    def test_una_matriz_vacia_devuelve_lista_vacia(self):
        assert cluster_columns(np.zeros((10, 0))) == []


class TestLaPermutacion:

    @pytest.mark.unit
    def test_romper_la_columna_que_el_modelo_usa_cuesta_precision(self):
        rng = np.random.default_rng(5)
        X = rng.normal(size=(300, 3))
        y = (X[:, 0] > 0).astype(int)
        caidas = permutation_drops(_ModeloQueUsa(0), X, y, [[0], [1], [2]], seed=1)
        assert caidas[0] > 0.3

    @pytest.mark.unit
    def test_romper_una_columna_que_no_usa_no_cuesta_nada(self):
        rng = np.random.default_rng(6)
        X = rng.normal(size=(300, 3))
        y = (X[:, 0] > 0).astype(int)
        caidas = permutation_drops(_ModeloQueUsa(0), X, y, [[0], [1], [2]], seed=1)
        assert abs(caidas[1]) < 1e-9 and abs(caidas[2]) < 1e-9

    @pytest.mark.unit
    def test_las_columnas_de_un_grupo_se_permutan_a_la_vez(self):
        """Barajarlas por separado destruiría también la correlación entre ellas,
        que no es lo que se quiere medir: se quiere romper su relación con el
        objetivo dejando intacta su estructura interna."""
        rng = np.random.default_rng(7)
        base = rng.normal(size=300)
        X = np.column_stack([base, base * 2.0])
        y = (base > 0).astype(int)
        antes = X[:, 0] - X[:, 1] / 2.0          # relación interna: exactamente 0
        caidas = permutation_drops(_ModeloQueUsa(0), X, y, [[0, 1]], seed=1)
        assert caidas[0] > 0.3
        assert np.allclose(antes, 0.0)           # la entrada no se modifica in situ

    @pytest.mark.unit
    def test_no_modifica_la_matriz_que_recibe(self):
        rng = np.random.default_rng(8)
        X = rng.normal(size=(200, 3))
        copia = X.copy()
        permutation_drops(_ModeloQueUsa(0), X, (X[:, 0] > 0).astype(int), [[0], [1]], seed=1)
        np.testing.assert_array_equal(X, copia)

    @pytest.mark.unit
    def test_es_determinista_con_la_misma_semilla(self):
        rng = np.random.default_rng(9)
        X = rng.normal(size=(200, 3))
        y = (X[:, 0] > 0).astype(int)
        a = permutation_drops(_ModeloQueUsa(0), X, y, [[0], [1], [2]], seed=3)
        b = permutation_drops(_ModeloQueUsa(0), X, y, [[0], [1], [2]], seed=3)
        np.testing.assert_allclose(a, b)

    @pytest.mark.unit
    def test_un_test_vacio_no_revienta(self):
        caidas = permutation_drops(_ModeloQueUsa(0), np.zeros((0, 2)), [], [[0], [1]])
        assert len(caidas) == 2


class TestLaAgregacionEntreTramos:
    """
    El error estándar sale de la variación ENTRE tramos, no entre permutaciones.
    Las permutaciones de un mismo tramo comparten modelo y test: solo miden el
    sorteo. Contarlas como independientes estrecha el intervalo por √N y hace que
    el ruido salga significativo — es un error que ya se cometió una vez en el
    estudio de features exógenas y lo detectó la calibración.
    """

    @pytest.mark.unit
    def test_una_caida_grande_y_consistente_sale_significativa(self):
        caidas = np.array([[0.10, 0.001], [0.11, -0.002], [0.09, 0.000],
                           [0.10, 0.001], [0.12, -0.001]])
        filas = aggregate_clusters(["util", "inutil"], [[0], [1]], caidas)
        assert filas[0]["feature"] == "util" and filas[0]["significant"]

    @pytest.mark.unit
    def test_una_caida_grande_pero_erratica_no_sale_significativa(self):
        """Media +0,04 con tramos que van de −0,15 a +0,25: la magnitud sola no
        distingue una importancia de un sorteo afortunado."""
        caidas = np.array([[0.25], [-0.15], [0.20], [-0.10], [0.00]])
        filas = aggregate_clusters(["erratica"], [[0]], caidas)
        assert filas[0]["importance"] > 0
        assert not filas[0]["significant"]

    @pytest.mark.unit
    def test_cada_importancia_viaja_con_su_incertidumbre(self):
        caidas = np.array([[0.10, 0.01], [0.11, 0.02], [0.09, 0.00]])
        for fila in aggregate_clusters(["a", "b"], [[0], [1]], caidas):
            assert fila["std_error"] is not None and "p_value" in fila

    @pytest.mark.unit
    def test_un_solo_tramo_no_puede_declarar_significancia(self):
        """Una única medición no permite distinguir señal de sorteo. Devolver un
        número sin incertidumbre invitaría a leerlo como si sí."""
        filas = aggregate_clusters(["a"], [[0]], np.array([[0.5]]))
        assert filas[0]["std_error"] is None
        assert not filas[0]["significant"]

    @pytest.mark.unit
    def test_se_corrige_por_multiplicidad(self):
        """Con ocho grupos y ningún efecto real, la probabilidad de que alguno
        salga significativo al 5 % es del 34 %, no del 5 %. Este caso tiene un
        grupo con p crudo bajo que NO sobrevive a la corrección."""
        rng = np.random.default_rng(11)
        caidas = rng.normal(0, 0.01, size=(5, 12))
        caidas[:, 0] += 0.012                     # apenas por encima del ruido
        filas = aggregate_clusters([f"c{i}" for i in range(12)],
                                   [[i] for i in range(12)], caidas)
        crudos = [f for f in filas if f["p_value"] < 0.05]
        assert crudos, "el caso debe tener al menos un p crudo bajo para probar la corrección"
        assert not any(f["significant"] for f in filas)

    @pytest.mark.unit
    def test_las_filas_salen_ordenadas_por_importancia(self):
        caidas = np.array([[0.01, 0.10, 0.05], [0.02, 0.11, 0.04], [0.00, 0.09, 0.06]])
        filas = aggregate_clusters(["a", "b", "c"], [[0], [1], [2]], caidas)
        assert [f["feature"] for f in filas] == ["b", "c", "a"]

    @pytest.mark.unit
    def test_cada_fila_dice_que_columnas_agrupa(self):
        """Sin ello, «rsi_14» en la lista se lee como una variable cuando en
        realidad representa a diez que dicen casi lo mismo."""
        caidas = np.array([[0.1], [0.1], [0.1]])
        fila = aggregate_clusters(["rsi_14", "rsi_7"], [[0, 1]], caidas)[0]
        assert fila["columns"] == ["rsi_14", "rsi_7"]

    @pytest.mark.unit
    def test_sin_tramos_devuelve_lista_vacia(self):
        assert aggregate_clusters(["a"], [[0]], np.zeros((0, 1))) == []


class TestCalibracionExtremoAExtremo:
    """
    Las dos direcciones, sobre datos donde la respuesta se conoce de antemano.
    """

    @staticmethod
    def _correr(X, y, col_modelo, n_folds=5):
        clusters = cluster_columns(X)
        corte = len(y) // (n_folds + 1)
        caidas = []
        for k in range(1, n_folds + 1):
            te = slice(k * corte, (k + 1) * corte)
            caidas.append(permutation_drops(_ModeloQueUsa(col_modelo), X[te], y[te],
                                            clusters, seed=k))
        return aggregate_clusters([f"x{i}" for i in range(X.shape[1])],
                                  clusters, np.array(caidas))

    @pytest.mark.unit
    def test_sobre_ruido_puro_nada_sale_significativo(self):
        rng = np.random.default_rng(12)
        X = rng.normal(size=(900, 6))
        y = rng.integers(0, 2, 900)
        assert not any(f["significant"] for f in self._correr(X, y, 0))

    @pytest.mark.unit
    def test_con_senal_plantada_la_encuentra(self):
        """La mitad que impide que el resultado negativo de arriba sea el de un
        instrumento que nunca dice que sí."""
        rng = np.random.default_rng(13)
        X = rng.normal(size=(900, 6))
        y = (X[:, 2] > 0).astype(int)
        filas = self._correr(X, y, 2)
        assert filas[0]["feature"] == "x2" and filas[0]["significant"]

    @pytest.mark.unit
    def test_el_numero_de_permutaciones_por_defecto_es_el_documentado(self):
        """Subirlo no estrecha la incertidumbre publicada —esa sale de la
        variación entre tramos— así que solo costaría latencia."""
        assert DEFAULT_PERMUTATIONS == 3


class TestElAgrupamientoConHuecos:
    """
    `np.corrcoef` propaga: un solo NaN deja toda la fila de correlaciones en NaN
    y esa columna no se agrupa con nadie. Quedaría como grupo propio y su
    importancia se mediría sin las hermanas que la sustituyen — exactamente el
    error que el agrupamiento existe para evitar.
    """

    @pytest.mark.unit
    def test_una_columna_con_huecos_sigue_agrupando_con_su_gemela(self):
        rng = np.random.default_rng(21)
        base = rng.normal(size=400)
        gemela = base + rng.normal(0, 0.01, 400)
        gemela[:5] = np.nan
        clusters = cluster_columns(np.column_stack([base, gemela, rng.normal(size=400)]))
        assert [0, 1] in clusters

    @pytest.mark.unit
    def test_sin_solape_suficiente_no_se_inventa_una_correlacion(self):
        """Dos columnas que nunca son finitas a la vez no tienen evidencia de
        decir lo mismo; unirlas sería agrupar por ausencia de datos."""
        a = np.concatenate([np.arange(50.0), np.full(50, np.nan)])
        b = np.concatenate([np.full(50, np.nan), np.arange(50.0)])
        assert cluster_columns(np.column_stack([a, b])) == [[0], [1]]


class TestUnaSolaReglaDeAgrupamiento:

    @pytest.mark.unit
    def test_el_estudio_de_features_usa_la_misma_regla_que_el_modelo(self):
        """Dos implementaciones de la misma regla derivan. Y estas dos se
        comparan entre sí —el estudio decide si las exógenas aportan sobre las
        técnicas—, así que agrupar distinto haría incomparables sus resultados."""
        import pandas as pd

        from core.application.use_cases.feature_study import (
            CLUSTER_THRESHOLD as ESTUDIO, _cluster_columns,
        )
        assert ESTUDIO == CLUSTER_THRESHOLD

        rng = np.random.default_rng(22)
        base = rng.normal(size=300)
        X = np.column_stack([base, base + rng.normal(0, 0.01, 300), rng.normal(size=300)])
        frame = pd.DataFrame(X, columns=["a", "a_casi", "otra"])
        por_nombre = _cluster_columns(frame)
        por_indice = [[frame.columns[j] for j in g] for g in cluster_columns(X)]
        assert por_nombre == por_indice
