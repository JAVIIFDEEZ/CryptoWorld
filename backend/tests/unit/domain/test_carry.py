"""
test_carry.py — Un flujo de caja no se valida como una predicción.

El resto de este motor pregunta siempre lo mismo: ¿se distingue del azar? Aquí
no hay predicción que validar — el funding está en el histórico, se cobró o no
se cobró. Lo que puede salir mal es otra cosa, y es lo que estos tests cubren:

  · que las CUATRO comisiones se cuenten (dos patas, entrada y salida), porque
    contar menos convierte un carry mediocre en uno excelente sobre el papel;
  · que el signo esté del lado correcto, porque el corto cobra donde el resto
    del motor paga y ahí es fácil equivocarse;
  · que el nulo destruya la afirmación bajo prueba y solo esa;
  · que la liquidación se mire, porque un carry excelente con la liquidación al
    8 % de distancia no es un carry excelente.

Y la calibración va en las dos direcciones, como en todo lo demás: un régimen de
funding positivo tiene que salir OPERABLE y uno sin sesgo tiene que salir
rechazado. Un instrumento que nunca dice que no autoriza cualquier cosa.
"""

import numpy as np
import pytest

from core.domain.services.carry import (
    PERIODS_PER_YEAR, CarryCosts, CarryPosition, carry_verdict, funding_income,
    liquidation_price, null_distribution, shock_margin_probability, simulate_carry,
)


def _funding_positivo(n=1095, media=0.0001, ruido=0.00005, seed=1):
    """Un año de funding con sesgo positivo: el régimen histórico habitual.

    0,01 % cada 8 h son unos 11 puntos porcentuales anualizados, que está dentro
    de lo que se ha visto en BTC en tramos largos.
    """
    rng = np.random.default_rng(seed)
    return rng.normal(media, ruido, n)


def _funding_sin_sesgo(n=1095, escala=0.0001, seed=2):
    """Misma magnitud, media cero: la hipótesis nula hecha datos."""
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, escala, n)


class TestElSignoEstaDelLadoCorrecto:
    """
    El resto del motor es long-only y trata un rate positivo como COSTE. El
    corto del delta-neutral está al otro lado y lo cobra. Reutilizar por
    descuido la función de coste invertiría el resultado entero.
    """

    @pytest.mark.unit
    def test_el_corto_cobra_cuando_el_funding_es_positivo(self):
        assert funding_income([0.0001], 10_000.0)[0] == pytest.approx(1.0)

    @pytest.mark.unit
    def test_y_paga_cuando_es_negativo(self):
        assert funding_income([-0.0001], 10_000.0)[0] == pytest.approx(-1.0)

    @pytest.mark.unit
    def test_el_ingreso_escala_con_el_nocional(self):
        assert funding_income([0.0002], 50_000.0)[0] == pytest.approx(10.0)

    @pytest.mark.unit
    def test_los_huecos_no_cuentan_como_cero(self):
        """Un NaN es «no hay dato», no «no se cobró». Tratarlos igual haría que
        un tramo sin histórico pareciera un tramo sin funding."""
        assert funding_income([0.0001, np.nan, 0.0001], 10_000.0).size == 2


class TestLasCuatroComisiones:

    @pytest.mark.unit
    def test_montar_y_deshacer_son_cuatro_ordenes(self):
        """Comprar spot, vender perp, y al revés al cerrar."""
        costes = CarryCosts(taker_fee_bps=5.0, slippage_bps=2.0)
        assert costes.round_trip_bps == pytest.approx(28.0)

    @pytest.mark.unit
    def test_el_coste_de_ordenes_sale_del_nocional(self):
        out = simulate_carry(_funding_positivo(), CarryPosition(notional_usd=10_000.0))
        assert out["order_costs_usd"] == pytest.approx(28.0, rel=1e-6)

    @pytest.mark.unit
    def test_un_tramo_corto_no_cubre_las_comisiones(self):
        """El resultado más común y el que más se enseña sin decir que es bruto:
        tres días de funding no pagan cuatro órdenes."""
        out = simulate_carry(_funding_positivo(n=9))      # 3 días
        assert out["gross_funding_usd"] > 0
        assert out["net_usd"] < 0

    @pytest.mark.unit
    def test_el_coste_de_capital_escala_con_el_tiempo(self):
        corto = simulate_carry(_funding_positivo(n=100),
                               costs=CarryCosts(capital_cost_annual_pct=5.0))
        largo = simulate_carry(_funding_positivo(n=1000),
                               costs=CarryCosts(capital_cost_annual_pct=5.0))
        assert largo["capital_cost_usd"] > corto["capital_cost_usd"] * 5


