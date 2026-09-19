"""
tests/integration/test_derivatives_store.py — Archivar lo que solo existía como
«ahora mismo».

Cuatro series que la plataforma sabía leer y no guardaba. Lo que estos tests
fijan no es que se lean —eso lo hace el cliente— sino las tres propiedades que
hacen que lo archivado sirva para algo meses después:

  · **idempotencia**, porque si reejecutar duplica, nadie rellena huecos;
  · **aislamiento entre fuentes**, porque una API caída no puede llevarse por
    delante a las otras tres;
  · **cobertura declarada**, porque una métrica sin datos y una métrica sin
    importancia llevan a conclusiones opuestas y hay que poder distinguirlas.

Se usa un cliente de mentira. Aquí no se prueba Binance: se prueba qué hace este
módulo con lo que Binance devuelva, incluido cuando no devuelve nada.
"""

import pytest

from core.application.use_cases.derivatives_store import (
    DEPTH_2PCT_USD, LONG_SHORT_RATIO, OPEN_INTEREST_USD, TAKER_BUY_SELL_RATIO,
    IngestDerivativesUseCase, coverage, depth_within_band,
)


class _ClienteFalso:
    """Devuelve series fijas; puede fallar en las fuentes que se le indiquen."""

    def __init__(self, n=5, falla=(), libro=None, base_ms=1_700_000_000_000):
        self.n, self.falla, self.base = n, set(falla), base_ms
        self.libro = libro if libro is not None else {
            "bids": [["100.0", "5"], ["99.0", "5"], ["50.0", "100"]],
            "asks": [["101.0", "5"], ["102.0", "5"], ["200.0", "100"]],
        }

    def _serie(self, metrica, campo, valor0):
        if metrica in self.falla:
            raise RuntimeError("fuente caída")
        return [{"timestamp": self.base + i * 3_600_000, campo: str(valor0 + i)}
                for i in range(self.n)]

    def open_interest_history(self, symbol, period="1h", limit=500):
        return self._serie(OPEN_INTEREST_USD, "sumOpenInterestValue", 1_000_000)

    def long_short_ratio_history(self, symbol, period="1h", limit=500):
        return self._serie(LONG_SHORT_RATIO, "longShortRatio", 1)

    def taker_buy_sell_history(self, symbol, period="1h", limit=500):
        return self._serie(TAKER_BUY_SELL_RATIO, "buySellRatio", 1)

    def order_book_depth(self, symbol, limit=500):
        if DEPTH_2PCT_USD in self.falla:
            raise RuntimeError("fuente caída")
        return self.libro


class TestLaProfundidadDelLibro:

    @pytest.mark.unit
    def test_solo_cuenta_lo_que_esta_dentro_de_la_banda(self):
        """Los niveles a 50 y 200 están fuera del ±2 % y no deben sumar: contarlos
        diría que el libro aguanta un dinero que en un susto no está."""
        libro = {"bids": [["100.0", "5"], ["50.0", "100"]],
                 "asks": [["101.0", "5"], ["200.0", "100"]]}
        # medio = 100.5; banda = [98.49, 102.51] → solo 100×5 y 101×5
        assert depth_within_band(libro) == pytest.approx(500.0 + 505.0)

    @pytest.mark.unit
    def test_suma_los_dos_lados(self):
        """La pregunta es cuánto aguanta antes de romperse, y eso no depende de
        la dirección."""
        libro = {"bids": [["100.0", "1"]], "asks": [["100.0", "1"]]}
        assert depth_within_band(libro) == pytest.approx(200.0)

    @pytest.mark.unit
    def test_un_libro_vacio_devuelve_none_y_no_cero(self):
        """Cero significaría «no hay liquidez», que es muy distinto de «no he
        podido mirar»."""
        assert depth_within_band({"bids": [], "asks": []}) is None
        assert depth_within_band({}) is None

    @pytest.mark.unit
    def test_un_libro_malformado_no_revienta(self):
        assert depth_within_band({"bids": [["x", "y"]], "asks": [["1", "1"]]}) is None


@pytest.mark.integration
def test_archiva_las_cuatro_series(db):
    from core.infrastructure.persistence.models import DerivativeMetricPoint

    out = IngestDerivativesUseCase().execute("BTC", client=_ClienteFalso(n=5))
    assert out["points_stored"] == 16          # 5×3 series + 1 foto de profundidad
    assert set(out["metrics"]) == {OPEN_INTEREST_USD, LONG_SHORT_RATIO,
                                   TAKER_BUY_SELL_RATIO, DEPTH_2PCT_USD}
    assert DerivativeMetricPoint.objects.filter(symbol="BTC").count() == 16


@pytest.mark.integration
def test_reejecutar_no_duplica(db):
    """Si reejecutar duplicara, nadie rellenaría huecos — y los huecos son el
    estado normal de cualquier ingesta real."""
    from core.infrastructure.persistence.models import DerivativeMetricPoint

    cliente = _ClienteFalso(n=5)
    IngestDerivativesUseCase().execute("BTC", client=cliente)
    antes = DerivativeMetricPoint.objects.filter(metric=OPEN_INTEREST_USD).count()
    IngestDerivativesUseCase().execute("BTC", client=cliente)
    despues = DerivativeMetricPoint.objects.filter(metric=OPEN_INTEREST_USD).count()
    assert antes == despues == 5


