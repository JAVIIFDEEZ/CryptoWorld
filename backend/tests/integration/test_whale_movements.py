"""
tests/integration/test_whale_movements.py — Mayores movimientos on-chain.

Verifica que el feed combina transferencias nativas y de tokens, las valora en
USD, descarta las pequeñas, ordena por valor, extrae etiquetas de entidad y
respeta el límite. El cliente Blockscout se mockea.
"""

import pytest

from core.application.use_cases.get_whale_movements import GetWhaleMovementsUseCase

FAKE_STATS = {"coin_price": "2000.0"}

# Transacciones nativas (forma REST v2): from/to objetos, value en wei.
FAKE_NATIVE = [
    # 100 ETH × 2000 = 200.000 USD, de un exchange etiquetado
    {"hash": "0xa", "from": {"hash": "0xFROM", "name": "Binance"}, "to": {"hash": "0xTO"},
     "value": "100000000000000000000", "method": "transfer", "timestamp": "2026-06-24T10:00:00Z"},
    # 0.5 ETH × 2000 = 1.000 USD → por debajo del umbral
    {"hash": "0xb", "from": {"hash": "0xX"}, "to": {"hash": "0xY"},
     "value": "500000000000000000", "method": None, "timestamp": "2026-06-24T10:01:00Z"},
    # interacción de contrato con value 0 → se ignora
    {"hash": "0xc", "from": {"hash": "0xX"}, "to": {"hash": "0xCONTRACT", "is_contract": True},
     "value": "0", "method": "approve", "timestamp": "2026-06-24T10:02:00Z"},
]
# Transferencias de tokens: total.value + token con decimals/exchange_rate.
FAKE_TOKENS = [
    # 1.000.000 USDC × 1 = 1.000.000 USD (el mayor) → a Coinbase etiquetado
    {"tx_hash": "0xd", "from": {"hash": "0xWHALE"}, "to": {"hash": "0xCB", "name": "Coinbase"},
     "token": {"symbol": "USDC", "name": "USD Coin", "decimals": "6", "exchange_rate": "1.0", "type": "ERC-20"},
     "total": {"value": "1000000000000", "decimals": "6"}, "timestamp": "2026-06-24T09:00:00Z"},
    # NFT (ERC-721) → se ignora
    {"tx_hash": "0xe", "from": {"hash": "0xA"}, "to": {"hash": "0xB"},
     "token": {"symbol": "PUNK", "type": "ERC-721"}, "total": {"token_id": "42"},
     "timestamp": "2026-06-24T09:01:00Z"},
    # token sin precio → value_usd None → se descarta del feed
    {"tx_hash": "0xf", "from": {"hash": "0xA"}, "to": {"hash": "0xB"},
     "token": {"symbol": "NOP", "decimals": "18", "exchange_rate": None, "type": "ERC-20"},
     "total": {"value": "5000000000000000000000", "decimals": "18"}, "timestamp": "2026-06-24T09:02:00Z"},
]


class _FakeClient:
    def get_chain_stats(self, chain):
        return FAKE_STATS

    def get_recent_transactions(self, chain, pages=2):
        return FAKE_NATIVE

    def get_recent_token_transfers(self, chain, pages=2):
        return FAKE_TOKENS


class TestWhaleMovements:

    def _run(self, min_usd=100_000, limit=25):
        return GetWhaleMovementsUseCase(client=_FakeClient()).execute(
            chain="ethereum", min_usd=min_usd, limit=limit,
        )

    @pytest.mark.unit
    def test_combines_and_sorts_by_usd(self):
        r = self._run()
        # Solo 2 superan el umbral (USDC 1M y ETH 200k); ordenados desc
        assert r["count"] == 2
        assert r["movements"][0]["symbol"] == "USDC"
        assert r["movements"][0]["value_usd"] == pytest.approx(1_000_000.0)
        assert r["movements"][1]["symbol"] == "ETH"
        assert r["movements"][1]["value_usd"] == pytest.approx(200_000.0)

    @pytest.mark.unit
    def test_threshold_filters_small_moves(self):
        r = self._run(min_usd=500_000)
        assert r["count"] == 1 and r["movements"][0]["symbol"] == "USDC"

    @pytest.mark.unit
    def test_zero_value_and_nft_and_unpriced_excluded(self):
        r = self._run(min_usd=0)
        symbols = [m["symbol"] for m in r["movements"]]
        assert "PUNK" not in symbols      # NFT
        assert "NOP" not in symbols       # sin precio
        # las 2 nativas con value > 0 aparecen; la de contrato (value 0) se excluye
        assert symbols.count("ETH") == 2

    @pytest.mark.unit
    def test_entity_labels_extracted(self):
        r = self._run()
        usdc = r["movements"][0]
        eth = r["movements"][1]
        assert usdc["to"]["label"] == "Coinbase"
        assert eth["from"]["label"] == "Binance"

    @pytest.mark.unit
    def test_limit_caps_results(self):
        r = self._run(min_usd=0, limit=1)
        assert r["count"] == 1

    @pytest.mark.unit
    def test_explorer_url_built(self):
        r = self._run()
        assert r["movements"][0]["explorer_url"].endswith("/tx/0xd")

    @pytest.mark.unit
    def test_unsupported_chain(self):
        r = GetWhaleMovementsUseCase(client=_FakeClient()).execute(chain="dogechain")
        assert "error" in r


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/movements/").status_code == 401

    @pytest.mark.integration
    def test_returns_movements(self, authenticated_client, monkeypatch):
        from core.infrastructure.external_apis.blockscout_client import BlockscoutClient
        monkeypatch.setattr(BlockscoutClient, "get_chain_stats", lambda self, c: FAKE_STATS)
        monkeypatch.setattr(BlockscoutClient, "get_recent_transactions", lambda self, c, pages=2: FAKE_NATIVE)
        monkeypatch.setattr(BlockscoutClient, "get_recent_token_transfers", lambda self, c, pages=2: FAKE_TOKENS)
        resp = authenticated_client.get("/api/blockchain/movements/", {"chain": "ethereum", "min_usd": 100000})
        assert resp.status_code == 200
        assert resp.data["count"] == 2 and resp.data["movements"][0]["symbol"] == "USDC"
