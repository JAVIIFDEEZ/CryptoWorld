"""
tests/integration/test_carry_test.py — El carry contra el almacén real.

Lo que se prueba aquí no es la aritmética —eso vive en los tests de dominio—
sino lo que solo se puede romper con base de datos delante: que el corte
temporal use la unidad correcta, que un activo sin histórico lo diga en vez de
emitir un veredicto, y que el informe impreso no reviente en ninguna de sus
ramas.

El corte temporal merece su propio test. `funding_time` se guarda como epoch en
milisegundos, no como fecha: pasar un `datetime` a ese campo no falla de forma
visible, compara mal y devuelve de menos. Un tramo recortado en silencio daría un
veredicto sobre menos historia de la que hay, que es el peor tipo de error aquí
porque parece un resultado.
"""

from datetime import datetime, timedelta, timezone as _tz
from io import StringIO

import numpy as np
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def _ms(dt) -> int:
    return int(dt.timestamp() * 1000)


def _sembrar(symbol="BTCUSDT", n=1095, media=0.0001, ruido=0.0, seed=1,
             hasta=None, paso_horas=8):
    """Siembra `n` liquidaciones de financiación hacia atrás desde `hasta`."""
    from core.infrastructure.persistence.models import FundingRateRecord

    rng = np.random.default_rng(seed)
    fin = hasta or datetime.now(_tz.utc)
    filas = []
    for i in range(n):
        # `n - 1 - i`: la más reciente cae en `hasta` y la más antigua a
        # 8 h × (n−1). Con `n - i` la más antigua caería exactamente en el borde
        # de una ventana de un año y entraría o no según los microsegundos.
        momento = fin - timedelta(hours=paso_horas * (n - 1 - i))
        filas.append(FundingRateRecord(
            symbol=symbol, funding_time=_ms(momento),
            funding_rate=float(rng.normal(media, ruido)) if ruido else media,
            interval_hours=paso_horas, source="test",
        ))
    FundingRateRecord.objects.bulk_create(filas)


@pytest.mark.integration
def test_sin_historico_lo_dice_en_vez_de_emitir_veredicto(db):
    """No es lo mismo «el carry no compensa» que «no hay datos para saberlo»."""
    from core.application.use_cases.carry_test import CarryTestUseCase

    out = CarryTestUseCase().execute("BTC")
    assert out["verdict"] == "SIN_DATOS"
    assert out["tradeable"] is False
    assert out["funding_coverage"]["available"] is False


@pytest.mark.integration
def test_un_ano_de_funding_positivo_sale_operable(db):
    from core.application.use_cases.carry_test import CarryTestUseCase

    _sembrar(n=1095, media=0.0001)
    out = CarryTestUseCase().execute("BTC")
    assert out["verdict"] == "OPERABLE"
    assert out["observed"]["periods"] == 1095
    assert out["observed"]["net_annualized_pct"] > 5


@pytest.mark.integration
def test_un_funding_negativo_sostenido_no_sale_operable(db):
    """El riesgo real del carry: el flujo cambia de sentido."""
    from core.application.use_cases.carry_test import CarryTestUseCase

    _sembrar(n=1095, media=-0.0001)
    out = CarryTestUseCase().execute("BTC")
    assert out["tradeable"] is False
    assert out["verdict"] == "NO_CUBRE_COSTES"


@pytest.mark.integration
def test_el_corte_temporal_usa_milisegundos_y_no_recorta_de_mas(db):
    """La mitad del histórico queda fuera de la ventana de 100 días y la otra
    dentro; si el corte se hiciera con una fecha contra un entero, el filtro
    devolvería de menos sin avisar."""
    from core.application.use_cases.carry_test import CarryTestUseCase

    ahora = datetime.now(_tz.utc)
    _sembrar(n=60, media=0.0001, hasta=ahora)                      # ~20 días
    _sembrar(n=60, media=0.0001, hasta=ahora - timedelta(days=300))  # muy antiguo

    reciente = CarryTestUseCase().execute("BTC", days=100)
    todo = CarryTestUseCase().execute("BTC", days=400)
    assert reciente["observed"]["periods"] == 60
    assert todo["observed"]["periods"] == 120


