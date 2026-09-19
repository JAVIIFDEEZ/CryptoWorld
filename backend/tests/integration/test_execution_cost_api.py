"""
tests/integration/test_execution_cost_api.py — El coste de ejecución, por API.

Lo que se comprueba aquí no es la aritmética —eso vive en los tests de dominio—
sino el contrato: que el endpoint exija autenticación, que no invente un coste
cuando no hay histórico, y sobre todo que **la etiqueta del método viaje con el
número**. Un cliente que reciba `impact_bps` sin `method` no tiene forma de
saber que está leyendo una estimación y no una medición del libro de órdenes, y
ese es el modo de fallo caro de esta función.
"""

import numpy as np
import pandas as pd
import pytest


def _daily(n=60, price=100.0, volume=1_000.0, seed=1, sigma=0.03):
    rng = np.random.default_rng(seed)
    close = price * np.exp(np.cumsum(rng.normal(0, sigma, n)))
    return pd.DataFrame({
        "timestamp": np.arange(n, dtype=np.int64) * 86_400_000,
        "open": close, "high": close * 1.01, "low": close * 0.99,
        "close": close, "volume": np.full(n, volume),
    })


@pytest.fixture
def con_historico(monkeypatch):
    """Sustituye la descarga de velas: aquí se prueba el endpoint, no la red."""
    def _install(df):
        import core.application.use_cases.ohlcv_fetcher as fetcher

        class _Result:
            def __init__(self, df):
                self.df, self.source = df, "test"

        monkeypatch.setattr(fetcher, "fetch_ohlcv_dataframe",
                            lambda **k: (_Result(df) if df is not None else None))
    return _install


@pytest.mark.integration
def test_requiere_autenticacion(client):
    resp = client.get("/api/analysis/execution-cost/?asset_symbol=BTC")
    assert resp.status_code in (401, 403)


@pytest.mark.integration
def test_sin_simbolo_responde_400(authenticated_client):
    resp = authenticated_client.get("/api/analysis/execution-cost/")
    assert resp.status_code == 400


@pytest.mark.integration
def test_devuelve_la_escalera_completa(db, authenticated_client, con_historico):
    con_historico(_daily(volume=100_000.0))
    resp = authenticated_client.get("/api/analysis/execution-cost/?asset_symbol=BTC")
    assert resp.status_code == 200
    datos = resp.data
    assert datos["available"] is True
    assert len(datos["steps"]) == 4
    assert datos["symbol"] == "BTC"
    for paso in datos["steps"]:
        assert {"notional_usd", "participation_pct", "impact_bps",
                "impact_usd", "feasible"} <= set(paso)


@pytest.mark.integration
def test_el_metodo_viaja_con_el_numero(db, authenticated_client, con_historico):
    """Sin esto, `impact_bps` se lee como una medición de profundidad."""
    con_historico(_daily(volume=100_000.0))
    resp = authenticated_client.get("/api/analysis/execution-cost/?asset_symbol=BTC")
    assert resp.data["method"] == "SQRT_IMPACT_MODEL"
    assert "libro de órdenes" in resp.data["note"]


@pytest.mark.integration
def test_el_coste_crece_con_el_tamano(db, authenticated_client, con_historico):
    con_historico(_daily(volume=100_000.0))
    resp = authenticated_client.get("/api/analysis/execution-cost/?asset_symbol=BTC")
    bps = [p["impact_bps"] for p in resp.data["steps"]]
    assert bps == sorted(bps)


@pytest.mark.integration
def test_sin_historico_lo_dice_en_vez_de_devolver_cero(db, authenticated_client,
                                                      con_historico):
    """Un coste cero se leería como «ejecutar aquí es gratis», que es justo lo
    contrario de lo que significa no tener datos del activo."""
    con_historico(None)
    resp = authenticated_client.get("/api/analysis/execution-cost/?asset_symbol=XYZ")
    assert resp.status_code == 200
    assert resp.data["available"] is False
    assert resp.data["steps"] == []


@pytest.mark.integration
def test_un_activo_estrecho_marca_los_tamanos_no_ejecutables(
        db, authenticated_client, con_historico):
    con_historico(_daily(volume=10.0))         # ~1.000 USD/día de volumen
    resp = authenticated_client.get("/api/analysis/execution-cost/?asset_symbol=MINI")
    ejecutables = [p["feasible"] for p in resp.data["steps"]]
    assert ejecutables[0] is False             # ni 1.000 USD entran
    assert resp.data["max_executable_usd"] < 1_000
