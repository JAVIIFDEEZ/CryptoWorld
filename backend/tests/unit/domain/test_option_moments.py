"""
test_option_moments.py — ¿Recupera la integral la volatilidad que se plantó?

Aquí hay una ventaja que casi ningún otro módulo de este motor tiene: **se puede
construir el dato de entrada con la respuesta conocida exactamente**. Si se
generan precios de opciones con Black-Scholes a una volatilidad σ conocida, la
varianza libre de modelo tiene que devolver σ. No «algo parecido»: σ.

Eso convierte los tests en una verificación de la fórmula y no en una descripción
de lo que el código hace. Y permite medir el sesgo de truncación en vez de
suponerlo: se estrecha la cadena a propósito y se comprueba que el resultado baja
—nunca sube—, que es lo que dice la teoría.
"""

import numpy as np
import pytest

from core.domain.services.option_moments import (
    DAYS_PER_YEAR, MIN_STRIKES, WING_DELTA, OptionQuote, model_free_variance,
    variance_risk_premium, wing_structure,
)


def _bs(forward: float, strike: float, sigma: float, T: float) -> tuple:
    """Precios y deltas de Black-Scholes sobre el forward (Black-76, r = 0)."""
    from scipy.stats import norm

    if T <= 0 or sigma <= 0:
        return max(forward - strike, 0.0), max(strike - forward, 0.0), 1.0, -1.0
    sq = sigma * np.sqrt(T)
    d1 = (np.log(forward / strike) + 0.5 * sq ** 2) / sq
    d2 = d1 - sq
    call = forward * norm.cdf(d1) - strike * norm.cdf(d2)
    put = strike * norm.cdf(-d2) - forward * norm.cdf(-d1)
    return float(call), float(put), float(norm.cdf(d1)), float(-norm.cdf(-d1))


