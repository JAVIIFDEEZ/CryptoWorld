"""
tests/integration/test_onchain_forensics_api.py — Casos de uso/endpoints forenses.

Usa un cliente Blockscout falso (sin red) para verificar la normalización de
transacciones/tenedores, la validación de direcciones y los endpoints.
"""

import pytest


class FakeClient:
    """Cliente Blockscout de prueba: devuelve datos con la FORMA real del API v2."""

    def __init__(self, txs_by_addr=None, holders=None, token_info=None):
        self._txs = txs_by_addr or {}
        self._holders = holders or []
        self._info = token_info or {"decimals": "18", "name": "Test", "symbol": "TST", "holders": "1000"}

    def get_transactions(self, chain, address):
        return self._txs.get(address.lower(), [])

    def get_token_holders(self, chain, token, pages=1):
        return self._holders

    def get_token_info(self, chain, token):
        return self._info


def _tx(frm, to, wei, ts="2023-11-14T12:00:00.000000Z"):
    return {"from": {"hash": frm}, "to": {"hash": to}, "value": str(wei), "timestamp": ts}


A = "0x" + "a" * 40
B = "0x" + "b" * 40
TOKEN = "0x" + "c" * 40


class TestTraceFlow:

    @pytest.mark.integration
    def test_normalizes_and_builds_tree(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_forensics import TraceFlowUseCase
        cache.clear()
        client = FakeClient(txs_by_addr={A.lower(): [_tx(A, B, 5 * 10**18)]})
        out = TraceFlowUseCase(client=client).execute("ethereum", A, depth=1)
        assert out["status"] == "OK"
        assert out["tree"]["children"][0]["address"] == B.lower()
        assert out["tree"]["children"][0]["value_in"] == pytest.approx(5.0)

    @pytest.mark.integration
    def test_invalid_address(self, db):
        from core.application.use_cases.get_onchain_forensics import TraceFlowUseCase
        assert "error" in TraceFlowUseCase(client=FakeClient()).execute("ethereum", "nope")


class TestConcentration:

    @pytest.mark.integration
    def test_concentration_from_holders(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_forensics import TokenConcentrationUseCase
        cache.clear()
        holders = [{"address": {"hash": "0xwhale", "is_contract": False}, "value": str(900 * 10**18)}]
        holders += [{"address": {"hash": f"0x{i}", "is_contract": False}, "value": str(1 * 10**18)}
                    for i in range(100)]
        client = FakeClient(holders=holders)
        out = TokenConcentrationUseCase(client=client).execute("ethereum", TOKEN)
        assert out["status"] == "OK"
        assert out["token_symbol"] == "TST"
        assert out["concentration"]["verdict"] == "CRÍTICA"
        assert out["concentration"]["top_holders"][0]["value"] == pytest.approx(900.0)


class TestFingerprint:

    @pytest.mark.integration
    def test_fingerprint_from_txs(self, db):
        from django.core.cache import cache
        from core.application.use_cases.get_onchain_forensics import WalletFingerprintUseCase
        cache.clear()
        txs = [_tx(A, B, 10**18, f"2023-11-{10 + i:02d}T09:00:00.000000Z") for i in range(5)]
        client = FakeClient(txs_by_addr={A.lower(): txs})
        out = WalletFingerprintUseCase(client=client).execute("ethereum", A, now_ts=1_700_100_000)
        assert out["status"] == "OK"
        assert out["fingerprint"]["available"] is True
        assert out["fingerprint"]["sample_txs"] == 5


class TestApi:

    @pytest.mark.integration
    def test_endpoints_require_auth(self, api_client):
        assert api_client.get("/api/blockchain/forensics/flow/").status_code == 401
        assert api_client.get("/api/blockchain/forensics/concentration/").status_code == 401
        assert api_client.get("/api/blockchain/forensics/fingerprint/").status_code == 401

    @pytest.mark.integration
    def test_flow_endpoint_validates_address(self, authenticated_client, db):
        resp = authenticated_client.get("/api/blockchain/forensics/flow/", {"address": "bad"})
        assert resp.status_code == 400
        assert "error" in resp.data