class TestElRendimientoSeMideSobreElCapitalInmovilizado:

    @pytest.mark.unit
    def test_el_capital_incluye_el_spot_y_el_margen(self):
        """Sobre el nocional saldría un número más halagüeño; el capital parado
        es el spot entero más el margen del corto."""
        out = simulate_carry(_funding_positivo(),
                             CarryPosition(notional_usd=10_000.0, margin_pct=0.20))
        assert out["capital_usd"] == pytest.approx(12_000.0)

    @pytest.mark.unit
    def test_un_ano_de_funding_positivo_rinde_lo_que_debe(self):
        """0,01 % cada 8 h sobre 10.000 USD son ~1.095 USD al año; sobre 12.000
        de capital y descontando 28 de comisiones, algo por encima del 8 %."""
        out = simulate_carry(_funding_positivo(n=1095, media=0.0001, ruido=0.0))
        assert out["gross_funding_usd"] == pytest.approx(1095.0, rel=1e-3)
        assert 8.0 < out["net_annualized_pct"] < 9.5

    @pytest.mark.unit
    def test_declara_cuantos_periodos_cobro(self):
        out = simulate_carry(_funding_positivo(n=300))
        assert out["periods"] == 300
        assert out["years"] == pytest.approx(300 / PERIODS_PER_YEAR, rel=1e-3)

    @pytest.mark.unit
    def test_sin_datos_lo_dice_en_vez_de_devolver_cero(self):
        assert simulate_carry([])["verdict"] == "SIN_DATOS"


class TestLaLiquidacionDeLaPataCorta:

    @pytest.mark.unit
    def test_el_corto_se_liquida_cuando_el_precio_sube(self):
        pos = CarryPosition(margin_pct=0.20, maintenance_margin=0.005)
        assert liquidation_price(100.0, pos) == pytest.approx(119.5)

    @pytest.mark.unit
    def test_menos_margen_acerca_la_liquidacion(self):
        """Más apalancamiento en la pata corta es más capital eficiente y más
        cerca del desastre: las dos cosas a la vez, y hay que verlas juntas."""
        holgado = liquidation_price(100.0, CarryPosition(margin_pct=0.50))
        ajustado = liquidation_price(100.0, CarryPosition(margin_pct=0.10))
        assert ajustado < holgado

    @pytest.mark.unit
    def test_detecta_que_el_maximo_del_tramo_habria_liquidado(self):
        out = simulate_carry(_funding_positivo(), CarryPosition(margin_pct=0.10),
                             entry_price=100.0, max_price=130.0)
        assert out["liquidated"] is True

    @pytest.mark.unit
    def test_y_que_no_lo_habria_hecho(self):
        out = simulate_carry(_funding_positivo(), CarryPosition(margin_pct=0.50),
                             entry_price=100.0, max_price=130.0)
        assert out["liquidated"] is False

    @pytest.mark.unit
    def test_el_shock_es_un_escenario_declarado_no_una_probabilidad(self):
        """Una probabilidad de liquidación necesita un modelo de la cola de la
        distribución de precios, que es lo que peor se estima en cripto. El
        escenario no lo necesita y se entiende sin él."""
        out = shock_margin_probability(_funding_positivo(),
                                       CarryPosition(margin_pct=0.20), shock_pct=15.0)
        assert out["survives"] is True
        assert out["buffer_pct"] == pytest.approx(19.5)

    @pytest.mark.unit
    def test_un_shock_mayor_que_el_colchon_liquida(self):
        out = shock_margin_probability(_funding_positivo(),
                                       CarryPosition(margin_pct=0.10), shock_pct=15.0)
        assert out["survives"] is False
        assert "LIQUIDA" in out["note"]


class TestElNuloDestruyeSoloLoQueSePrueba:
    """
    La afirmación del carry no es «acierto la dirección» sino «el funding es
    sistemáticamente positivo». El nulo tiene que negar eso y nada más.
    """

    @pytest.mark.unit
    def test_el_nulo_tiene_mediana_negativa_por_los_costes(self):
        """Sin sesgo de signo el flujo esperado es cero y quedan las cuatro
        comisiones: el nulo de un carry es PERDER dinero."""
        out = null_distribution(_funding_positivo())
        assert out["median_usd"] < 0

    @pytest.mark.unit
    def test_conserva_la_escala_del_funding(self):
        """Si el nulo usara magnitudes distintas, compararlo con lo observado no
        diría nada sobre el sesgo: mezclaría dos efectos."""
        grande = null_distribution(_funding_positivo(media=0.0, ruido=0.001))
        pequeno = null_distribution(_funding_positivo(media=0.0, ruido=0.00001))
        assert abs(grande["p95_usd"]) > abs(pequeno["p95_usd"]) * 10

    @pytest.mark.unit
    def test_declara_su_metodo(self):
        out = null_distribution(_funding_positivo())
        assert out["method"] == "SIGN_RANDOMIZATION"

    @pytest.mark.unit
    def test_es_reproducible(self):
        a = null_distribution(_funding_positivo(), seed=7)
        b = null_distribution(_funding_positivo(), seed=7)
        assert a["p95_usd"] == b["p95_usd"]

    @pytest.mark.unit
    def test_sin_datos_no_inventa_un_listón(self):
        assert null_distribution([])["p95_usd"] is None


