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
    DEPTH_2PCT_USD, DEPTH_REACH_PCT, LONG_SHORT_RATIO, OPEN_INTEREST_USD,
    TAKER_BUY_SELL_RATIO, IngestDerivativesUseCase, coverage, depth_within_band,
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
        assert depth_within_band(libro)["usd"] == pytest.approx(500.0 + 505.0)

    @pytest.mark.unit
    def test_suma_los_dos_lados(self):
        """La pregunta es cuánto aguanta antes de romperse, y eso no depende de
        la dirección."""
        libro = {"bids": [["100.0", "1"]], "asks": [["100.0", "1"]]}
        assert depth_within_band(libro)["usd"] == pytest.approx(200.0)

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
    # 5×3 series + alcance + profundidad: el alcance se archiva SIEMPRE.
    assert out["points_stored"] == 17
    assert set(out["metrics"]) == {OPEN_INTEREST_USD, LONG_SHORT_RATIO,
                                   TAKER_BUY_SELL_RATIO, DEPTH_2PCT_USD,
                                   DEPTH_REACH_PCT}
    assert DerivativeMetricPoint.objects.filter(symbol="BTC").count() == 17


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
    assert out["points_stored"] == 12          # 5×2 + alcance + profundidad


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


class TestLaTareaProgramada:
    """
    Sin tarea programada, la profundidad del libro no se recoge — y es la única
    de las cuatro series que no se puede recuperar hacia atrás. Estos tests fijan
    que la tarea existe, que está en el planificador y que un símbolo caído no se
    lleva por delante al resto.
    """

    @pytest.mark.integration
    def test_esta_en_el_planificador_de_celery(self, db):
        from django.conf import settings

        entrada = settings.CELERY_BEAT_SCHEDULE.get("sync-derivative-metrics")
        assert entrada is not None
        assert entrada["task"] == "core.tasks.sync_derivative_metrics"
        # La profundidad es una foto: con una cadencia larga se pierde resolución
        # que no se recupera. Cuarto de hora o menos.
        assert entrada["schedule"] <= 900.0

    @pytest.mark.integration
    def test_la_tarea_recoge_los_activos_del_almacen(self, db, monkeypatch):
        from core.infrastructure.persistence.models import CryptoAsset
        import core.application.use_cases.derivatives_store as ds
        from core.tasks import sync_derivative_metrics

        CryptoAsset.objects.create(symbol="BTC", name="Bitcoin", market_cap=1e12)
        CryptoAsset.objects.create(symbol="ETH", name="Ether", market_cap=5e11)
        monkeypatch.setattr(
            ds.IngestDerivativesUseCase, "execute",
            lambda self, symbol, **k: {"points_stored": 7, "symbol": symbol})

        out = sync_derivative_metrics()
        assert out["stored"] == 14
        assert set(out["by_symbol"]) == {"BTC", "ETH"}

    @pytest.mark.integration
    def test_un_simbolo_caido_no_frena_al_resto(self, db, monkeypatch):
        from core.infrastructure.persistence.models import CryptoAsset
        import core.application.use_cases.derivatives_store as ds
        from core.tasks import sync_derivative_metrics

        CryptoAsset.objects.create(symbol="BTC", name="Bitcoin", market_cap=1e12)
        CryptoAsset.objects.create(symbol="ETH", name="Ether", market_cap=5e11)

        def _falla_btc(self, symbol, **k):
            if symbol == "BTC":
                raise RuntimeError("API caída")
            return {"points_stored": 5, "symbol": symbol}

        monkeypatch.setattr(ds.IngestDerivativesUseCase, "execute", _falla_btc)
        out = sync_derivative_metrics()
        assert out["stored"] == 5
        assert "ETH" in out["by_symbol"] and "BTC" not in out["by_symbol"]


