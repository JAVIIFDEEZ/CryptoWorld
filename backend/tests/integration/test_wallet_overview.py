"""
tests/integration/test_wallet_overview.py — Explorador on-chain de wallets.

Verifica la consolidación del retrato on-chain (saldo nativo valorado, tokens
ERC-20 ordenados por valor USD, transacciones con dirección), la validación de
red/dirección y los endpoints REST. El cliente Blockscout se mockea: los tests
no tocan la red (igual que el resto de clientes externos del proyecto).
"""

import pytest

from core.application.use_cases.get_wallet_overview import GetWalletOverviewUseCase
from core.infrastructure.external_apis.blockscout_client import (
    BlockscoutClient, BlockscoutClientError, is_valid_address,
)

VITALIK = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

# Respuestas canónicas con la forma real de la API v2 de Blockscout.
FAKE_ADDRESS = {
    "hash": VITALIK,
    "coin_balance": "5000000000000000000",   # 5 ETH (wei)
    "exchange_rate": "2000.0",                # 2000 USD/ETH
    "is_contract": False,
    "is_verified": False,
    "ens_domain_name": "vitalik.eth",
}
FAKE_TOKENS = [
    # USDC: 6 decimales, 1500 unidades → valor 1500 USD
    {"token": {"address": "0xA0b", "name": "USD Coin", "symbol": "USDC", "decimals": "6",
               "exchange_rate": "1.0", "type": "ERC-20"}, "value": "1500000000"},
    # WETH: 18 decimales, 2 unidades → valor 4000 USD (debe ir primero por valor)
    {"token": {"address": "0xC02", "name": "WETH", "symbol": "WETH", "decimals": "18",
               "exchange_rate": "2000.0", "type": "ERC-20"}, "value": "2000000000000000000"},
    # Token sin precio: balance 10, sin exchange_rate → value_usd None (va al final)
    {"token": {"address": "0xDEAD", "name": "NoPrice", "symbol": "NOP", "decimals": "18",
               "exchange_rate": None, "type": "ERC-20"}, "value": "10000000000000000000"},
    # NFT (ERC-721) → debe ignorarse
    {"token": {"address": "0xNFT", "name": "Punk", "symbol": "PUNK", "decimals": "0",
               "type": "ERC-721"}, "value": "1"},
    # Saldo cero → debe ignorarse
    {"token": {"address": "0xZERO", "name": "Zero", "symbol": "ZRO", "decimals": "18",
               "exchange_rate": "1.0", "type": "ERC-20"}, "value": "0"},
]
FAKE_TXS = [
    {"hash": "0xaaa", "method": "transfer", "from": {"hash": VITALIK}, "to": {"hash": "0xbbb"},
     "value": "1000000000000000000", "status": "ok", "timestamp": "2026-06-01T00:00:00Z"},
    {"hash": "0xccc", "method": None, "from": {"hash": "0xddd"}, "to": {"hash": VITALIK},
     "value": "500000000000000000", "status": "ok", "timestamp": "2026-06-02T00:00:00Z"},
]


class _FakeClient:
    def get_address(self, chain, address):
        return FAKE_ADDRESS

    def get_token_balances(self, chain, address):
        return FAKE_TOKENS

    def get_transactions(self, chain, address):
        return FAKE_TXS


class TestAddressValidation:

    @pytest.mark.unit
    def test_valid_and_invalid_addresses(self):
        assert is_valid_address(VITALIK)
        assert is_valid_address("0x" + "a" * 40)
        assert not is_valid_address("0x123")            # demasiado corta
        assert not is_valid_address("d8dA6B" + "0" * 34)  # sin 0x
        assert not is_valid_address("0x" + "z" * 40)    # no hexadecimal
        assert not is_valid_address("")


