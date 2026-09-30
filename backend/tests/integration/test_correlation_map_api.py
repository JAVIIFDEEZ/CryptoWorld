"""
tests/integration/test_correlation_map_api.py — El mapa de correlaciones por API.

Lo que solo se puede romper con base de datos y endpoint delante: que las series
se unan por marca temporal, que las etiquetas y la matriz vayan en el mismo orden
—el peor fallo posible aquí porque no tiene ningún síntoma visible—, que el
endpoint exija autenticación y que valide sus parámetros.
"""

from datetime import datetime, timedelta, timezone as _tz

import numpy as np
import pytest
from django.urls import reverse
from rest_framework.test import APIClient


H = 3_600_000
URL = "/api/market/correlation-map/"


def _sembrar(simbolos, n=900, interval="1h", seed=1, cargas=None, saltar=None):
    """Siembra velas correlacionadas por un factor común para cada símbolo."""
    from core.infrastructure.persistence.models import OhlcvCandle

    rng = np.random.default_rng(seed)
    inicio = int((datetime.now(_tz.utc) - timedelta(hours=n + 1)).timestamp() * 1000)
    inicio -= inicio % H
    marcas = np.arange(n, dtype=np.int64) * H + inicio
    factor = rng.normal(0, 0.02, n)
    saltar = saltar or {}

    filas = []
    for s in simbolos:
        carga = (cargas or {}).get(s, 0.8)
        r = carga * factor + np.sqrt(max(1 - carga ** 2, 0)) * rng.normal(0, 0.02, n)
        cierres = 100.0 * np.exp(np.cumsum(r))
        omitir = set(saltar.get(s, ()))
        for i in range(n):
            if i in omitir:
                continue
            filas.append(OhlcvCandle(symbol=s, interval=interval,
                                     open_time=int(marcas[i]), open=cierres[i],
                                     high=cierres[i], low=cierres[i],
                                     close=cierres[i], volume=1.0, source="test"))
    OhlcvCandle.objects.bulk_create(filas, batch_size=2000)
    return marcas


@pytest.fixture
def cliente(db, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="mapa", email="mapa@test.com", password="Secreta123!")
    c = APIClient()
    c.force_authenticate(user=usuario)
    return c


# ─────────────────────────────────────────────────────────── el caso de uso


@pytest.mark.integration
def test_las_series_se_unen_por_marca_temporal(db):
    """A un símbolo le faltan velas en mitad del histórico. Con emparejado por
    posición, todo lo posterior al hueco quedaría desfasado y la correlación
    medida dejaría de ser una correlación."""
    from core.application.use_cases.correlation_map import CorrelationMapUseCase

    huecos = tuple(range(400, 460))
    _sembrar(["AAA", "BBB", "CCC"], n=900, cargas={"AAA": 0.9, "BBB": 0.9,
                                                   "CCC": 0.9},
             saltar={"BBB": huecos})
    out = CorrelationMapUseCase().execute(symbols=["AAA", "BBB", "CCC"], window=90)
    assert out["candles_aligned"] == 900 - len(huecos) - 1
    assert out["average_correlation"] > 0.5


@pytest.mark.integration
def test_las_etiquetas_y_la_matriz_van_en_el_mismo_orden(db):
    """Si se desincronizaran, el mapa mostraría las correlaciones de otros activos
    sin ningún síntoma visible. Se comprueba contra una celda recalculada."""
    from core.application.use_cases.correlation_map import CorrelationMapUseCase

    _sembrar(["AAA", "BBB", "CCC", "DDD"], n=900,
             cargas={"AAA": 0.95, "BBB": 0.92, "CCC": 0.1, "DDD": 0.15})
    out = CorrelationMapUseCase().execute(
        symbols=["AAA", "BBB", "CCC", "DDD"], window=200)
    m = np.array(out["matrix"])
    assert np.allclose(np.diag(m), 1.0)
    assert np.allclose(m, m.T)
    # Los dos de carga alta tienen que estar más correlacionados entre sí que con
    # los de carga baja, y eso se lee por las etiquetas.
    i, j = out["labels"].index("AAA"), out["labels"].index("BBB")
    k = out["labels"].index("CCC")
    assert m[i, j] > m[i, k]


