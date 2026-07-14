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


class TestTokenSafety:

    @pytest.mark.integration
    def test_dangerous_token_flagged(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_risk import TokenSafetyUseCase
        cache.clear()

        class ContractClient:
            def get_smart_contract(self, chain, token):
                return {"is_verified": True, "owner_address_hash": "0xowner",
                        "abi": [{"type": "function", "name": "mint"},
                                {"type": "function", "name": "setBlacklist"}]}
            def get_token_info(self, chain, token):
                return {"name": "Rug", "symbol": "RUG", "decimals": "18"}
            def get_token_holders(self, chain, token, pages=1):
                return [{"address": {"hash": "0xw"}, "value": str(950 * 10**18)}] + \
                       [{"address": {"hash": f"0x{i}"}, "value": str(1 * 10**18)} for i in range(60)]

        out = TokenSafetyUseCase(client=ContractClient()).execute("ethereum", "0x" + "c" * 40)
        assert out["status"] == "OK"
        assert out["token_symbol"] == "RUG"
        assert out["verdict"] in ("PELIGROSO", "RIESGO ALTO")
        cats = {f["category"] for f in out["flags"]}
        assert "mint" in cats and "concentration" in cats

    @pytest.mark.integration
    def test_unverified_token(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_risk import TokenSafetyUseCase
        cache.clear()

        class EmptyClient:
            def get_smart_contract(self, chain, token):
                return {}          # no verificado
            def get_token_info(self, chain, token):
                return {"name": "X", "symbol": "X", "decimals": "18"}
            def get_token_holders(self, chain, token, pages=1):
                return []

        out = TokenSafetyUseCase(client=EmptyClient()).execute("ethereum", "0x" + "c" * 40)
        assert out["verified"] is False
        assert any(f["category"] == "unverified" for f in out["flags"])

    @pytest.mark.integration
    def test_token_safety_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/forensics/token-safety/").status_code == 401

    @pytest.mark.integration
    def test_token_safety_validates(self, authenticated_client, db):
        resp = authenticated_client.get("/api/blockchain/forensics/token-safety/", {"token": "bad"})
        assert resp.status_code == 400


class TestWashTrading:

    @pytest.mark.integration
    def test_detects_round_trip_wash(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_risk import WashTradingUseCase
        cache.clear()

        def transfer(frm, to):
            return {"from": {"hash": frm}, "to": {"hash": to},
                    "total": {"value": str(100 * 10**18)}, "timestamp": "2023-11-14T12:00:00Z"}

        class WashClient:
            def get_token_info(self, chain, token):
                return {"name": "Pump", "symbol": "PUMP", "decimals": "18"}
            def get_token_transfers(self, chain, token, pages=2):
                out = []
                for _ in range(8):
                    out.append(transfer("0xa", "0xb"))
                    out.append(transfer("0xb", "0xa"))
                return out

        out = WashTradingUseCase(client=WashClient()).execute("ethereum", "0x" + "c" * 40)
        assert out["status"] == "OK"
        assert out["token_symbol"] == "PUMP"
        assert out["verdict"] == "MANIPULADO"
        assert out["round_trip_ratio"] > 0.9

    @pytest.mark.integration
    def test_organic_token_clean(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_risk import WashTradingUseCase
        cache.clear()

        class OrganicClient:
            def get_token_info(self, chain, token):
                return {"name": "Real", "symbol": "REAL", "decimals": "18"}
            def get_token_transfers(self, chain, token, pages=2):
                return [{"from": {"hash": f"0xs{i}"}, "to": {"hash": f"0xd{i}"},
                         "total": {"value": str(50 * 10**18)}, "timestamp": "2023-11-14T12:00:00Z"}
                        for i in range(20)]

        out = WashTradingUseCase(client=OrganicClient()).execute("ethereum", "0x" + "c" * 40)
        assert out["verdict"] == "ORGÁNICO"

    @pytest.mark.integration
    def test_wash_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/forensics/wash-trading/").status_code == 401

    @pytest.mark.integration
    def test_wash_validates(self, authenticated_client, db):
        resp = authenticated_client.get("/api/blockchain/forensics/wash-trading/", {"token": "bad"})
        assert resp.status_code == 400