@pytest.mark.integration
def test_el_simbolo_se_normaliza_al_par_del_perpetuo(db):
    """El almacén guarda BTCUSDT; el usuario escribe BTC."""
    from core.application.use_cases.carry_test import CarryTestUseCase

    _sembrar(symbol="BTCUSDT", n=400, media=0.0001)
    assert CarryTestUseCase().execute("btc")["observed"]["periods"] == 400


@pytest.mark.integration
def test_no_mezcla_activos(db):
    from core.application.use_cases.carry_test import CarryTestUseCase

    _sembrar(symbol="BTCUSDT", n=400, media=0.0001)
    _sembrar(symbol="ETHUSDT", n=200, media=0.0001)
    assert CarryTestUseCase().execute("ETH")["observed"]["periods"] == 200


@pytest.mark.integration
def test_la_cobertura_declara_el_tramo_cubierto(db):
    """Sin ella no se puede distinguir «un año de evidencia» de «tres semanas»."""
    from core.application.use_cases.carry_test import CarryTestUseCase

    _sembrar(n=500, media=0.0001)
    cobertura = CarryTestUseCase().execute("BTC")["funding_coverage"]
    assert cobertura["periods"] == 500
    assert cobertura["first"] < cobertura["last"]


class TestElComando:

    @staticmethod
    def _run(*args, **kwargs):
        out = StringIO()
        call_command("carry_test", *args, stdout=out, stderr=out, **kwargs)
        return out.getvalue()

    @pytest.mark.integration
    def test_imprime_el_veredicto_y_el_desglose(self, db):
        _sembrar(n=1095, media=0.0001)
        salida = self._run("BTC")
        assert "OPERABLE" in salida
        assert "comisiones (4 órdenes)" in salida
        assert "CONTRA EL NULO" in salida

    @pytest.mark.integration
    def test_el_protocolo_viaja_con_el_resultado(self, db):
        _sembrar(n=1095, media=0.0001)
        salida = self._run("BTC")
        assert "CUATRO comisiones" in salida
        assert "percentil 95" in salida

    @pytest.mark.integration
    def test_la_rama_sin_datos_tambien_se_imprime(self, db):
        """Es la que más veces se va a ver el primer día y la que reventaría sin
        que nadie lo hubiera probado."""
        salida = self._run("BTC")
        assert "SIN_DATOS" in salida

    @pytest.mark.integration
    def test_el_json_es_parseable_y_completo(self, db):
        import json

        _sembrar(n=1095, media=0.0001)
        datos = json.loads(self._run("BTC", "--json"))
        assert datos[0]["verdict"] == "OPERABLE"
        assert "null" in datos[0] and "observed" in datos[0]

    @pytest.mark.integration
    def test_un_margen_imposible_se_rechaza(self, db):
        with pytest.raises(CommandError):
            self._run("BTC", "--margin", "1.5")

    @pytest.mark.integration
    def test_un_nocional_no_positivo_se_rechaza(self, db):
        with pytest.raises(CommandError):
            self._run("BTC", "--notional", "0")

    @pytest.mark.integration
    def test_menos_margen_puede_cambiar_el_veredicto(self, db):
        """Mismo funding, mismo coste: lo único que cambia es el apalancamiento,
        y con él si un shock del 15 % deja viva la posición."""
        _sembrar(n=1095, media=0.0001)
        holgado = self._run("BTC", "--margin", "0.30")
        ajustado = self._run("BTC", "--margin", "0.10")
        assert "OPERABLE" in holgado
        assert "RIESGO_DE_LIQUIDACION" in ajustado
