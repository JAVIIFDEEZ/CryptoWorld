"""
test_conformal.py — La cobertura que se promete, medida.

Este módulo sustituye una constante elegida a mano por un umbral derivado de una
tasa de error. Todo su valor está en que esa tasa se cumpla: si se pide un 10 % de
fallo y sale un 25 %, el número es peor que el 0,05 anterior, porque el 0,05 al
menos no prometía nada.

Por eso el test central no comprueba que el código corra: comprueba que **la
cobertura empírica se acerque a la nominal** sobre datos donde se conoce la
respuesta. Y su pareja obligatoria: que los conjuntos sean PEQUEÑOS. Una cobertura
del 90 % con conjuntos de tamaño 2 se consigue diciendo siempre «no sé», y sería
un instrumento inútil que pasa el primer test con nota.
"""

import numpy as np
import pytest

from core.domain.services.conformal import (
    DEFAULT_ALPHA, DEFAULT_GAMMA, LABEL_DOWN, LABEL_UP, MIN_CALIBRATION,
    AdaptiveConformal, calibrate, coverage, nonconformity, prediction_set,
)


def _modelo_bueno(n=2000, seed=1, fuerza=3.0):
    """Probabilidades informativas: el modelo sabe algo de verdad."""
    rng = np.random.default_rng(seed)
    senal = rng.normal(0, 1, n)
    p_up = 1.0 / (1.0 + np.exp(-fuerza * senal))
    y = (rng.random(n) < p_up).astype(int)
    return p_up, y


def _modelo_inutil(n=2000, seed=2):
    """Probabilidades sin información: moneda al aire declarada como tal."""
    rng = np.random.default_rng(seed)
    return np.full(n, 0.5), rng.integers(0, 2, n)


def _modelo_sobreseguro(n=2000, seed=3):
    """El caso peligroso: probabilidades extremas y sin información. Un modelo
    que dice «95 % alcista» y acierta la mitad de las veces."""
    rng = np.random.default_rng(seed)
    p_up = rng.choice([0.05, 0.95], size=n)
    return p_up, rng.integers(0, 2, n)


class TestLaPuntuacionDeNoConformidad:

    @pytest.mark.unit
    def test_una_prediccion_perfecta_puntua_cero(self):
        assert nonconformity([1.0], [1])[0] == pytest.approx(0.0)
        assert nonconformity([0.0], [0])[0] == pytest.approx(0.0)

    @pytest.mark.unit
    def test_un_fallo_total_puntua_uno(self):
        assert nonconformity([0.0], [1])[0] == pytest.approx(1.0)
        assert nonconformity([1.0], [0])[0] == pytest.approx(1.0)

    @pytest.mark.unit
    def test_la_moneda_al_aire_puntua_la_mitad(self):
        assert nonconformity([0.5], [1])[0] == pytest.approx(0.5)

    @pytest.mark.unit
    def test_mide_la_probabilidad_de_la_etiqueta_verdadera_y_no_la_de_subida(self):
        """Si midiera siempre `1 − p_up`, un modelo que acierta las bajadas
        saldría malísimo."""
        assert nonconformity([0.2], [0])[0] == pytest.approx(0.2)


class TestElUmbral:

    @pytest.mark.unit
    def test_usa_la_correccion_de_muestra_finita(self):
        """El índice es ⌈(n+1)(1−α)⌉ y no ⌈n(1−α)⌉. Con n pequeño la diferencia
        no es cosmética: es lo que separa la cobertura nominal de una cobertura
        sistemáticamente por debajo."""
        scores = np.linspace(0.0, 1.0, 100)
        out = calibrate(scores, alpha=0.10)
        # ⌈101 × 0,90⌉ = 91 → el elemento 91 de 100 ordenados
        # `q_hat` se publica redondeado a 6 decimales; lo que se comprueba es
        # que el índice elegido sea el 91 de 100 y no el 90.
        assert out["q_hat"] == pytest.approx(scores[90], abs=1e-6)

    @pytest.mark.unit
    def test_una_calibracion_corta_se_rechaza(self):
        out = calibrate(np.linspace(0, 1, 10))
        assert out["available"] is False
        assert "Calibración insuficiente" in out["note"]

    @pytest.mark.unit
    def test_el_minimo_deja_que_el_cuantil_no_lo_decida_un_punto(self):
        assert MIN_CALIBRATION >= 1.0 / DEFAULT_ALPHA

    @pytest.mark.unit
    def test_un_alfa_mas_exigente_pide_un_umbral_mas_laxo(self):
        """Menos error tolerado significa conjuntos más grandes: la probabilidad
        mínima para entrar baja."""
        scores = _puntuaciones()
        estricto = calibrate(scores, alpha=0.01)
        laxo = calibrate(scores, alpha=0.20)
        assert estricto["min_proba"] < laxo["min_proba"]

    @pytest.mark.unit
    def test_traduce_el_umbral_a_probabilidad_minima(self):
        """Es la cifra comparable con la vieja banda del 0,05, y sin ella nadie
        puede juzgar si el cambio fue a mejor."""
        out = calibrate(_puntuaciones())
        assert out["min_proba"] == pytest.approx(1.0 - out["q_hat"])


