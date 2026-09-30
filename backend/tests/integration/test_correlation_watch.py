"""
tests/integration/test_correlation_watch.py — La vigilancia contra el almacén real.

Lo que se prueba aquí no es el detector —eso vive en los tests de dominio— sino
lo que solo se puede romper con base de datos delante:

· que las dos series se UNAN por marca temporal y no se emparejen por posición,
  que es el fallo que convertiría una correlación de 0,85 en una de 0,2 sin que
  nada avisara;
· que los índices internos del detector vuelvan a ser fechas correctas después de
  pasar por el cebado de la volatilidad, la ventana móvil y el corte de
  referencia;
· que un activo sin histórico lo diga en vez de emitir un veredicto;
· que el informe impreso no reviente en ninguna de sus ramas, incluida la que se
  verá el primer día.

El test de la unión temporal es el que justifica el fichero. `load_dataframe`
devuelve las últimas N velas de cada símbolo por separado, y en este mismo
almacén hay un `find_gaps` porque faltan velas. Emparejar por posición dos series
con huecos distintos desfasa una respecto a la otra y la cantidad medida deja de
ser una correlación.
"""

from datetime import datetime, timedelta, timezone as _tz
from io import StringIO

import numpy as np
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


HORA_MS = 3_600_000


def _sembrar_par(simbolo_a="BTC", simbolo_b="ETH", n=1600, rho=0.80,
                 rho2=None, corte=None, interval="1h", seed=1,
                 saltar_en_b=(), base_ms=None):
    """Siembra dos series de velas correlacionadas en el almacén.

    `saltar_en_b` omite esas posiciones SOLO en la segunda serie: es como se
    reproduce un hueco real del almacén y se comprueba que la unión temporal lo
    absorbe en vez de desfasar.
    """
    from core.infrastructure.persistence.models import OhlcvCandle

    rng = np.random.default_rng(seed)
    e1 = rng.standard_normal(n)
    e2 = rng.standard_normal(n)
    r = np.full(n, float(rho))
    if rho2 is not None and corte is not None:
        r[corte:] = float(rho2)
    ra = e1 * 0.02
    rb = (r * e1 + np.sqrt(np.maximum(1.0 - r ** 2, 0.0)) * e2) * 0.02

    inicio = base_ms if base_ms is not None else int(
        (datetime.now(_tz.utc) - timedelta(hours=n + 1)).timestamp() * 1000)
    ca = 30_000.0 * np.exp(np.cumsum(ra))
    cb = 2_000.0 * np.exp(np.cumsum(rb))

    filas = []
    for i in range(n):
        t = inicio + i * HORA_MS
        filas.append(OhlcvCandle(symbol=simbolo_a, interval=interval, open_time=t,
                                 open=ca[i], high=ca[i], low=ca[i], close=ca[i],
                                 volume=1.0, source="test"))
        if i not in saltar_en_b:
            filas.append(OhlcvCandle(symbol=simbolo_b, interval=interval, open_time=t,
                                     open=cb[i], high=cb[i], low=cb[i], close=cb[i],
                                     volume=1.0, source="test"))
    OhlcvCandle.objects.bulk_create(filas)
    return inicio


# ------------------------------------------------------------------ la unión


@pytest.mark.integration
def test_las_series_se_unen_por_marca_temporal_y_no_por_posicion(db):
    """El fallo que este fichero existe para impedir.

    A la segunda serie le faltan velas en mitad del histórico. Si el emparejado
    fuera por posición, todo lo posterior al primer hueco quedaría desfasado y la
    correlación medida se hundiría. Con unión por marca temporal, la correlación
    de referencia sigue siendo la plantada.
    """
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    huecos = tuple(range(700, 760))
    _sembrar_par(n=1600, rho=0.85, saltar_en_b=huecos)

    out = CorrelationWatchUseCase().execute(["BTC", "ETH"], replicates=60)
    assert out["candles_aligned"] == 1600 - len(huecos)
    pareja = out["pairs"][0]
    assert pareja["verdict"] in ("ESTABLE", "ROTO")
    # La correlación plantada sobrevive a la unión. Con emparejado por posición
    # el tramo posterior al hueco entraría desfasado y esto bajaría de 0,3.
    assert pareja["reference_corr"] > 0.70


@pytest.mark.integration
def test_un_activo_sin_histórico_se_declara_y_no_hunde_el_resto(db):
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    _sembrar_par(n=1600, rho=0.80)
    out = CorrelationWatchUseCase().execute(["BTC", "ETH", "DOGE"], replicates=60)
    assert "DOGE" in out["missing"]
    assert out["symbols"] == ["BTC", "ETH"]
    assert out["pairs_evaluated"] == 1