def _cadena(forward=100_000.0, sigma=0.60, dias=30.0, n=81, ancho_sigma=4.0,
            skew=0.0):
    """
    Cadena sintética a volatilidad conocida.

    `ancho_sigma` es hasta dónde llegan los strikes, en desviaciones del
    movimiento esperado — el parámetro con el que se mide la truncación.
    `skew` inclina la sonrisa linealmente en log-strike para probar las alas.
    """
    T = dias / DAYS_PER_YEAR
    paso = forward * sigma * np.sqrt(T) * ancho_sigma / (n // 2)
    strikes = forward + paso * np.arange(-(n // 2), n // 2 + 1)
    strikes = strikes[strikes > 0]

    filas = []
    for k in strikes:
        moneyness = np.log(k / forward)
        s = max(sigma + skew * moneyness, 0.05)
        call, put, dc, dp = _bs(forward, float(k), s, T)
        filas.append(OptionQuote(strike=float(k), call_price=call, put_price=put,
                                 call_iv=s, put_iv=s, call_delta=dc, put_delta=dp))
    return filas, T


class TestLaIntegralRecuperaLaVolatilidadPlantada:
    """
    El test que verifica la fórmula en vez de describirla. Si esto falla, todo lo
    que dependa del módulo es ficción.
    """

    @pytest.mark.unit
    def test_recupera_una_volatilidad_del_60_por_ciento(self):
        quotes, _ = _cadena(sigma=0.60, ancho_sigma=6.0, n=201)
        out = model_free_variance(quotes, forward=100_000.0, days_to_expiry=30.0)
        assert out["available"]
        assert out["implied_vol_annual"] == pytest.approx(0.60, rel=0.02)

    @pytest.mark.unit
    def test_y_una_del_20_por_ciento(self):
        quotes, _ = _cadena(sigma=0.20, ancho_sigma=6.0, n=201)
        out = model_free_variance(quotes, forward=100_000.0, days_to_expiry=30.0)
        assert out["implied_vol_annual"] == pytest.approx(0.20, rel=0.02)

    @pytest.mark.unit
    def test_y_una_del_120_por_ciento_que_es_territorio_cripto(self):
        quotes, _ = _cadena(sigma=1.20, ancho_sigma=6.0, n=201)
        out = model_free_variance(quotes, forward=100_000.0, days_to_expiry=30.0)
        assert out["implied_vol_annual"] == pytest.approx(1.20, rel=0.03)

    @pytest.mark.unit
    def test_funciona_a_distintos_vencimientos(self):
        for dias in (7.0, 30.0, 90.0, 180.0):
            quotes, _ = _cadena(sigma=0.60, dias=dias, ancho_sigma=6.0, n=201)
            out = model_free_variance(quotes, forward=100_000.0, days_to_expiry=dias)
            assert out["implied_vol_annual"] == pytest.approx(0.60, rel=0.04), dias

    @pytest.mark.unit
    def test_no_depende_del_nivel_de_precio(self):
        """La varianza es adimensional: la misma σ con BTC a 40.000 o a 120.000."""
        bajo, _ = _cadena(forward=40_000.0, sigma=0.60, ancho_sigma=6.0, n=201)
        alto, _ = _cadena(forward=120_000.0, sigma=0.60, ancho_sigma=6.0, n=201)
        v1 = model_free_variance(bajo, 40_000.0, 30.0)["implied_vol_annual"]
        v2 = model_free_variance(alto, 120_000.0, 30.0)["implied_vol_annual"]
        assert v1 == pytest.approx(v2, rel=0.02)


class TestElSesgoDeTruncacionSeMideNoSeSupone:
    """
    La teoría dice que truncar las colas SIEMPRE infravalora, porque el integrando
    es positivo y quitar trozos solo puede restar. Aquí se comprueba, porque es el
    límite más importante del módulo y en cripto las cadenas son estrechas.
    """

    @pytest.mark.unit
    def test_una_cadena_estrecha_infravalora(self):
        ancha, _ = _cadena(sigma=0.60, ancho_sigma=6.0, n=201)
        estrecha, _ = _cadena(sigma=0.60, ancho_sigma=1.5, n=201)
        v_ancha = model_free_variance(ancha, 100_000.0, 30.0)["implied_vol_annual"]
        v_estrecha = model_free_variance(estrecha, 100_000.0, 30.0)["implied_vol_annual"]
        assert v_estrecha < v_ancha
        assert v_estrecha < 0.60          # por debajo de la verdad, nunca por encima

    @pytest.mark.unit
    def test_el_sesgo_va_siempre_en_la_misma_direccion(self):
        """Nunca sobrevalora. Si en algún ancho saliera por encima de la verdad,
        la fórmula tendría un error de signo en alguna parte."""
        for ancho in (1.0, 2.0, 3.0, 4.0, 6.0):
            quotes, _ = _cadena(sigma=0.60, ancho_sigma=ancho, n=201)
            v = model_free_variance(quotes, 100_000.0, 30.0)["implied_vol_annual"]
            assert v <= 0.60 * 1.02, ancho

    @pytest.mark.unit
    def test_reporta_hasta_donde_llega_la_cadena_en_sigmas(self):
        """Es la cifra que permite juzgar cuánto pesa la truncación. Sin ella, el
        número de volatilidad no se puede auditar."""
        quotes, _ = _cadena(sigma=0.60, ancho_sigma=2.0, n=101)
        out = model_free_variance(quotes, 100_000.0, 30.0)
        assert 1.0 < out["coverage_sigma_up"] < 3.0
        assert "infravalora" in out["note"]

    @pytest.mark.unit
    def test_menos_strikes_se_reportan_para_poder_descontar_el_error(self):
        quotes, _ = _cadena(n=11, ancho_sigma=4.0)
        out = model_free_variance(quotes, 100_000.0, 30.0)
        assert out["n_strikes"] <= 11


class TestNoProduceNumerosQueNoPuedeSostener:

    @pytest.mark.unit
    def test_una_cadena_demasiado_corta_se_rechaza(self):
        quotes, _ = _cadena(n=5, ancho_sigma=4.0)
        out = model_free_variance(quotes[:3], 100_000.0, 30.0)
        assert out["available"] is False
        assert f"{MIN_STRIKES}" in out["note"]

    @pytest.mark.unit
    def test_un_vencimiento_pasado_se_rechaza(self):
        quotes, _ = _cadena()
        assert model_free_variance(quotes, 100_000.0, 0.0)["available"] is False

    @pytest.mark.unit
    def test_strikes_sin_precio_no_cuentan_como_cero(self):
        """Un strike sin cotización es «no hay dato», no «vale cero». Contarlo
        como cero restaría varianza."""
        quotes, _ = _cadena(n=41, ancho_sigma=4.0)
        con_huecos = [
            OptionQuote(strike=q.strike, call_price=None, put_price=None,
                        call_iv=q.call_iv, put_iv=q.put_iv,
                        call_delta=q.call_delta, put_delta=q.put_delta)
            if i % 2 else q
            for i, q in enumerate(quotes)
        ]
        out = model_free_variance(con_huecos, 100_000.0, 30.0)
        assert out["n_strikes"] < len(quotes)
        assert out["available"] is True

    @pytest.mark.unit
    def test_declara_su_metodo(self):
        quotes, _ = _cadena()
        assert model_free_variance(quotes, 100_000.0, 30.0)["method"] == "MODEL_FREE_VIX"


class TestLasAlasDeLaSonrisa:

    @pytest.mark.unit
    def test_una_sonrisa_plana_no_tiene_asimetria(self):
        quotes, _ = _cadena(sigma=0.60, skew=0.0)
        out = wing_structure(quotes)
        assert out["available"]
        assert out["risk_reversal_pct"] == pytest.approx(0.0, abs=0.5)

    @pytest.mark.unit
    def test_una_sonrisa_inclinada_a_la_baja_da_risk_reversal_negativo(self):
        """Puts más caras que calls: miedo a caer. Es el régimen habitual en
        renta variable."""
        quotes, _ = _cadena(sigma=0.60, skew=-0.5)
        out = wing_structure(quotes)
        assert out["risk_reversal_pct"] < 0
        assert out["skew_side"] == "BAJISTA"

    @pytest.mark.unit
    def test_y_al_contrario_cuando_se_paga_por_la_subida(self):
        """En cripto ocurre, y es lo que hace informativo este indicador aquí: un
        detector de miedo copiado de renta variable llegaría con el signo fijo."""
        quotes, _ = _cadena(sigma=0.60, skew=0.5)
        out = wing_structure(quotes)
        assert out["risk_reversal_pct"] > 0
        assert out["skew_side"] == "ALCISTA"

    @pytest.mark.unit
    def test_el_delta_de_las_alas_es_la_convencion_de_mesa(self):
        assert WING_DELTA == 0.25

    @pytest.mark.unit
    def test_se_interpola_en_delta_y_no_en_strike(self):
        """«La put de 25 delta» significa lo mismo con BTC a 40.000 que a 120.000;
        «la put de strike 35.000» no significa nada estable."""
        bajo, _ = _cadena(forward=40_000.0, sigma=0.60, skew=-0.5)
        alto, _ = _cadena(forward=120_000.0, sigma=0.60, skew=-0.5)
        rr1 = wing_structure(bajo)["risk_reversal_pct"]
        rr2 = wing_structure(alto)["risk_reversal_pct"]
        assert rr1 == pytest.approx(rr2, rel=0.1)

    @pytest.mark.unit
    def test_no_extrapola_cuando_la_cadena_no_llega(self):
        """Extrapolar la sonrisa es inventarse las alas, que es justo el dato que
        se busca."""
        quotes, _ = _cadena(ancho_sigma=0.15, n=9)     # solo cerca del dinero
        out = wing_structure(quotes)
        assert out["available"] is False
        assert "No se extrapola" in out["note"]

    @pytest.mark.unit
    def test_la_mariposa_mide_convexidad(self):
        """Alas por encima del dinero = se paga por movimiento grande en
        cualquier dirección."""
        quotes, _ = _cadena(sigma=0.60, skew=0.0)
        # Sonrisa en U: se suben las dos alas sobre el ATM.
        convexa = []
        for q in quotes:
            m = abs(np.log(q.strike / 100_000.0))
            s = 0.60 + 0.8 * m
            convexa.append(OptionQuote(strike=q.strike, call_price=q.call_price,
                                       put_price=q.put_price, call_iv=s, put_iv=s,
                                       call_delta=q.call_delta, put_delta=q.put_delta))
        assert wing_structure(convexa)["butterfly_pct"] > 0


class TestLaPrimaDeRiesgoDeVarianza:

    @pytest.mark.unit
    def test_implicita_por_encima_de_realizada_sale_cara(self):
        out = variance_risk_premium(0.60 ** 2, 0.40 ** 2)
        assert out["expensive"] is True
        assert out["vrp_vol_points"] == pytest.approx(20.0, abs=0.1)

    @pytest.mark.unit
    def test_y_por_debajo_sale_barata(self):
        out = variance_risk_premium(0.30 ** 2, 0.50 ** 2)
        assert out["expensive"] is False
        assert "infravalorando" in out["note"]

    @pytest.mark.unit
    def test_publica_el_ratio_ademas_de_la_diferencia(self):
        """La diferencia en puntos depende del nivel; el ratio no, y permite
        comparar regímenes de volatilidad distintos."""
        out = variance_risk_premium(0.60 ** 2, 0.40 ** 2)
        assert out["iv_rv_ratio"] == pytest.approx(2.25, rel=0.01)

    @pytest.mark.unit
    def test_avisa_de_que_no_es_un_carry_cosechable(self):
        """La prima paga el riesgo de cola: muchas ganancias pequeñas y una
        pérdida enorme. Es el mismo perfil de pago que hace peligroso al
        martingala, y el documento de edge lo descartó por eso."""
        out = variance_risk_premium(0.60 ** 2, 0.40 ** 2)
        assert "riesgo de cola" in out["note"]

    @pytest.mark.unit
    def test_valores_no_validos_se_rechazan(self):
        assert variance_risk_premium(0.0, 0.1)["available"] is False
        assert variance_risk_premium(0.1, -1.0)["available"] is False