class TestLaCalibracionEnLasDosDirecciones:
    """
    La mitad que importa: un instrumento que nunca dice que no autoriza
    cualquier cosa, y aquí lo que autoriza es poner dinero real.
    """

    @staticmethod
    def _veredicto(rates, position=None, costs=None, shock_pct=15.0):
        pos = position or CarryPosition()
        observado = simulate_carry(rates, pos, costs)
        nulo = null_distribution(rates, pos, costs)
        shock = shock_margin_probability(rates, pos, shock_pct)
        return carry_verdict(observado, nulo, shock)

    @pytest.mark.unit
    def test_un_regimen_de_funding_positivo_sale_operable(self):
        assert self._veredicto(_funding_positivo())["verdict"] == "OPERABLE"

    @pytest.mark.unit
    def test_un_funding_sin_sesgo_se_rechaza(self):
        """El caso que justifica el nulo: misma magnitud, sin sesgo, y el
        veredicto tiene que ser que no."""
        veredicto = self._veredicto(_funding_sin_sesgo())
        assert not veredicto["tradeable"]
        assert veredicto["verdict"] in ("NO_CUBRE_COSTES", "INDISTINGUIBLE_DEL_NULO")

    @pytest.mark.unit
    def test_un_funding_negativo_sostenido_se_rechaza(self):
        """El riesgo real del carry: el flujo cambia de sentido y se paga en
        lugar de cobrarse."""
        veredicto = self._veredicto(_funding_positivo(media=-0.0001))
        assert veredicto["verdict"] == "NO_CUBRE_COSTES"

    @pytest.mark.unit
    def test_un_carry_rentable_pero_mal_apalancado_no_sale_operable(self):
        """Rentable y a punto de liquidarse no es operable: es una apuesta a que
        no haya un día malo."""
        veredicto = self._veredicto(_funding_positivo(),
                                    CarryPosition(margin_pct=0.10), shock_pct=15.0)
        assert veredicto["verdict"] == "RIESGO_DE_LIQUIDACION"
        assert veredicto["covers_costs"] and veredicto["beats_null"]

    @pytest.mark.unit
    def test_las_comisiones_mandan_en_el_horizonte_corto_no_en_el_largo(self):
        """El umbral de rentabilidad es un número de PERIODOS, no de dinero.

        Con los costes por defecto —28 bps de ida y vuelta— y un funding del
        0,01 % cada 8 h, hacen falta 28 liquidaciones para cubrirlos: unos nueve
        días. Antes de eso el carry pierde por mucho que el funding sea bueno, y
        después las comisiones dejan de importar — por eso unas comisiones altas
        no tumban un carry anual, y decir lo contrario sería un error cómodo."""
        constante = np.full(1095, 0.0001)
        corto = simulate_carry(constante[:20])       # por debajo del umbral
        justo = simulate_carry(constante[:40])       # por encima
        assert corto["net_usd"] < 0
        assert justo["net_usd"] > 0

    @pytest.mark.unit
    def test_unas_comisiones_absurdas_si_lo_tumban(self):
        """La otra cara: el coste es una propiedad del venue, y hay venues donde
        esto sencillamente no se puede operar."""
        veredicto = self._veredicto(_funding_positivo(),
                                    costs=CarryCosts(taker_fee_bps=400.0,
                                                     slippage_bps=0.0))
        assert not veredicto["tradeable"]
        assert veredicto["verdict"] == "NO_CUBRE_COSTES"

    @pytest.mark.unit
    def test_las_tres_condiciones_viajan_con_el_veredicto(self):
        """Para que un rechazo diga POR QUÉ y no solo que no."""
        veredicto = self._veredicto(_funding_positivo())
        assert {"covers_costs", "beats_null", "survives_shock"} <= set(veredicto)

    @pytest.mark.unit
    def test_el_rechazo_por_nulo_explica_que_es_una_racha(self):
        veredicto = self._veredicto(_funding_positivo(media=0.000012, ruido=0.0002))
        if veredicto["verdict"] == "INDISTINGUIBLE_DEL_NULO":
            assert "racha" in veredicto["note"]
