"""
test_crypto_factors.py — El listón contra el que hay que medir, calibrado.

Este módulo existe para poder decir «tu Sharpe 2 es beta de mercado». Eso lo
convierte en el instrumento más peligroso de los que hay aquí: si midiera mal,
tumbaría estrategias buenas o —peor— dejaría pasar como alfa lo que es
exposición. Las dos direcciones importan y las dos se prueban.

La calibración central son tres estrategias construidas a propósito:

  · una que ES beta de mercado puro → alfa cero, beta 1, R² alto;
  · una que ES momento puro → alfa cero, beta de CMOM en 1;
  · una ortogonal con retorno propio → alfa positivo y significativo.

Si la tercera no saliera, el «SIN_ALFA» de las dos primeras no significaría nada:
sería el veredicto de un instrumento que nunca dice que sí.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services.crypto_factors import (
    FACTOR_NAMES, MIN_UNIVERSE, N_QUANTILES, REBALANCE_DAYS, build_factors,
    factor_alpha,
)


def _panel(n_periods=120, n_assets=20, seed=1, mom_premium=0.0, size_premium=0.0):
    """
    Panel sintético con premios plantados.

    `mom_premium` hace que las monedas con más momento previo rindan más la
    semana siguiente; `size_premium`, que las pequeñas rindan más. Sirven para
    comprobar que los factores capturan lo que dicen capturar.
    """
    rng = np.random.default_rng(seed)
    filas = []
    momento_previo = rng.normal(0, 0.1, n_assets)
    for p in range(n_periods):
        # Volumen en dólares muy dispersos, como en cripto real.
        size = np.exp(rng.normal(15, 2.0, n_assets))
        mercado = rng.normal(0.005, 0.05)
        rango_mom = (np.argsort(np.argsort(momento_previo)) / (n_assets - 1)) - 0.5
        rango_size = (np.argsort(np.argsort(size)) / (n_assets - 1)) - 0.5
        ret = (mercado
               + rng.normal(0, 0.08, n_assets)
               + mom_premium * rango_mom
               - size_premium * rango_size)
        for a in range(n_assets):
            filas.append({"period": p, "symbol": f"C{a}", "ret": float(ret[a]),
                          "size": float(size[a]), "mom": float(momento_previo[a])})
        momento_previo = ret          # el momento de la próxima es el retorno de esta
    return pd.DataFrame(filas)


def _factores(**kw):
    out = build_factors(_panel(**kw))
    assert out["available"], out["note"]
    return out["factors"]


class TestSeNiegaCuandoNoPuedeMedir:
    """
    Con 1.700 monedas un quintil son 340 carteras. Con 10, son 2. Devolver una
    serie en el segundo caso sería devolver ruido con nombre de factor.
    """

    @pytest.mark.unit
    def test_un_universo_pequeno_se_rechaza_en_vez_de_producir_ruido(self):
        out = build_factors(_panel(n_assets=6))
        assert out["available"] is False
        assert out["factors"] is None
        assert "Universo insuficiente" in out["note"]

    @pytest.mark.unit
    def test_el_minimo_deja_al_menos_dos_por_quintil(self):
        assert MIN_UNIVERSE >= 2 * N_QUANTILES

    @pytest.mark.unit
    def test_un_panel_sin_las_columnas_necesarias_lo_dice(self):
        out = build_factors(pd.DataFrame({"period": [1], "symbol": ["A"]}))
        assert out["available"] is False and "Faltan columnas" in out["note"]

    @pytest.mark.unit
    def test_declara_que_el_tamano_es_una_aproximacion(self):
        """Usar la capitalización de hoy para ordenar carteras del pasado sería
        lookahead, y de los que peor se detectan porque el número parece un dato."""
        out = build_factors(_panel())
        assert out["size_proxy"] == "DOLLAR_VOLUME"
        assert "lookahead" in out["note"]

    @pytest.mark.unit
    def test_cita_el_paper(self):
        """La construcción no es propia: si alguien discute el factor, tiene que
        poder ir a la fuente."""
        out = build_factors(_panel())
        assert "Liu" in out["reference"] and "Journal of Finance" in out["reference"]


class TestLosFactoresCapturanLoQueDicen:

    @pytest.mark.unit
    def test_el_rebalanceo_es_semanal_como_en_el_paper(self):
        """No es arbitrario: el momento de cripto vive entre una y cuatro semanas
        y se invierte más allá del mes, así que rebalancear mensualmente mediría
        la reversión."""
        assert REBALANCE_DAYS == 7

    @pytest.mark.unit
    def test_devuelve_las_tres_series(self):
        f = _factores()
        assert list(f.columns[:3]) == list(FACTOR_NAMES)

    @pytest.mark.unit
    def test_cmom_es_positivo_cuando_hay_premio_de_momento(self):
        f = _factores(mom_premium=0.06, n_periods=200)
        assert f["CMOM"].mean() > 0

    @pytest.mark.unit
    def test_cmom_no_inventa_premio_donde_no_lo_hay(self):
        f = _factores(mom_premium=0.0, n_periods=200, seed=5)
        assert abs(f["CMOM"].mean()) < 0.01

    @pytest.mark.unit
    def test_csmb_va_de_pequenas_menos_grandes(self):
        """Q5−Q1 sobre tamaño daría grandes menos pequeñas: el factor con el signo
        al revés, y todas las betas de tamaño interpretadas del revés con él."""
        f = _factores(size_premium=0.06, n_periods=200)
        assert f["CSMB"].mean() > 0

    @pytest.mark.unit
    def test_cmkt_se_parece_al_retorno_medio_del_universo(self):
        panel = _panel(n_periods=60)
        f = build_factors(panel)["factors"]
        medio = panel.groupby("period")["ret"].mean()
        # Ponderado por valor frente a equiponderado: correlacionados, no iguales.
        assert np.corrcoef(f["CMKT"].to_numpy(), medio.to_numpy())[0, 1] > 0.5

    @pytest.mark.unit
    def test_el_numero_de_activos_por_periodo_viaja_con_los_factores(self):
        """Un factor calculado sobre 11 activos y otro sobre 300 no son
        comparables, y quien lo lea tiene que poder verlo."""
        f = _factores()
        assert "n_assets" in f.columns and f["n_assets"].min() >= MIN_UNIVERSE


class TestElAlfaEsLoQueQuedaDespuesDeLosFactores:
    """
    La calibración que decide si este instrumento sirve. Tres estrategias con la
    respuesta conocida de antemano.
    """

    @pytest.mark.unit
    def test_beta_de_mercado_puro_no_tiene_alfa(self):
        """El caso más común y el más caro de confundir con un descubrimiento:
        mercado apalancado. Sharpe alto, alfa cero."""
        f = _factores(n_periods=200)
        estrategia = 1.5 * f["CMKT"].to_numpy()
        out = factor_alpha(estrategia, f)
        assert out["verdict"] == "SIN_ALFA"
        assert out["betas"]["CMKT"] == pytest.approx(1.5, abs=0.05)
        assert out["r_squared"] > 0.95

    @pytest.mark.unit
    def test_momento_puro_tampoco(self):
        """Es literalmente el resultado de LTW: nueve estrategias que parecían
        anomalías eran las mismas tres exposiciones."""
        f = _factores(n_periods=200, mom_premium=0.05)
        out = factor_alpha(f["CMOM"].to_numpy(), f)
        assert out["verdict"] == "SIN_ALFA"
        assert out["betas"]["CMOM"] == pytest.approx(1.0, abs=0.05)

    @pytest.mark.unit
    def test_una_estrategia_ortogonal_con_retorno_propio_si_tiene_alfa(self):
        """La mitad sin la cual el «SIN_ALFA» de arriba no significaría nada."""
        f = _factores(n_periods=200)
        rng = np.random.default_rng(9)
        estrategia = 0.02 + rng.normal(0, 0.01, len(f))   # ortogonal y rentable
        out = factor_alpha(estrategia, f)
        assert out["verdict"] == "ALFA"
        assert out["alpha"] == pytest.approx(0.02, abs=0.004)

    @pytest.mark.unit
    def test_alfa_mas_beta_se_separan_bien(self):
        """Mercado apalancado MÁS una idea propia: el alfa tiene que salir la
        idea, no la suma."""
        f = _factores(n_periods=250)
        rng = np.random.default_rng(11)
        estrategia = 0.015 + 1.2 * f["CMKT"].to_numpy() + rng.normal(0, 0.01, len(f))
        out = factor_alpha(estrategia, f)
        assert out["alpha"] == pytest.approx(0.015, abs=0.004)
        assert out["betas"]["CMKT"] == pytest.approx(1.2, abs=0.05)

    @pytest.mark.unit
    def test_ruido_sin_retorno_no_produce_alfa(self):
        f = _factores(n_periods=200)
        rng = np.random.default_rng(13)
        out = factor_alpha(rng.normal(0, 0.02, len(f)), f)
        assert out["verdict"] == "SIN_ALFA"


class TestLaInferenciaNoSeAutoenganya:

    @pytest.mark.unit
    def test_los_errores_estandar_son_robustos_a_autocorrelacion(self):
        """Los residuos de una estrategia están autocorrelacionados: las
        posiciones se solapan y los regímenes duran semanas. Con errores clásicos
        el intervalo se estrecha y el ruido sale significativo — el mismo error
        que la falta de purga, cometido en la inferencia."""
        f = _factores(n_periods=250)
        rng = np.random.default_rng(17)
        # Residuos suavizados: autocorrelación positiva fuerte, media cero.
        ruido = np.convolve(rng.normal(0, 0.03, len(f) + 20), np.ones(10) / 10,
                            mode="same")[:len(f)]
        out = factor_alpha(ruido, f)
        assert out["newey_west_lags"] >= 1
        assert out["verdict"] == "SIN_ALFA"

    @pytest.mark.unit
    def test_la_ventana_crece_con_la_muestra(self):
        corto = factor_alpha(np.random.default_rng(1).normal(0, 0.02, 60),
                             _factores(n_periods=60))
        largo = factor_alpha(np.random.default_rng(1).normal(0, 0.02, 400),
                             _factores(n_periods=400))
        assert largo["newey_west_lags"] >= corto["newey_west_lags"]

    @pytest.mark.unit
    def test_pocos_periodos_se_rechazan_en_vez_de_producir_un_alfa(self):
        f = _factores(n_periods=40)
        out = factor_alpha(np.zeros(10), f)
        assert out["available"] is False and "20 periodos" in out["note"]

    @pytest.mark.unit
    def test_el_informe_dice_cuanto_explican_los_factores(self):
        """Un R² alto con alfa cero es el diagnóstico completo: la estrategia
        funciona, y lo que hace ya se puede comprar."""
        f = _factores(n_periods=200)
        out = factor_alpha(1.5 * f["CMKT"].to_numpy(), f)
        assert "se consigue con exposición" in out["note"]

    @pytest.mark.unit
    def test_un_alfa_significativo_pero_economicamente_nulo_no_cuenta(self):
        """El modo degenerado que encontró la calibración: una estrategia que ES
        una combinación exacta de los factores deja residuos de 1e-17, el error
        estándar se va a cero y el t se dispara sobre un alfa de 0,0000. Un
        replicador de índice apalancado es ese caso en la vida real."""
        f = _factores(n_periods=200)
        out = factor_alpha(1.5 * f["CMKT"].to_numpy(), f)
        assert out["alpha_significant"] is True          # estadísticamente, sí
        assert out["alpha_economically_relevant"] is False
        assert out["verdict"] == "SIN_ALFA"              # y aun así, no es alfa
        assert "económicamente nulo" in out["note"]

    @pytest.mark.unit
    def test_el_alfa_se_reporta_tambien_anualizado(self):
        """Un alfa «de 0,0004 por periodo» no le dice nada a nadie; un 2 % anual,
        sí — y es la unidad en la que se compara con el coste de rebalancear."""
        f = _factores(n_periods=200)
        rng = np.random.default_rng(23)
        out = factor_alpha(0.01 + rng.normal(0, 0.01, len(f)), f)
        # `alpha` se publica redondeado a 6 decimales y la anualización se hace
        # sobre el valor sin redondear, así que la comparación es aproximada a
        # propósito: lo que se comprueba es que la unidad sea la correcta.
        assert out["alpha_annualized_pct"] == pytest.approx(
            out["alpha"] * 365 / 7 * 100, rel=1e-3)

    @pytest.mark.unit
    def test_las_betas_viajan_con_su_t(self):
        """Una beta de 1,5 con t de 0,4 no es una exposición: es ruido."""
        f = _factores(n_periods=200)
        out = factor_alpha(f["CMKT"].to_numpy(), f)
        assert set(out["beta_t"]) == set(FACTOR_NAMES)


class TestElInformeSigueSiendoCreible:
    """
    Un número aritméticamente correcto puede arruinar un informe. Con residuos de
    1e-17 los estadísticos t salen del orden de 1e14, y quien lee
    «t = +469074387171099» deja de creerse las cifras de al lado — con razón.
    """

    @pytest.mark.unit
    def test_ningun_estadistico_t_se_publica_sin_recortar(self):
        from core.domain.services.crypto_factors import T_STAT_CAP

        f = _factores(n_periods=200)
        out = factor_alpha(1.4 * f["CMKT"].to_numpy(), f)
        assert abs(out["alpha_t"]) <= T_STAT_CAP
        for t in out["beta_t"].values():
            assert abs(t) <= T_STAT_CAP

    @pytest.mark.unit
    def test_el_ajuste_degenerado_se_declara_y_no_solo_se_recorta(self):
        """Recortar el número sin explicarlo dejaría al lector preguntándose por
        qué la beta tiene un t de 999."""
        f = _factores(n_periods=200)
        out = factor_alpha(1.4 * f["CMKT"].to_numpy(), f)
        assert out["degenerate_fit"] is True

    @pytest.mark.unit
    def test_una_estrategia_normal_no_se_marca_como_degenerada(self):
        f = _factores(n_periods=200)
        rng = np.random.default_rng(31)
        out = factor_alpha(0.01 + rng.normal(0, 0.03, len(f)), f)
        assert out["degenerate_fit"] is False