@pytest.mark.integration
def test_sin_almacen_lo_dice_en_vez_de_emitir_veredicto(db):
    """«No hay datos para saberlo» no es «la correlación aguanta»."""
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    out = CorrelationWatchUseCase().execute(["BTC", "ETH"])
    assert out["verdict"] == "SIN_DATOS"
    assert out["pairs"] == []


@pytest.mark.integration
def test_un_solo_activo_no_es_una_correlacion(db):
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    assert CorrelationWatchUseCase().execute(["BTC"])["verdict"] == "SIN_DATOS"


@pytest.mark.integration
def test_no_mezcla_marcos_temporales(db):
    """Velas de 1h y de 4h del mismo activo no son la misma serie."""
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    _sembrar_par(n=1600, rho=0.80, interval="1h")
    out = CorrelationWatchUseCase().execute(["BTC", "ETH"], interval="4h")
    assert out["verdict"] == "SIN_DATOS"


# --------------------------------------------------------------- el veredicto


@pytest.mark.integration
def test_una_correlacion_estable_sale_estable(db):
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    _sembrar_par(n=1800, rho=0.80, seed=5)
    out = CorrelationWatchUseCase().execute(["BTC", "ETH"], replicates=200)
    assert out["verdict"] == "ESTABLE"
    assert out["pairs_broken"] == 0


@pytest.mark.integration
def test_una_ruptura_plantada_se_detecta_y_se_fecha(db):
    """El caso completo: la ruptura se detecta Y el informe la sitúa en el tiempo.

    La fecha es la mitad del producto. Un aviso sin fecha no se puede cruzar con
    lo que pasó en el mercado, y sin ese cruce no se puede decidir si la ruptura
    es estructural o fue un día raro.
    """
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    inicio = _sembrar_par(n=1800, rho=0.85, rho2=0.20, corte=1100, seed=6)
    out = CorrelationWatchUseCase().execute(["BTC", "ETH"], replicates=200)

    pareja = out["pairs"][0]
    assert pareja["broken"] is True
    assert out["verdict"] in ("ROTO", "INDICIOS")

    momento_real = datetime.fromtimestamp((inicio + 1100 * HORA_MS) / 1000, _tz.utc)
    alarma = datetime.fromisoformat(pareja["alarm_time"])
    # La alarma llega DESPUÉS de la ruptura —es un detector, no un oráculo— y no
    # más de unos cientos de barras después, que es lo medido en el laboratorio.
    assert alarma > momento_real
    assert (alarma - momento_real) < timedelta(hours=400)


@pytest.mark.integration
def test_las_fechas_caen_dentro_del_histórico_sembrado(db):
    """Tres cambios de coordenadas encadenados —cebado, ventana, referencia— y
    cada uno se equivocó una vez al escribirlo. Si la traducción se desmadra, las
    fechas se salen del tramo que existe."""
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    inicio = _sembrar_par(n=1800, rho=0.85, rho2=0.20, corte=1100, seed=7)
    fin = inicio + 1799 * HORA_MS
    pareja = CorrelationWatchUseCase().execute(["BTC", "ETH"], replicates=150)["pairs"][0]
    assert pareja["broken"] is True
    for clave in ("alarm_time", "change_point_time"):
        t = datetime.fromisoformat(pareja[clave]).timestamp() * 1000
        assert inicio <= t <= fin, f"{clave} fuera del histórico"
    # El punto de cambio no puede ir por delante de su propia alarma.
    assert pareja["change_point_time"] <= pareja["alarm_time"]


@pytest.mark.integration
def test_dos_ejecuciones_seguidas_dan_el_mismo_umbral(db):
    """Reproducibilidad, que en un informe que puede recortar una posición no es
    una comodidad.

    La semilla de cada pareja se derivaba de `hash()` de su nombre, y el hash de
    una cadena en Python va salado por proceso: la misma pareja sobre los mismos
    datos calibraba un umbral distinto en cada ejecución, y dos ejecuciones
    seguidas podían dar veredictos opuestos sin que nada hubiera cambiado. Este
    test no lo detectaría dentro de un solo proceso —el salt es fijo mientras
    corre—, así que comprueba lo que sí puede: que la semilla sea función pura del
    nombre y no dependa del estado del intérprete.
    """
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    _sembrar_par(n=1600, rho=0.80, seed=16)
    uc = CorrelationWatchUseCase()
    assert uc._seed("BTC", "ETH") == uc._seed("BTC", "ETH")
    assert uc._seed("BTC", "ETH") != uc._seed("ETH", "BTC")
    # Y el valor concreto queda fijado: si alguien cambia la derivación, los
    # umbrales de todos los informes anteriores dejan de ser reproducibles.
    from zlib import crc32
    assert uc._seed("BTC", "ETH") == crc32(b"BTC/ETH") & 0x7FFFFFFF

    primero = uc.execute(["BTC", "ETH"], replicates=60)["pairs"][0]
    segundo = uc.execute(["BTC", "ETH"], replicates=60)["pairs"][0]
    assert primero["threshold"] == segundo["threshold"]
    assert primero["verdict"] == segundo["verdict"]


