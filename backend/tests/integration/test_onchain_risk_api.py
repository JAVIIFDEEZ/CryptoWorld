"""
tests/integration/test_onchain_risk_api.py — Casos de uso/endpoints de riesgo.

Cliente Blockscout falso: verifica la extracción de etiquetas (riesgo), la
decodificación de approve() (aprobaciones) y la construcción de aristas (entidad).
"""

import pytest

A = "0x" + "a" * 40
B = "0x" + "b" * 40
C = "0x" + "c" * 40


class FakeClient:
    def __init__(self, address_info=None, txs_by_addr=None):
        self._info = address_info or {}
        self._txs = txs_by_addr or {}

    def get_address(self, chain, address):
        return self._info

    def get_transactions(self, chain, address):
        return self._txs.get(address.lower(), [])


def _node(addr, label=None, is_contract=False, is_verified=False):
    node = {"hash": addr, "is_contract": is_contract, "is_verified": is_verified}
    if label:
        node["metadata"] = {"tags": [{"name": label}]}
    return node


def _tx(frm, to, ts="2023-11-14T12:00:00.000000Z"):
    return {"from": frm, "to": to, "value": "0", "timestamp": ts}


class TestAddressRisk:

    @pytest.mark.integration
    def test_flagged_counterparty_raises_score(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_risk import AddressRiskUseCase
        cache.clear()
        txs = [_tx(_node(A), _node(B, label="Tornado Cash"))]
        out = AddressRiskUseCase(client=FakeClient(address_info=_node(A), txs_by_addr={A.lower(): txs})).execute("ethereum", A)
        assert out["status"] == "OK"
        assert out["score"] > 0
        assert out["counterparties_analyzed"] == 1
        assert any(f["category"] == "mixer" for f in out["factors"])

    @pytest.mark.integration
    def test_clean_address(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_risk import AddressRiskUseCase
        cache.clear()
        txs = [_tx(_node(A), _node(B, label="Uniswap"))]
        out = AddressRiskUseCase(client=FakeClient(address_info=_node(A), txs_by_addr={A.lower(): txs})).execute("ethereum", A)
        assert out["score"] == 0 and out["band"] == "BAJO"

    @pytest.mark.integration
    def test_invalid(self, db):
        from core.application.use_cases.get_onchain_risk import AddressRiskUseCase
        assert "error" in AddressRiskUseCase(client=FakeClient()).execute("ethereum", "x")


class TestApprovals:

    @pytest.mark.integration
    def test_decodes_and_ranks_approvals(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_risk import ApprovalsUseCase
        cache.clear()
        token = _node(C, is_verified=False)
        token["name"] = "USDC"
        txs = [{
            "method": "approve",
            "to": token,
            "timestamp": "2023-11-14T12:00:00.000000Z",
            "decoded_input": {"parameters": [
                {"name": "spender", "type": "address", "value": B},
                {"name": "amount", "type": "uint256", "value": str(2**256 - 1)},
            ]},
        }]
        out = ApprovalsUseCase(client=FakeClient(txs_by_addr={A.lower(): txs})).execute("ethereum", A)
        assert out["status"] == "OK"
        assert out["total"] == 1
        assert out["approvals"][0]["is_unlimited"] is True
        assert out["approvals"][0]["risk"] == "ALTO"      # ilimitada + sin verificar
        assert out["unlimited"] == 1

    @pytest.mark.integration
    def test_no_approvals(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_risk import ApprovalsUseCase
        cache.clear()
        txs = [{"method": "transfer", "to": _node(C), "decoded_input": {}}]
        out = ApprovalsUseCase(client=FakeClient(txs_by_addr={A.lower(): txs})).execute("ethereum", A)
        assert out["total"] == 0 and out["worst"] == "NINGUNO"


class TestEntityGraph:

    @pytest.mark.integration
    def test_builds_edges_from_frequency(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_risk import EntityGraphUseCase
        cache.clear()
        # Root interactúa 3 veces con B → arista fuerte; B y C se mueven juntos
        root_txs = [_tx(_node(A), _node(B)) for _ in range(3)]
        b_txs = [_tx(_node(B), _node(C)) for _ in range(2)]
        client = FakeClient(txs_by_addr={A.lower(): root_txs, B.lower(): b_txs, C.lower(): []})
        out = EntityGraphUseCase(client=client).execute("ethereum", A)
        assert out["status"] == "OK"
        assert A.lower() in out["entity"]
        assert out["entity_size"] >= 1
        assert any(e["a"] == A.lower() or e["b"] == A.lower() for e in out["edges"])


class TestApi:

    @pytest.mark.integration
    def test_endpoints_require_auth(self, api_client):
        for path in ("risk", "approvals", "entity"):
            assert api_client.get(f"/api/blockchain/forensics/{path}/").status_code == 401

    @pytest.mark.integration
    def test_risk_validates_address(self, authenticated_client, db):
        resp = authenticated_client.get("/api/blockchain/forensics/risk/", {"address": "bad"})
        assert resp.status_code == 400