class TestWalletOverview:

    def _overview(self):
        return GetWalletOverviewUseCase(client=_FakeClient()).execute(chain="ethereum", address=VITALIK)

    @pytest.mark.unit
    def test_native_balance_and_valuation(self):
        r = self._overview()
        assert r["native_balance"] == pytest.approx(5.0)       # 5 ETH desde wei
        assert r["native_value_usd"] == pytest.approx(10000.0)  # 5 × 2000
        assert r["native_symbol"] == "ETH" and r["ens_name"] == "vitalik.eth"
        assert r["is_contract"] is False

    @pytest.mark.unit
    def test_tokens_normalized_filtered_and_sorted(self):
        r = self._overview()
        # 3 ERC-20 con saldo > 0 (NFT y saldo cero excluidos)
        assert r["token_count"] == 3
        symbols = [t["symbol"] for t in r["tokens"]]
        # WETH (4000) antes que USDC (1500); el sin precio al final
        assert symbols == ["WETH", "USDC", "NOP"]
        assert r["tokens"][0]["value_usd"] == pytest.approx(4000.0)
        assert r["tokens"][2]["value_usd"] is None
        # Valor de tokens = 4000 + 1500 (el sin precio no suma)
        assert r["tokens_value_usd"] == pytest.approx(5500.0)

    @pytest.mark.unit
    def test_portfolio_total(self):
        r = self._overview()
        # 10000 (nativo) + 5500 (tokens) = 15500
        assert r["portfolio_value_usd"] == pytest.approx(15500.0)

    @pytest.mark.unit
    def test_transactions_direction(self):
        r = self._overview()
        txs = {t["hash"]: t for t in r["transactions"]}
        assert txs["0xaaa"]["direction"] == "out"   # from = wallet
        assert txs["0xccc"]["direction"] == "in"    # to = wallet
        assert txs["0xaaa"]["value_native"] == pytest.approx(1.0)

    @pytest.mark.unit
    def test_invalid_address_rejected(self):
        r = GetWalletOverviewUseCase(client=_FakeClient()).execute(chain="ethereum", address="0xbad")
        assert "error" in r and "inválida" in r["error"].lower()

    @pytest.mark.unit
    def test_unsupported_chain_rejected(self):
        r = GetWalletOverviewUseCase(client=_FakeClient()).execute(chain="dogechain", address=VITALIK)
        assert "error" in r and "no soportada" in r["error"].lower()

    @pytest.mark.unit
    def test_client_error_surfaced(self):
        class _Boom:
            def get_address(self, *a):
                raise BlockscoutClientError("Timeout al conectar con Blockscout.")
        r = GetWalletOverviewUseCase(client=_Boom()).execute(chain="ethereum", address=VITALIK)
        assert "error" in r and "Timeout" in r["error"]


class TestApi:

    @pytest.mark.integration
    def test_wallet_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/wallet/", {"address": VITALIK}).status_code == 401

    @pytest.mark.integration
    def test_chains_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/wallet/chains/").status_code == 401

    @pytest.mark.integration
    def test_chains_endpoint_lists_networks(self, authenticated_client):
        resp = authenticated_client.get("/api/blockchain/wallet/chains/")
        assert resp.status_code == 200
        slugs = [c["slug"] for c in resp.data["chains"]]
        assert "ethereum" in slugs and "base" in slugs

    @pytest.mark.integration
    def test_wallet_endpoint_returns_overview(self, authenticated_client, monkeypatch):
        monkeypatch.setattr(BlockscoutClient, "get_address", lambda self, c, a: FAKE_ADDRESS)
        monkeypatch.setattr(BlockscoutClient, "get_token_balances", lambda self, c, a: FAKE_TOKENS)
        monkeypatch.setattr(BlockscoutClient, "get_transactions", lambda self, c, a: FAKE_TXS)
        resp = authenticated_client.get("/api/blockchain/wallet/", {"chain": "ethereum", "address": VITALIK})
        assert resp.status_code == 200
        assert resp.data["portfolio_value_usd"] == pytest.approx(15500.0)
        assert resp.data["explorer_url"].endswith(f"/address/{VITALIK}")

    @pytest.mark.integration
    def test_wallet_endpoint_rejects_bad_address(self, authenticated_client):
        resp = authenticated_client.get("/api/blockchain/wallet/", {"chain": "ethereum", "address": "0xbad"})
        assert resp.status_code == 400 and "error" in resp.data