@pytest.mark.integration
def test_el_informe_declara_cuantas_parejas_se_miraron(db):
    """Tres activos son tres contrastes. Quedarse con el que saltó sin decir
    cuántos se miraron es el defecto clásico de las pruebas múltiples."""
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    # Las dos parejas se siembran sobre la MISMA rejilla temporal para que la
    # unión no descarte nada y las seis combinaciones sean evaluables.
    base = int((datetime.now(_tz.utc) - timedelta(hours=1601)).timestamp() * 1000)
    _sembrar_par("BTC", "ETH", n=1600, rho=0.80, seed=8, base_ms=base)
    _sembrar_par("SOL", "ADA", n=1600, rho=0.60, seed=9, base_ms=base)

    out = CorrelationWatchUseCase().execute(["BTC", "ETH", "SOL", "ADA"],
                                            replicates=60)
    assert out["pairs_evaluated"] == 6          # 4 activos → 6 parejas
    assert out["expected_by_chance"] == pytest.approx(0.05 * 6)
    assert len(out["pairs"]) == 6


@pytest.mark.integration
def test_el_reparto_familiar_endurece_cada_pareja(db):
    """Con α repartido, cada pareja se juzga a α/m y el umbral de cada una SUBE.

    Es la contrapartida que hay que poder ver: el reparto compra una garantía
    sobre la cartera completa y la paga en potencia.
    """
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    base = int((datetime.now(_tz.utc) - timedelta(hours=1801)).timestamp() * 1000)
    _sembrar_par("BTC", "ETH", n=1800, rho=0.80, seed=17, base_ms=base)
    _sembrar_par("SOL", "ADA", n=1800, rho=0.60, seed=18, base_ms=base)
    uc = CorrelationWatchUseCase()

    suelto = uc.execute(["BTC", "ETH", "SOL", "ADA"], replicates=200)
    familiar = uc.execute(["BTC", "ETH", "SOL", "ADA"], replicates=200,
                          family_wise=True)

    assert suelto["family_wise"] is False
    assert familiar["family_wise"] is True
    assert familiar["alpha_per_pair"] == pytest.approx(0.05 / 6)
    assert suelto["alpha_per_pair"] == pytest.approx(0.05)

    por_nombre = {p["pair"]: p for p in suelto["pairs"]}
    for p in familiar["pairs"]:
        if p.get("threshold") and por_nombre[p["pair"]].get("threshold"):
            assert p["threshold"] >= por_nombre[p["pair"]]["threshold"]


@pytest.mark.integration
def test_el_mismo_activo_en_distinta_caja_no_cuenta_como_dos(db):
    """«btc» y «BTC» son un activo. Con el deduplicado antes de mayúsculas, los
    dos pasaban el filtro de «al menos dos» siendo uno solo."""
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    _sembrar_par(n=1600, rho=0.80, seed=19)
    out = CorrelationWatchUseCase().execute(["btc", "BTC"], replicates=60)
    assert out["verdict"] == "SIN_DATOS"
    assert out["pairs"] == []


@pytest.mark.integration
def test_una_sola_pareja_rota_de_seis_no_es_un_hallazgo(db):
    """El defecto que este test fija.

    El veredicto agregado comparaba las roturas con la media esperada: con seis
    parejas al 5 %, una sola rotura (esperadas 0,3) salía ROTO. Pero una rotura
    entre seis contrastes al 5 % ocurre el 26 % de las veces sin que nada haya
    cambiado. Ahora se contrasta contra la cola binomial y sale INDICIOS.
    """
    from core.application.use_cases.correlation_watch import CorrelationWatchUseCase

    uc = CorrelationWatchUseCase()
    # La aritmética, aislada: es la que decide el veredicto.
    assert uc._binomial_tail(1, 6, 0.05) == pytest.approx(0.2649, abs=1e-3)
    assert uc._verdict(["x"] * 6, ["x"], 0.05) == "INDICIOS"
    assert uc._verdict(["x"] * 6, ["x", "x"], 0.05) == "ROTO"
    # Con el α repartido, una sola rotura sí es significativa: para eso sirve.
    assert uc._verdict(["x"] * 6, ["x"], 0.05 / 6) == "ROTO"

    base = int((datetime.now(_tz.utc) - timedelta(hours=1701)).timestamp() * 1000)
    _sembrar_par("BTC", "ETH", n=1700, rho=0.80, rho2=0.20, corte=1000, seed=10,
                 base_ms=base)
    _sembrar_par("SOL", "ADA", n=1700, rho=0.60, seed=11, base_ms=base)
    out = uc.execute(["BTC", "ETH", "SOL", "ADA"], replicates=60)
    assert out["chance_of_this_many"] is not None
    if out["pairs_broken"] == 1:
        assert out["verdict"] == "INDICIOS"