class TestLaProfundidadNoSeLlamaMasDeLoQueEs:
    """
    Esta serie se llamaba «profundidad a ±2 %» y no lo era: se pedía un libro de
    500 niveles y se sumaba lo que hubiera dentro de la banda SIN comprobar si el
    libro llegaba a la banda. Con tick de 0,1 en BTCUSDT, 500 niveles no cubren
    ±2 % casi nunca.

    Peor que el sesgo: el número no era comparable entre activos. Un símbolo de
    tick ancho agota sus niveles mucho más lejos del medio que uno de tick fino,
    así que el mismo valor significaba cosas distintas según el activo.

    Lo encontró la especificación de investigación (§8.1).
    """

    @staticmethod
    def _libro(alcance_pct: float, niveles: int = 50):
        """Libro que llega exactamente hasta `alcance_pct` a cada lado."""
        medio = 100.0
        paso = medio * (alcance_pct / 100.0) / niveles
        bids = [[f"{medio - paso * (i + 1):.6f}", "1"] for i in range(niveles)]
        asks = [[f"{medio + paso * (i + 1):.6f}", "1"] for i in range(niveles)]
        return {"bids": bids, "asks": asks}

    @pytest.mark.unit
    def test_declara_hasta_donde_llega_el_libro(self):
        out = depth_within_band(self._libro(alcance_pct=0.5))
        assert out["reach_pct"] == pytest.approx(0.5, abs=0.02)

    @pytest.mark.unit
    def test_un_libro_que_no_llega_a_la_banda_se_marca_como_no_cubierto(self):
        """El caso real de BTCUSDT: el libro pedido llega al 0,5 % y la banda
        pide el 2 %."""
        assert depth_within_band(self._libro(alcance_pct=0.5))["covered"] is False

    @pytest.mark.unit
    def test_uno_que_si_llega_se_marca_como_cubierto(self):
        assert depth_within_band(self._libro(alcance_pct=5.0))["covered"] is True

    @pytest.mark.unit
    def test_manda_el_lado_mas_corto(self):
        """Si el libro llega a −5 % pero solo a +0,3 %, la banda de ±2 % NO está
        cubierta: una orden de venta se quedaría sin contrapartida."""
        # Libro realista: pujas descendentes, ofertas ascendentes. Llega al 5 %
        # por abajo y solo al 0,3 % por arriba.
        libro = {"bids": [["99.9", "1"], ["95.0", "1"]],
                 "asks": [["100.1", "1"], ["100.3", "1"]]}
        out = depth_within_band(libro)
        assert out["reach_bid_pct"] > out["reach_ask_pct"]
        assert out["covered"] is False

    @pytest.mark.integration
    def test_un_libro_truncado_no_entra_en_la_serie_de_dos_por_ciento(self, db):
        """Mezclar un dato truncado con uno completo en la misma serie la hace
        inservible sin que nada falle de forma visible."""
        from core.infrastructure.persistence.models import DerivativeMetricPoint

        cliente = _ClienteFalso(n=3, libro=self._libro(alcance_pct=0.4))
        out = IngestDerivativesUseCase().execute("BTC", client=cliente)
        assert DEPTH_2PCT_USD in out["errors"]
        assert "truncado" in out["errors"][DEPTH_2PCT_USD]
        assert not DerivativeMetricPoint.objects.filter(metric=DEPTH_2PCT_USD).exists()

    @pytest.mark.integration
    def test_pero_el_alcance_si_se_archiva_siempre(self, db):
        """Es el único dato que permite saber si la profundidad de un día es
        comparable con la de otro, así que se guarda aunque la banda falle."""
        from core.infrastructure.persistence.models import DerivativeMetricPoint

        cliente = _ClienteFalso(n=3, libro=self._libro(alcance_pct=0.4))
        IngestDerivativesUseCase().execute("BTC", client=cliente)
        punto = DerivativeMetricPoint.objects.filter(metric=DEPTH_REACH_PCT).first()
        assert punto is not None and punto.value == pytest.approx(0.4, abs=0.02)

    @pytest.mark.integration
    def test_se_piden_los_mil_niveles_que_admite_el_endpoint(self, db):
        """Pedir 500 era la causa del truncado. Mil es el máximo del endpoint."""
        pedidos = {}

        class _Espia(_ClienteFalso):
            def order_book_depth(self, symbol, limit=500):
                pedidos["limit"] = limit
                return super().order_book_depth(symbol, limit)

        IngestDerivativesUseCase().execute("BTC", client=_Espia(n=3))
        assert pedidos["limit"] == 1000

    @pytest.mark.unit
    def test_un_libro_desordenado_no_produce_un_medio_equivocado(self):
        """Los exchanges lo devuelven ordenado, pero tomar el primer elemento
        hace que una fuente nueva con otro convenio dé un alcance equivocado sin
        que nada falle."""
        ordenado = {"bids": [["99.9", "1"], ["95.0", "1"]],
                    "asks": [["100.1", "1"], ["105.0", "1"]]}
        revuelto = {"bids": [["95.0", "1"], ["99.9", "1"]],
                    "asks": [["105.0", "1"], ["100.1", "1"]]}
        assert (depth_within_band(ordenado)["reach_pct"]
                == pytest.approx(depth_within_band(revuelto)["reach_pct"]))