@pytest.mark.integration
def test_una_fuente_caida_no_se_lleva_a_las_demas(db):
    """El modo de fallo real: tres endpoints responden y uno no."""
    out = IngestDerivativesUseCase().execute(
        "BTC", client=_ClienteFalso(n=5, falla=(LONG_SHORT_RATIO,)))
    assert LONG_SHORT_RATIO in out["errors"]
    assert OPEN_INTEREST_USD in out["metrics"]
    assert out["points_stored"] == 11          # 5×2 + profundidad


@pytest.mark.integration
def test_si_todo_falla_lo_dice_y_no_escribe_nada(db):
    out = IngestDerivativesUseCase().execute(
        "BTC", client=_ClienteFalso(falla=(OPEN_INTEREST_USD, LONG_SHORT_RATIO,
                                           TAKER_BUY_SELL_RATIO, DEPTH_2PCT_USD)))
    assert out["points_stored"] == 0
    assert len(out["errors"]) == 4


@pytest.mark.integration
def test_el_interes_abierto_se_guarda_en_dinero_no_en_contratos(db):
    """Los contratos no son comparables entre activos ni en el tiempo si el
    contrato se redefine; el nocional sí."""
    from core.infrastructure.persistence.models import DerivativeMetricPoint

    IngestDerivativesUseCase().execute("BTC", client=_ClienteFalso(n=3))
    valores = list(DerivativeMetricPoint.objects
                   .filter(metric=OPEN_INTEREST_USD).order_by("observed_at")
                   .values_list("value", flat=True))
    assert valores == [1_000_000.0, 1_000_001.0, 1_000_002.0]


@pytest.mark.integration
def test_el_venue_forma_parte_de_la_clave(db):
    """El funding y el posicionamiento de Binance y Bybit difieren en el mismo
    instante, y esa diferencia ES la oportunidad de dislocación: mezclarlos en
    una sola serie la borraría."""
    from core.infrastructure.persistence.models import DerivativeMetricPoint

    cliente = _ClienteFalso(n=4)
    IngestDerivativesUseCase().execute("BTC", venue="binance", client=cliente)
    IngestDerivativesUseCase().execute("BTC", venue="bybit", client=cliente)
    assert DerivativeMetricPoint.objects.filter(
        symbol="BTC", metric=OPEN_INTEREST_USD).count() == 8


@pytest.mark.integration
def test_guarda_cuando_el_valor_era_cierto_y_cuando_se_escribio(db):
    """Sin esa pareja no se puede auditar después que un estudio no usó
    información que en su momento no existía."""
    from core.infrastructure.persistence.models import DerivativeMetricPoint

    IngestDerivativesUseCase().execute("BTC", client=_ClienteFalso(n=2))
    punto = DerivativeMetricPoint.objects.filter(metric=OPEN_INTEREST_USD).first()
    assert punto.observed_at == 1_700_000_000_000
    assert punto.created_at is not None


class TestLaCobertura:

    @pytest.mark.integration
    def test_distingue_no_recogido_de_recogido_sin_valor(self, db):
        """Es la distinción que impide confundir «esta métrica no aporta» con
        «esta métrica no se ha medido»."""
        IngestDerivativesUseCase().execute(
            "BTC", client=_ClienteFalso(n=5, falla=(TAKER_BUY_SELL_RATIO,)))
        cob = coverage("BTC")["metrics"]
        assert cob[OPEN_INTEREST_USD]["available"] is True
        assert cob[TAKER_BUY_SELL_RATIO]["available"] is False
        assert "No se ha recogido" in cob[TAKER_BUY_SELL_RATIO]["note"]

    @pytest.mark.integration
    def test_declara_el_tramo_cubierto(self, db):
        IngestDerivativesUseCase().execute("BTC", client=_ClienteFalso(n=25))
        cob = coverage("BTC")["metrics"][OPEN_INTEREST_USD]
        assert cob["points"] == 25
        assert cob["span_days"] == pytest.approx(1.0, abs=0.01)   # 24 h de paso

    @pytest.mark.integration
    def test_sin_nada_recogido_no_revienta(self, db):
        cob = coverage("XYZ")["metrics"]
        assert all(not m["available"] for m in cob.values())


class TestElComandoDeIngesta:

    @staticmethod
    def _run(*args, **kwargs):
        from io import StringIO

        from django.core.management import call_command
        out = StringIO()
        call_command("ingest_derivatives", *args, stdout=out, stderr=out, **kwargs)
        return out.getvalue()

    @pytest.mark.integration
    def test_la_cobertura_se_puede_consultar_sin_traer_nada(self, db):
        """Es el modo que se usa para saber si merece la pena estudiar algo."""
        salida = self._run("BTC", "--coverage")
        assert "No se ha recogido" in salida

    @pytest.mark.integration
    def test_informa_de_las_fuentes_caidas_en_vez_de_callarlas(self, db, monkeypatch):
        """Una ingesta silenciosamente incompleta es peor que una que falla: deja
        huecos que nadie sabe que hay que rellenar."""
        import core.application.use_cases.derivatives_store as ds

        monkeypatch.setattr(
            ds.IngestDerivativesUseCase, "execute",
            lambda self, *a, **k: {"symbol": "BTC", "venue": "binance",
                                   "points_stored": 0, "metrics": [],
                                   "errors": {"open_interest_usd": "Timeout"},
                                   "note": "0 puntos nuevos de 0 traídos."})
        assert "sin datos de open_interest_usd" in self._run("BTC")