# ----------------------------------------------------------------- el comando


class TestElComando:

    @staticmethod
    def _run(*args, **kwargs):
        out = StringIO()
        call_command("correlation_watch", *args, stdout=out, stderr=out, **kwargs)
        return out.getvalue()

    @pytest.mark.integration
    def test_imprime_el_veredicto_y_las_parejas(self, db):
        _sembrar_par(n=1800, rho=0.80, seed=12)
        salida = self._run("BTC", "ETH", "--replicates", "60")
        assert "BTC/ETH" in salida
        assert "VEREDICTO" in salida
        assert "PROTOCOLO" in salida

    @pytest.mark.integration
    def test_la_nota_de_limitaciones_viaja_con_el_resultado(self, db):
        """Lo que el detector NO ve tiene que llegar junto al veredicto, no en un
        documento aparte que nadie abre."""
        _sembrar_par(n=1800, rho=0.80, seed=13)
        salida = self._run("BTC", "ETH", "--replicates", "60")
        assert "DESPLAZAMIENTO DE NIVEL" in salida

    @pytest.mark.integration
    def test_una_ruptura_imprime_la_fecha_y_la_advertencia(self, db):
        _sembrar_par(n=1800, rho=0.85, rho2=0.20, corte=1100, seed=14)
        salida = self._run("BTC", "ETH", "--replicates", "150")
        assert "punto de cambio estimado" in salida
        assert "TARDE" in salida

    @pytest.mark.integration
    def test_la_rama_sin_datos_tambien_se_imprime(self, db):
        """La que más veces se va a ver el primer día y la que reventaría sin que
        nadie la hubiera probado."""
        assert "SIN_DATOS" in self._run("BTC", "ETH")

    @pytest.mark.integration
    def test_el_json_es_parseable_y_completo(self, db):
        import json

        _sembrar_par(n=1800, rho=0.80, seed=15)
        datos = json.loads(self._run("BTC", "ETH", "--json", "--replicates", "60"))
        assert datos["verdict"] in ("ESTABLE", "ROTO", "INDICIOS")
        assert "pairs" in datos and "protocol" in datos

    @pytest.mark.integration
    def test_un_solo_activo_se_rechaza(self, db):
        with pytest.raises(CommandError):
            self._run("BTC")

    @pytest.mark.integration
    def test_un_alfa_imposible_se_rechaza(self, db):
        with pytest.raises(CommandError):
            self._run("BTC", "ETH", "--alpha", "0.9")

    @pytest.mark.integration
    def test_una_ventana_demasiado_corta_se_rechaza(self, db):
        with pytest.raises(CommandError):
            self._run("BTC", "ETH", "--window", "3")

    @pytest.mark.integration
    def test_pocas_replicas_se_rechazan(self, db):
        """Un umbral calibrado con diez réplicas es peor que no dar umbral."""
        with pytest.raises(CommandError):
            self._run("BTC", "ETH", "--replicates", "5")

    @pytest.mark.integration
    def test_una_caida_objetivo_imposible_se_rechaza(self, db):
        with pytest.raises(CommandError):
            self._run("BTC", "ETH", "--drop", "0")

    @pytest.mark.integration
    def test_el_reparto_familiar_se_imprime_cuando_se_pide(self, db):
        """Si el α se reparte y no se dice, quien lea el informe creerá que cada
        pareja se juzgó al 5 %."""
        base = int((datetime.now(_tz.utc) - timedelta(hours=1801)).timestamp() * 1000)
        _sembrar_par("BTC", "ETH", n=1800, rho=0.80, seed=20, base_ms=base)
        _sembrar_par("SOL", "ADA", n=1800, rho=0.60, seed=21, base_ms=base)
        salida = self._run("BTC", "ETH", "SOL", "ADA", "--family-wise",
                           "--replicates", "60")
        assert "repartido entre parejas" in salida
        assert "por pareja" in self._run("BTC", "ETH", "--replicates", "60")