def _puntuaciones(n=500, seed=7):
    p, y = _modelo_bueno(n, seed)
    return nonconformity(p, y)


class TestElConjuntoDePredicciones:

    @pytest.mark.unit
    def test_una_probabilidad_extrema_da_una_sola_etiqueta(self):
        out = prediction_set(0.95, q_hat=0.6)      # mínimo 0,40
        assert out["set"] == [LABEL_UP] and out["status"] == "DECIDIDO"

    @pytest.mark.unit
    def test_la_zona_intermedia_da_las_dos(self):
        """Es el NEUTRAL de antes, pero derivado del error tolerado en vez de
        elegido a mano."""
        out = prediction_set(0.5, q_hat=0.6)
        assert set(out["set"]) == {LABEL_UP, LABEL_DOWN}
        assert out["status"] == "AMBOS" and out["label"] == "NEUTRAL"

    @pytest.mark.unit
    def test_un_umbral_exigente_puede_dejar_el_conjunto_vacio(self):
        """Vacío no es duda entre dos: es que ninguna etiqueta encaja con lo que
        el modelo vio al calibrarse. Es información, no un fallo."""
        out = prediction_set(0.5, q_hat=0.3)       # mínimo 0,70
        assert out["set"] == [] and out["status"] == "VACIO"
        assert "no reconoce el terreno" in out["note"]

    @pytest.mark.unit
    def test_el_conjunto_vacio_no_proclama_direccion(self):
        assert prediction_set(0.5, q_hat=0.3)["label"] == "NEUTRAL"

    @pytest.mark.unit
    def test_es_simetrico(self):
        arriba = prediction_set(0.9, q_hat=0.5)
        abajo = prediction_set(0.1, q_hat=0.5)
        assert arriba["set"] == [LABEL_UP] and abajo["set"] == [LABEL_DOWN]


class TestLaCoberturaPrometidaSeCumple:
    """
    El test central. Si esto falla, el módulo entero es peor que la constante que
    sustituye — porque la constante no prometía nada.
    """

    @staticmethod
    def _partir(p, y, corte=0.5):
        k = int(len(p) * corte)
        return (p[:k], y[:k]), (p[k:], y[k:])

    @pytest.mark.unit
    def test_la_cobertura_empirica_se_acerca_a_la_nominal(self):
        p, y = _modelo_bueno(4000)
        (pc, yc), (pt, yt) = self._partir(p, y)
        q = calibrate(nonconformity(pc, yc), alpha=0.10)["q_hat"]
        out = coverage(pt, yt, q)
        assert 86.0 <= out["covered_pct"] <= 94.0

    @pytest.mark.unit
    def test_y_tambien_con_otro_alfa(self):
        p, y = _modelo_bueno(4000, seed=11)
        (pc, yc), (pt, yt) = self._partir(p, y)
        q = calibrate(nonconformity(pc, yc), alpha=0.20)["q_hat"]
        assert 75.0 <= coverage(pt, yt, q)["covered_pct"] <= 86.0

    @pytest.mark.unit
    def test_un_modelo_bueno_produce_conjuntos_pequenos(self):
        """La pareja obligatoria del test anterior: una cobertura del 90 % con
        conjuntos de tamaño 2 se consigue diciendo siempre «no sé»."""
        p, y = _modelo_bueno(4000, fuerza=4.0)
        (pc, yc), (pt, yt) = self._partir(p, y)
        q = calibrate(nonconformity(pc, yc))["q_hat"]
        assert coverage(pt, yt, q)["avg_set_size"] < 1.6

    @pytest.mark.unit
    def test_un_modelo_inutil_produce_conjuntos_grandes_y_lo_admite(self):
        """Lo correcto ante un modelo sin información no es equivocarse: es
        devolver las dos etiquetas siempre. El método lo hace solo."""
        p, y = _modelo_inutil(4000)
        (pc, yc), (pt, yt) = self._partir(p, y)
        q = calibrate(nonconformity(pc, yc))["q_hat"]
        out = coverage(pt, yt, q)
        assert out["avg_set_size"] > 1.9
        assert out["covered_pct"] > 95.0          # cubre porque nunca se moja

    @pytest.mark.unit
    def test_un_modelo_sobreseguro_no_engana_a_la_cobertura(self):
        """El caso peligroso: dice «95 % alcista» y acierta la mitad. La
        calibración conformal lo detecta y ensancha los conjuntos, que es
        exactamente lo que la banda fija del 0,05 no podía hacer."""
        p, y = _modelo_sobreseguro(4000)
        (pc, yc), (pt, yt) = self._partir(p, y)
        q = calibrate(nonconformity(pc, yc))["q_hat"]
        out = coverage(pt, yt, q)
        assert out["covered_pct"] >= 85.0
        assert out["avg_set_size"] > 1.5

    @pytest.mark.unit
    def test_el_informe_avisa_de_que_el_tamano_es_la_medida_de_utilidad(self):
        p, y = _modelo_bueno(1000)
        q = calibrate(nonconformity(p, y))["q_hat"]
        assert "conjuntos pequeños" in coverage(p, y, q)["note"]


