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


FAKE_STATS = {
    "gas_prices": {"slow": 1.45, "average": 1.9, "fast": 3.14},
    "gas_price_updated_at": "2026-06-24T14:20:10Z",
    "network_utilization_percentage": 49.42,
    "average_block_time": 12000,
    "coin_price": "1643.1",
    "coin_price_change_percentage": 2.5,
    "total_transactions": "3563224565",
    "total_blocks": "25387579",
    "total_addresses": "662030795",
    "transactions_today": "2869094",
}
FAKE_BALANCE_HISTORY = [
    {"date": "2026-06-22", "value": "2000000000000000000"},  # 2 ETH
    {"date": "2026-06-20", "value": "1000000000000000000"},  # 1 ETH (desordenado a propósito)
    {"date": "2026-06-24", "value": "5000000000000000000"},  # 5 ETH
]


class _FakeClient:
    def get_address(self, chain, address):
        return FAKE_ADDRESS

    def get_token_balances(self, chain, address):
        return FAKE_TOKENS

    def get_transactions(self, chain, address):
        return FAKE_TXS

    def get_chain_stats(self, chain):
        return FAKE_STATS

    def get_balance_history(self, chain, address):
        return FAKE_BALANCE_HISTORY


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


class TestChainHealth:

    def _health(self, chain="ethereum"):
        from core.application.use_cases.get_chain_health import GetChainHealthUseCase
        return GetChainHealthUseCase(client=_FakeClient()).execute(chain=chain)

    @pytest.mark.unit
    def test_gas_and_network_normalized(self):
        r = self._health()
        assert r["gas_average"] == pytest.approx(1.9)
        assert r["block_time_sec"] == pytest.approx(12.0)   # 12000 ms → 12 s
        assert r["coin_price_usd"] == pytest.approx(1643.1)
        assert r["network_utilization_pct"] == pytest.approx(49.42)

    @pytest.mark.unit
    def test_gas_level_is_chain_aware(self):
        # 1.9 Gwei en Ethereum (umbral cheap=10) → barato
        assert self._health("ethereum")["gas_level"] == "cheap"
        # Mismo 1.9 Gwei en Base (umbral high=0.5) → caro
        assert self._health("base")["gas_level"] == "high"

    @pytest.mark.unit
    def test_unsupported_chain_rejected(self):
        assert "error" in self._health("dogechain")


class TestBalanceHistory:

    def _history(self):
        from core.application.use_cases.get_wallet_overview import GetWalletBalanceHistoryUseCase
        return GetWalletBalanceHistoryUseCase(client=_FakeClient()).execute(chain="ethereum", address=VITALIK)

    @pytest.mark.unit
    def test_history_sorted_and_valued(self):
        r = self._history()
        dates = [p["date"] for p in r["history"]]
        assert dates == ["2026-06-20", "2026-06-22", "2026-06-24"]   # ordenado por fecha
        assert r["history"][0]["balance"] == pytest.approx(1.0)
        # valorado al precio actual (2000)
        assert r["history"][2]["value_usd_at_today_price"] == pytest.approx(10000.0)

    @pytest.mark.unit
    def test_invalid_address_rejected(self):
        from core.application.use_cases.get_wallet_overview import GetWalletBalanceHistoryUseCase
        r = GetWalletBalanceHistoryUseCase(client=_FakeClient()).execute(chain="ethereum", address="0xbad")
        assert "error" in r


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

    @pytest.mark.integration
    def test_health_endpoint_returns_gas(self, authenticated_client, monkeypatch):
        monkeypatch.setattr(BlockscoutClient, "get_chain_stats", lambda self, c: FAKE_STATS)
        resp = authenticated_client.get("/api/blockchain/health/", {"chain": "ethereum"})
        assert resp.status_code == 200
        assert resp.data["gas_level"] == "cheap" and resp.data["gas_average"] == pytest.approx(1.9)

    @pytest.mark.integration
    def test_health_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/health/").status_code == 401

    @pytest.mark.integration
    def test_balance_history_endpoint(self, authenticated_client, monkeypatch):
        monkeypatch.setattr(BlockscoutClient, "get_balance_history", lambda self, c, a: FAKE_BALANCE_HISTORY)
        monkeypatch.setattr(BlockscoutClient, "get_address", lambda self, c, a: FAKE_ADDRESS)
        resp = authenticated_client.get("/api/blockchain/wallet/history/", {"chain": "ethereum", "address": VITALIK})
        assert resp.status_code == 200 and resp.data["points"] == 3
        assert resp.data["history"][0]["date"] == "2026-06-20"
