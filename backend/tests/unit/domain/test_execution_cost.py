"""
test_execution_cost.py — La escalera de coste, y lo que promete no ser.

El número que produce este módulo es el que convierte una señal en una decisión:
un edge de 30 puntos básicos es un negocio a 10.000 USD y una pérdida a
1.000.000 en un activo estrecho, y es el mismo edge.

Por eso los tests cubren dos cosas distintas. La primera es la aritmética: que
el coste crezca con la raíz del tamaño y no linealmente, porque de ahí sale toda
la intuición del usuario sobre cuánto puede mover. La segunda es la **honestidad
de la etiqueta**: esto es un modelo con un parámetro libre, no una lectura del
libro de órdenes, y quien lea «12 bps» tiene derecho a saberlo. Un número
estimado que se presenta como medido es peor que no tenerlo.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services.market_impact import (
    DEFAULT_LADDER, ImpactModel, average_daily_volume_usd, cost_ladder,
    daily_volatility_of, impact_bps,
)


def _daily(n=60, price=100.0, volume=1_000.0, seed=1, sigma=0.02):
    rng = np.random.default_rng(seed)
    close = price * np.exp(np.cumsum(rng.normal(0, sigma, n)))
    return pd.DataFrame({
        "timestamp": np.arange(n, dtype=np.int64) * 86_400_000,
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": np.full(n, volume),
    })


class TestLaFormaDelCoste:
    """
    La raíz cuadrada no es un detalle de implementación: es lo que dice que
    doblar el tamaño NO dobla el coste, y a la vez que el coste nunca deja de
    crecer — no hay un tamaño «gratis».
    """

    @pytest.mark.unit
    def test_cuadruplicar_el_tamano_dobla_el_coste(self):
        a = impact_bps(10_000, adv=1e8, daily_volatility=0.03)
        b = impact_bps(40_000, adv=1e8, daily_volatility=0.03)
        assert b / a == pytest.approx(2.0, rel=1e-6)

    @pytest.mark.unit
    def test_el_coste_nunca_se_estanca(self):
        """Un modelo lineal saturado diría que a partir de cierto tamaño da
        igual; este dice que siempre cuesta más, que es lo observado."""
        anterior = 0.0
        for notional in (1e3, 1e4, 1e5, 1e6, 1e7):
            actual = impact_bps(notional, adv=1e8, daily_volatility=0.03)
            assert actual > anterior
            anterior = actual

    @pytest.mark.unit
    def test_un_activo_mas_estrecho_cuesta_mas_al_mismo_tamano(self):
        estrecho = impact_bps(100_000, adv=1e6, daily_volatility=0.03)
        liquido = impact_bps(100_000, adv=1e9, daily_volatility=0.03)
        assert estrecho > liquido * 10

    @pytest.mark.unit
    def test_mas_volatilidad_encarece_la_ejecucion(self):
        calmado = impact_bps(100_000, adv=1e8, daily_volatility=0.01)
        agitado = impact_bps(100_000, adv=1e8, daily_volatility=0.06)
        assert agitado > calmado


class TestLaEscalera:

    @pytest.mark.unit
    def test_devuelve_un_escalon_por_tamano(self):
        out = cost_ladder(adv_usd=1e8, daily_volatility=0.03)
        assert [s["notional_usd"] for s in out["steps"]] == list(DEFAULT_LADDER)

    @pytest.mark.unit
    def test_cada_escalon_trae_el_coste_en_bps_y_en_dinero(self):
        """En bps se compara con el edge; en dinero se entiende. Hacen falta los
        dos: «12 bps» no le dice a nadie cuánto va a pagar."""
        out = cost_ladder(adv_usd=1e8, daily_volatility=0.03)
        paso = out["steps"][1]
        assert paso["impact_usd"] == pytest.approx(
            paso["impact_bps"] / 10_000 * paso["notional_usd"], rel=1e-6)

    @pytest.mark.unit
    def test_marca_lo_que_ya_no_es_ejecutable(self):
        """Por encima del 10 % del volumen diario la orden deja de poder
        ejecutarse en un día sin mover el mercado de forma evidente."""
        out = cost_ladder(adv_usd=1e6, daily_volatility=0.03)
        assert out["steps"][0]["feasible"]          # 1.000 sobre 1M = 0,1 %
        assert not out["steps"][-1]["feasible"]     # 1M sobre 1M = 100 %

    @pytest.mark.unit
    def test_da_el_techo_explicito_y_no_solo_la_escalera(self):
        """Es la cifra que convierte la tabla en una decisión: no «cuánto me
        cuesta» sino «hasta dónde puedo»."""
        out = cost_ladder(adv_usd=1e8, daily_volatility=0.03)
        assert out["max_executable_usd"] == pytest.approx(1e7)   # 10 % del ADV

    @pytest.mark.unit
    def test_el_techo_coincide_con_la_frontera_de_ejecutable(self):
        out = cost_ladder(adv_usd=5e6, daily_volatility=0.03,
                          notionals=(499_000.0, 501_000.0))
        assert out["steps"][0]["feasible"] and not out["steps"][1]["feasible"]

    @pytest.mark.unit
    def test_un_gamma_distinto_mueve_el_coste_proporcionalmente(self):
        """`gamma` es el único parámetro libre y está expuesto, no escondido:
        quien no se crea el 0,8 puede ver qué cambia."""
        base = cost_ladder(adv_usd=1e8, daily_volatility=0.03)
        doble = cost_ladder(adv_usd=1e8, daily_volatility=0.03,
                            model=ImpactModel(gamma=1.6))
        assert doble["steps"][0]["impact_bps"] == pytest.approx(
            base["steps"][0]["impact_bps"] * 2, rel=1e-6)


class TestNoFingeSaberLoQueNoSabe:
    """
    El modo de fallo caro de este módulo no es equivocarse en el número: es que
    alguien lea una estimación como una medición.
    """

    @pytest.mark.unit
    def test_sin_volumen_dice_que_no_puede_en_vez_de_devolver_cero(self):
        """Un cero se leería como «ejecutar aquí es gratis», que es lo contrario
        de la verdad: si no hay volumen, ejecutar es carísimo."""
        out = cost_ladder(adv_usd=0.0, daily_volatility=0.03)
        assert out["available"] is False and out["steps"] == []

    @pytest.mark.unit
    def test_sin_volatilidad_tampoco_inventa(self):
        out = cost_ladder(adv_usd=1e8, daily_volatility=0.0)
        assert out["available"] is False

    @pytest.mark.unit
    def test_declara_que_es_un_modelo_y_no_el_libro_de_ordenes(self):
        """La plataforma consulta profundidad en vivo pero no la archiva, así que
        no hay serie con la que medir esto hacia atrás. Decirlo es lo que separa
        una estimación auditable de un número que parece un dato."""
        out = cost_ladder(adv_usd=1e8, daily_volatility=0.03)
        assert out["method"] == "SQRT_IMPACT_MODEL"
        assert "libro de órdenes" in out["note"]

    @pytest.mark.unit
    def test_avisa_de_que_en_estres_sera_peor(self):
        out = cost_ladder(adv_usd=1e8, daily_volatility=0.03)
        assert "estrés" in out["note"]

    @pytest.mark.unit
    def test_expone_con_que_se_calibro(self):
        """Sin el ADV y la volatilidad de los que sale, el número no es
        reproducible por nadie."""
        out = cost_ladder(adv_usd=1.23e8, daily_volatility=0.0321)
        assert out["adv_usd"] == pytest.approx(1.23e8)
        assert out["daily_volatility"] == pytest.approx(0.0321)
        assert out["gamma"] == ImpactModel().gamma


class TestLaCalibracionDesdeElHistorico:

    @pytest.mark.unit
    def test_el_volumen_medio_sale_en_dinero_no_en_unidades(self):
        """Un ADV de «1.000 BTC» y otro de «1.000 DOGE» no son comparables; en
        USD sí, y es en USD como se compara contra el tamaño de una orden."""
        df = _daily(n=40, price=100.0, volume=1_000.0, sigma=0.0)
        assert average_daily_volume_usd(df, window=30) == pytest.approx(100_000.0)

    @pytest.mark.unit
    def test_la_volatilidad_se_mide_sobre_retornos(self):
        tranquilo = daily_volatility_of(_daily(seed=2, sigma=0.005), window=30)
        agitado = daily_volatility_of(_daily(seed=2, sigma=0.05), window=30)
        assert agitado > tranquilo * 5

    @pytest.mark.unit
    def test_un_historico_demasiado_corto_no_produce_volatilidad_inventada(self):
        assert daily_volatility_of(_daily(n=2), window=30) == 0.0

    @pytest.mark.unit
    def test_extremo_a_extremo_sobre_un_activo_sintetico(self):
        """Un activo con 100.000 USD/día de volumen: una orden de 10.000 es el
        10 % del mercado diario y tiene que salir marcada como el límite."""
        df = _daily(n=60, price=100.0, volume=1_000.0, sigma=0.03)
        out = cost_ladder(average_daily_volume_usd(df), daily_volatility_of(df))
        assert out["available"]
        assert out["max_executable_usd"] == pytest.approx(10_000.0, rel=0.05)
        assert not out["steps"][2]["feasible"]     # 100.000 sobre 100.000/día