class TestLaVersionAdaptativa:
    """
    La garantía clásica exige intercambiabilidad y las series financieras no la
    cumplen. Estos tests fijan lo que sí se puede afirmar.
    """

    @pytest.mark.unit
    def test_un_fallo_endurece_el_nivel_y_un_acierto_lo_relaja(self):
        ac = AdaptiveConformal(alpha=0.10, gamma=0.05)
        tras_fallo = ac.update(covered=False)
        assert tras_fallo < 0.10
        ac2 = AdaptiveConformal(alpha=0.10, gamma=0.05)
        assert ac2.update(covered=True) > 0.10

    @pytest.mark.unit
    def test_el_nivel_nunca_sale_del_intervalo_valido(self):
        """Fuera de (0,1) no define un cuantil. Cien fallos seguidos no pueden
        producir un nivel negativo."""
        ac = AdaptiveConformal(alpha=0.10, gamma=0.5)
        for _ in range(100):
            ac.update(covered=False)
        assert 0.0 < ac.alpha_t < 1.0

    @pytest.mark.unit
    def test_converge_a_la_tasa_pedida_a_largo_plazo(self):
        """La afirmación honesta: convergencia a largo plazo, sin hipótesis de
        distribución ni de estacionariedad."""
        p, y = _modelo_bueno(6000, seed=21)
        k = 1500
        ac = AdaptiveConformal(alpha=0.10)
        out = ac.run(p[k:], y[k:], nonconformity(p[:k], y[:k]))
        assert out["available"] is True
        assert abs(out["empirical_error_pct"] - 10.0) < 4.0

    @pytest.mark.unit
    def test_absorbe_un_cambio_de_regimen_ensanchando_conjuntos(self):
        """La prueba de por qué hace falta la versión adaptativa: se calibra con
        un modelo bueno y se corre sobre un tramo donde el modelo deja de
        funcionar. El umbral fijo se quedaría corto; el adaptativo reacciona."""
        bueno_p, bueno_y = _modelo_bueno(3000, seed=31)
        malo_p, malo_y = _modelo_sobreseguro(3000, seed=32)
        calib = nonconformity(bueno_p, bueno_y)

        fijo = coverage(malo_p, malo_y, calibrate(calib)["q_hat"])
        ac = AdaptiveConformal(alpha=0.10)
        adaptativo = ac.run(malo_p, malo_y, calib)

        # El adaptativo paga cobertura con tamaño, que es el intercambio correcto.
        assert adaptativo["alpha_drift"] < 0
        assert adaptativo["avg_set_size"] > fijo["avg_set_size"]

    @pytest.mark.unit
    def test_sin_calibracion_suficiente_no_adapta_nada(self):
        ac = AdaptiveConformal()
        out = ac.run([0.5] * 50, [1] * 50, [0.5] * 5)
        assert out["available"] is False

    @pytest.mark.unit
    def test_declara_que_la_garantia_es_de_largo_plazo(self):
        """Es la diferencia entre citar el teorema y citarlo con sus
        condiciones."""
        p, y = _modelo_bueno(2000, seed=41)
        out = AdaptiveConformal().run(p[500:], y[500:], nonconformity(p[:500], y[:500]))
        assert "LARGO PLAZO" in out["note"]
        assert "intercambiabilidad" in out["note"]

    @pytest.mark.unit
    def test_los_valores_por_defecto_son_los_documentados(self):
        assert DEFAULT_ALPHA == 0.10 and DEFAULT_GAMMA == 0.01


class TestLosEmpatesExactosNoSePierden:
    """
    Con probabilidades cuantizadas los empates con el umbral son frecuentes, y la
    forma ingenua de la condición (`p ≥ 1 − q̂`) los pierde por el error de la
    resta. En la calibración costó 15 puntos de cobertura: se pedía un 90 % y
    salía un 74 %.
    """

    @pytest.mark.unit
    def test_una_etiqueta_justo_en_el_limite_entra(self):
        # p = 0,05 con q̂ = 0,95: la puntuación de ALCISTA es exactamente 0,95.
        out = prediction_set(0.05, q_hat=0.95)
        assert set(out["set"]) == {LABEL_UP, LABEL_DOWN}

    @pytest.mark.unit
    def test_y_la_cobertura_lo_refleja(self):
        p = np.full(400, 0.05)
        y = np.random.default_rng(3).integers(0, 2, 400)
        out = coverage(p, y, q_hat=0.95)
        assert out["covered_pct"] == 100.0
        assert out["avg_set_size"] == pytest.approx(2.0)

    @pytest.mark.unit
    def test_lo_que_queda_fuera_sigue_quedando_fuera(self):
        """El arreglo no puede volverse permisivo: una puntuación por encima del
        umbral tiene que seguir excluida."""
        out = prediction_set(0.02, q_hat=0.95)     # ALCISTA puntúa 0,98 > 0,95
        assert out["set"] == [LABEL_DOWN]
