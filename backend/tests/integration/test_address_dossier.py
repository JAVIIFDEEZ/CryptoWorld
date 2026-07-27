"""
tests/integration/test_address_dossier.py — Dossier forense unificado.

Cliente Blockscout falso compartido por todas las sub-herramientas: verifica la
síntesis del veredicto global, los hallazgos clave y la degradación honesta.
"""

import pytest

A = "0x" + "a" * 40
MIXER = "0x" + "b" * 40


class FakeClient:
    """Un solo cliente que sirve a las 5 sub-herramientas del dossier."""

    def __init__(self, txs=None, address_info=None):
        self._txs = txs or []
        self._info = address_info or {"hash": A}

    def get_address(self, chain, address):
        return self._info

    def get_transactions(self, chain, address):
        # La raíz tiene txs; las contrapartes, ninguna (árbol de 1 nivel).
        return self._txs if address.lower() == A.lower() else []


def _node(addr, label=None):
    node = {"hash": addr}
    if label:
        node["metadata"] = {"tags": [{"name": label}]}
    return node


def _tx(frm, to, ts="2023-11-14T12:00:00.000000Z", value="1000000000000000000"):
    return {"from": frm, "to": to, "value": value, "timestamp": ts}


class TestDossier:

    @pytest.mark.integration
    def test_synthesizes_verdict_from_sections(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_address_dossier import AddressDossierUseCase
        cache.clear()
        # Varias tx a una contraparte etiquetada como mixer → riesgo alto
        txs = [_tx(_node(A), _node(MIXER, label="Tornado Cash")) for _ in range(4)]
        out = AddressDossierUseCase(client=FakeClient(txs=txs, address_info=_node(A))).execute("ethereum", A)
        assert out["status"] == "OK"
        assert out["address"] == A.lower()
        v = out["verdict"]
        assert v["overall_score"] > 0
        assert v["band"] in ("MODERADO", "ELEVADO", "CRÍTICO")
        assert v["risk_band"] is not None
        assert any("mixer" in f["text"].lower() or "riesgo" in f["text"].lower()
                   for f in v["key_findings"])
        # Todas las secciones presentes
        assert set(out["sections"]) == {"risk", "fingerprint", "approvals", "entity", "flow"}

    @pytest.mark.integration
    def test_clean_address_is_limpio(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_address_dossier import AddressDossierUseCase
        cache.clear()
        txs = [_tx(_node(A), _node("0x" + "c" * 40, label="Uniswap"))]
        out = AddressDossierUseCase(client=FakeClient(txs=txs, address_info=_node(A))).execute("ethereum", A)
        assert out["verdict"]["band"] == "LIMPIO"
        assert out["verdict"]["overall_score"] == 0

    @pytest.mark.integration
    def test_invalid_address(self, db):
        from core.application.use_cases.get_address_dossier import AddressDossierUseCase
        assert "error" in AddressDossierUseCase(client=FakeClient()).execute("ethereum", "bad")


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/forensics/dossier/").status_code == 401

    @pytest.mark.integration
    def test_validates_address(self, authenticated_client, db):
        resp = authenticated_client.get("/api/blockchain/forensics/dossier/", {"address": "bad"})
        assert resp.status_code == 400
