"""
tests/integration/test_methodology_api.py — La nota metodológica, servida.

Lo que se comprueba es el contrato de publicación: que las notas lleguen
completas, que la evidencia propia viaje con ellas —el número de configuraciones
probadas es lo que hace interpretable cualquier Sharpe— y que la página no
reviente cuando todavía no hay nada que enseñar, que es el estado de una
instalación recién puesta en marcha.
"""

import pytest


@pytest.mark.integration
def test_requiere_autenticacion(client):
    """La evidencia incluye la campeona del usuario; el texto es genérico pero
    la cifra no."""
    assert client.get("/api/methodology/").status_code in (401, 403)


@pytest.mark.integration
def test_devuelve_las_notas_completas(db, authenticated_client):
    resp = authenticated_client.get("/api/methodology/")
    assert resp.status_code == 200
    notas = resp.data["notes"]
    assert len(notas) >= 10
    for nota in notas:
        assert {"key", "title", "what", "assumptions", "limits"} <= set(nota)
        assert nota["limits"]


@pytest.mark.integration
def test_publica_la_regla_y_lo_que_no_se_afirma(db, authenticated_client):
    resp = authenticated_client.get("/api/methodology/")
    assert "deflactar" in resp.data["golden_rule"]
    assert any("dirección del precio" in d for d in resp.data["disclaimers"])


@pytest.mark.integration
def test_va_versionada(db, authenticated_client):
    resp = authenticated_client.get("/api/methodology/")
    assert resp.data["version"]


@pytest.mark.integration
def test_sin_estrategias_todavia_no_revienta(db, authenticated_client):
    """El estado de una instalación recién puesta en marcha: cero ejecuciones,
    cero campeonas. La nota sigue siendo válida y tiene que servirse igual."""
    resp = authenticated_client.get("/api/methodology/")
    assert resp.status_code == 200
    assert resp.data["evidence_available"] is True
    assert resp.data["evaluations_total"] == 0
    assert resp.data["champion_sharpe"] is None


@pytest.mark.integration
def test_la_curva_del_azar_acompana_a_la_nota(db, authenticated_client):
    """Un Sharpe sin el número de pruebas que costó encontrarlo no es
    interpretable, y la curva es la forma de enseñarlo."""
    resp = authenticated_client.get("/api/methodology/")
    curva = resp.data["expected_max_sharpe"]["curve"]
    assert len(curva) >= 2
    valores = [p["expected_max_sharpe"] for p in curva]
    assert valores == sorted(valores)      # más pruebas, más Sharpe por azar


@pytest.mark.integration
def test_declara_que_la_varianza_de_la_curva_es_supuesta(db, authenticated_client):
    """Presentar como exacta una curva dibujada con una varianza supuesta sería
    exactamente el tipo de cifra que esta misma nota critica."""
    resp = authenticated_client.get("/api/methodology/")
    assert resp.data["variance_source"] == "FALLBACK"
    assert "supuesta" in resp.data["evidence_note"]


@pytest.mark.integration
def test_cuenta_las_ejecuciones_registradas(db, authenticated_client, test_user):
    from core.infrastructure.persistence.models import StrategyExperimentRun

    StrategyExperimentRun.objects.create(
        asset_symbol="BTC", interval="1d", evaluations=1200, effective_trials=40)
    StrategyExperimentRun.objects.create(
        asset_symbol="ETH", interval="1d", evaluations=800, effective_trials=25)

    resp = authenticated_client.get("/api/methodology/")
    assert resp.data["runs_recorded"] == 2
    assert resp.data["evaluations_total"] == 2000
    assert resp.data["effective_trials_total"] == 65