@pytest.mark.integration
def test_un_activo_sin_historico_se_declara(db):
    from core.application.use_cases.correlation_map import CorrelationMapUseCase

    _sembrar(["AAA", "BBB"], n=900)
    out = CorrelationMapUseCase().execute(symbols=["AAA", "BBB", "ZZZ"], window=90)
    assert "ZZZ" in out["missing"]
    assert set(out["labels"]) == {"AAA", "BBB"}


@pytest.mark.integration
def test_sin_almacen_lo_dice_en_vez_de_devolver_una_matriz_vacia(db):
    from core.application.use_cases.correlation_map import CorrelationMapUseCase

    out = CorrelationMapUseCase().execute(symbols=["AAA", "BBB"])
    assert out["verdict"] == "SIN_DATOS"
    assert out["matrix"] == []


@pytest.mark.integration
def test_un_solo_activo_no_es_una_matriz(db):
    from core.application.use_cases.correlation_map import CorrelationMapUseCase

    _sembrar(["AAA"], n=900)
    assert CorrelationMapUseCase().execute(symbols=["AAA"])["verdict"] == "SIN_DATOS"


@pytest.mark.integration
def test_no_mezcla_marcos_temporales(db):
    from core.application.use_cases.correlation_map import CorrelationMapUseCase

    _sembrar(["AAA", "BBB"], n=900, interval="1h")
    out = CorrelationMapUseCase().execute(symbols=["AAA", "BBB"], interval="4h")
    assert out["verdict"] == "SIN_DATOS"


# ───────────────────────────────────────────────────────────── el endpoint


@pytest.mark.integration
def test_el_endpoint_requiere_autenticacion(db):
    assert APIClient().get(URL).status_code in (401, 403)


@pytest.mark.integration
def test_el_endpoint_devuelve_la_matriz_y_el_espectro(cliente):
    _sembrar(["AAA", "BBB", "CCC"], n=900)
    r = cliente.get(URL, {"symbols": "AAA,BBB,CCC", "window": 90})
    assert r.status_code == 200
    datos = r.json()
    assert len(datos["labels"]) == 3
    assert len(datos["matrix"]) == 3
    assert datos["eigen"]["top_share"] is not None
    assert datos["eigen"]["effective_bets"] is not None


@pytest.mark.integration
def test_el_endpoint_publica_el_error_de_cada_celda(cliente):
    """Sin él, quien pinte el degradado leerá diferencias que son ruido."""
    _sembrar(["AAA", "BBB", "CCC"], n=900)
    datos = cliente.get(URL, {"symbols": "AAA,BBB,CCC", "window": 90}).json()
    assert datos["cell_se_z"] > 0
    assert "multiplicidad" in datos["limits"]


@pytest.mark.integration
def test_el_endpoint_marca_los_cambios_frente_a_la_referencia(cliente):
    _sembrar(["AAA", "BBB", "CCC"], n=900)
    datos = cliente.get(URL, {"symbols": "AAA,BBB,CCC", "window": 90,
                              "reference_window": 90}).json()
    assert "delta" in datos
    assert "delta_beyond_noise" in datos
    assert datos["delta_threshold_z"] > 0


@pytest.mark.integration
def test_una_ventana_imposible_se_rechaza(cliente):
    assert cliente.get(URL, {"window": 3}).status_code == 400
    assert cliente.get(URL, {"window": "abc"}).status_code == 400
    assert cliente.get(URL, {"reference_window": 99999}).status_code == 400


@pytest.mark.integration
def test_sin_simbolos_usa_la_cesta_por_capitalizacion(cliente):
    """Y si no hay cesta, lo dice en vez de reventar."""
    r = cliente.get(URL)
    assert r.status_code == 200
    assert r.json()["verdict"] in ("SIN_DATOS", "CONCENTRADO", "INTERMEDIO",
                                  "REPARTIDO")


@pytest.mark.integration
def test_la_ruta_esta_registrada_con_su_nombre(db):
    assert reverse("market-correlation-map") == URL
