"""
tests/integration/test_execution_window_api.py — La ventana de ejecución por API.

Lo que solo se puede romper con base de datos y endpoint delante:

· que el veredicto se calcule sobre el almacén propio y NO falle cuando el coste de
  ejecución —que sale de la cadena que consulta la red— no está disponible, porque
  en un entorno sin salida a internet eso es lo normal y el valor principal de la
  pantalla no depende de él;
· que la caché esté anclada a la hora en curso, no a una duración fija: con una
  caché de N minutos el endpoint podría devolver una casilla horaria ya pasada;
· que el endpoint exija autenticación y valide sus parámetros;
· que un activo sin histórico lo diga en vez de emitir un veredicto.
"""

from datetime import datetime, timedelta, timezone as _tz

import numpy as np
import pytest
from django.core.cache import cache
from django.urls import reverse
from rest_framework.test import APIClient


H = 3_600_000
URL = "/api/market/execution-window/"


def _sembrar(symbol="BTC", semanas=70, interval="1h", seed=1, vol=0.004,
             boost=None):
    """Siembra velas horarias de semanas completas, con boost opcional por casilla."""
    from core.domain.services import seasonality as sn
    from core.infrastructure.persistence.models import OhlcvCandle

    n = 24 * 7 * semanas
    inicio = int((datetime.now(_tz.utc) - timedelta(hours=n + 1)).timestamp() * 1000)
    inicio -= inicio % H
    marcas = np.arange(n, dtype=np.int64) * H + inicio

    rng = np.random.default_rng(seed)
    r = rng.normal(0.0, vol, n)
    if boost:
        dia, (h0, h1), factor = boost
        idx = sn.week_hour_index(marcas)
        sel = (idx // 24 == dia) & ((idx % 24) >= h0) & ((idx % 24) < h1)
        r = np.where(sel, r * factor, r)
    cierres = 30_000.0 * np.exp(np.cumsum(r))

    OhlcvCandle.objects.bulk_create([
        OhlcvCandle(symbol=symbol, interval=interval, open_time=int(marcas[i]),
                    open=cierres[i], high=cierres[i], low=cierres[i],
                    close=cierres[i], volume=1.0, source="test")
        for i in range(n)
    ], batch_size=3000)
    return marcas


@pytest.fixture(autouse=True)
def _cache_limpia():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cliente(db, django_user_model):
    usuario = django_user_model.objects.create_user(
        username="ventana", email="ventana@test.com", password="Secreta123!")
    c = APIClient()
    c.force_authenticate(user=usuario)
    return c


# ─────────────────────────────────────────────────────────── el caso de uso


@pytest.mark.integration
def test_el_veredicto_se_calcula_sin_coste_de_ejecucion(db):
    """El coste sale de la cadena que consulta la red; sin salida a internet no hay
    número, y el veredicto horario —que es el valor principal— no depende de él."""
    from core.application.use_cases.execution_window import ExecutionWindowUseCase

    _sembrar(semanas=70, seed=3)
    out = ExecutionWindowUseCase().execute("BTC")
    assert out["verdict"] != "SIN_DATOS"
    assert "reasons" in out and out["reasons"]
    # En este entorno el coste no se puede estimar y eso no rompe nada.
    assert "cost_bps_first_step" in out


@pytest.mark.integration
def test_sin_historico_lo_dice_en_vez_de_emitir_veredicto(db):
    from core.application.use_cases.execution_window import ExecutionWindowUseCase

    out = ExecutionWindowUseCase().execute("BTC")
    assert out["verdict"] == "SIN_DATOS"
    assert "ingerir histórico" in out["note"]


@pytest.mark.integration
def test_una_estructura_horaria_plantada_llega_al_veredicto(db):
    """Con la actividad multiplicada en un tramo conocido, la rejilla que viaja en
    la respuesta tiene que encontrarla y el panel poder pintarla."""
    from core.application.use_cases.execution_window import ExecutionWindowUseCase

    _sembrar(semanas=70, seed=4, boost=(4, (12, 16), 2.5))
    out = ExecutionWindowUseCase().execute("BTC")
    assert out["seasonality"]["verdict"] == "CON_ESTRUCTURA"
    assert out["seasonality_usable"] is True
    assert out["seasonality"]["cells_significant"] >= 1
    assert len(out["seasonality"]["mean_abs_return"]) == 168


@pytest.mark.integration
def test_sin_estructura_el_veredicto_horario_no_se_emite(db):
    """El caso que el panel tiene que pintar en gris: sobre ruido no hay base
    horaria y el veredicto lo declara en vez de inventar un semáforo."""
    from core.application.use_cases.execution_window import ExecutionWindowUseCase

    _sembrar(semanas=70, seed=5)
    out = ExecutionWindowUseCase().execute("BTC")
    assert out["seasonality_usable"] is False
    assert out["verdict"] == "SIN_BASE_HORARIA"
    assert all(h["activity"] is None for h in out["hours"])


@pytest.mark.integration
def test_el_horizonte_y_la_ventana_son_los_pedidos(db):
    from core.application.use_cases.execution_window import ExecutionWindowUseCase

    _sembrar(semanas=70, seed=6)
    out = ExecutionWindowUseCase().execute("BTC", horizon_hours=24, window_hours=4)
    assert len(out["hours"]) == 24
    assert out["best_window"]["length_hours"] == 4


@pytest.mark.integration
def test_no_mezcla_marcos_temporales(db):
    from core.application.use_cases.execution_window import ExecutionWindowUseCase

    _sembrar(semanas=70, seed=7, interval="1h")
    assert ExecutionWindowUseCase().execute("BTC", interval="4h")["verdict"] == "SIN_DATOS"


# ───────────────────────────────────────────────────────────── el endpoint


@pytest.mark.integration
def test_el_endpoint_requiere_autenticacion(db):
    assert APIClient().get(URL, {"asset_symbol": "BTC"}).status_code in (401, 403)


@pytest.mark.integration
def test_el_endpoint_devuelve_el_veredicto_y_la_rejilla(cliente):
    _sembrar(semanas=70, seed=10, boost=(4, (12, 16), 2.5))
    r = cliente.get(URL, {"asset_symbol": "BTC", "notional": 25000})
    assert r.status_code == 200
    datos = r.json()
    assert datos["symbol"] == "BTC"
    assert datos["notional_usd"] == 25000.0
    assert datos["verdict"] in ("FAVORABLE", "NEUTRAL", "DESFAVORABLE", "ESPERAR",
                               "EL_TAMANO_MANDA", "SIN_BASE_HORARIA")
    assert len(datos["seasonality"]["mean_abs_return"]) == 168
    assert datos["hours"]


@pytest.mark.integration
def test_el_endpoint_publica_sus_limites_y_lo_que_no_cubre(cliente):
    """Las dos cosas que impiden leer el panel como una señal de dirección."""
    _sembrar(semanas=70, seed=11)
    datos = cliente.get(URL, {"asset_symbol": "BTC"}).json()
    assert "FILTRO DE EJECUCIÓN" in datos["limits"]
    assert "FOMC" in datos["calendar_underivable"]
    assert "ORDENACIÓN" in datos["protocol"]


@pytest.mark.integration
def test_la_cache_esta_anclada_a_la_hora_en_curso(cliente):
    """Con una caché de duración fija, el endpoint podría devolver una casilla
    horaria ya pasada. La clave lleva la hora, así que al cambiar de hora se
    recalcula."""
    import time

    from core.application.use_cases.execution_window import ExecutionWindowUseCase

    _sembrar(semanas=70, seed=12)
    assert cliente.get(URL, {"asset_symbol": "BTC"}).status_code == 200

    hora = int(time.time() * 1000) // H
    clave_actual = f"execution_window:BTC:1h:10000:48:2:{hora}"
    assert cache.get(clave_actual) is not None
    # La hora siguiente no está cacheada: cambiar de hora fuerza el recálculo.
    assert cache.get(f"execution_window:BTC:1h:10000:48:2:{hora + 1}") is None
    assert ExecutionWindowUseCase is not None


@pytest.mark.integration
def test_falta_el_simbolo_se_rechaza(cliente):
    assert cliente.get(URL).status_code == 400


@pytest.mark.integration
def test_un_nocional_imposible_se_rechaza(cliente):
    for malo in ("0", "-100", "abc", "1e12"):
        assert cliente.get(URL, {"asset_symbol": "BTC",
                                 "notional": malo}).status_code == 400


@pytest.mark.integration
def test_un_horizonte_o_ventana_imposibles_se_rechazan(cliente):
    assert cliente.get(URL, {"asset_symbol": "BTC", "horizon": 2}).status_code == 400
    assert cliente.get(URL, {"asset_symbol": "BTC", "horizon": 9999}).status_code == 400
    assert cliente.get(URL, {"asset_symbol": "BTC", "window": 0}).status_code == 400
    assert cliente.get(URL, {"asset_symbol": "BTC", "window": 99}).status_code == 400
    assert cliente.get(URL, {"asset_symbol": "BTC", "horizon": "x"}).status_code == 400


@pytest.mark.integration
def test_sin_historico_el_endpoint_responde_200_con_sin_datos(cliente):
    """Un activo sin velas no es un error del cliente: es una ausencia de datos, y
    devolver 500 o 404 escondería la diferencia."""
    r = cliente.get(URL, {"asset_symbol": "ZZZ"})
    assert r.status_code == 200
    assert r.json()["verdict"] == "SIN_DATOS"


@pytest.mark.integration
def test_la_ruta_esta_registrada_con_su_nombre(db):
    assert reverse("market-execution-window") == URL
