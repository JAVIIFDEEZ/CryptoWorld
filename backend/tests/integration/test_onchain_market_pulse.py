"""
tests/integration/test_onchain_market_pulse.py — Pulso on-chain de mercado.
"""

from datetime import timedelta

import pytest
from django.utils import timezone


def _mv(chain, symbol, usd, direction, from_label="", to_label="", hours_ago=1):
    from core.infrastructure.persistence.models import WhaleMovementSnapshot
    return WhaleMovementSnapshot.objects.create(
        chain=chain, symbol=symbol, amount=usd / 1000, value_usd=usd,
        from_address="0x" + "a" * 40, to_address="0x" + "b" * 40,
        from_label=from_label, to_label=to_label, direction=direction,
        tx_hash=f"0x{chain}{symbol}{usd}{direction}{from_label}{to_label}"[:80],
        moved_at=timezone.now() - timedelta(hours=hours_ago),
    )


class TestMarketPulse:

    @pytest.mark.integration
    def test_aggregates_across_chains_with_verdict(self, db):
        from core.application.use_cases.onchain_market_pulse import OnChainMarketPulseUseCase

        # Retiradas dominan (acumulación): 4M salen, 1M entra; ≥5 clasificados
        _mv("ethereum", "ETH", 1_500_000, "from_exchange", from_label="Binance 14")
        _mv("ethereum", "ETH", 500_000, "from_exchange", from_label="Binance 2")
        _mv("base", "ETH", 1_000_000, "from_exchange", from_label="Coinbase 3")
        _mv("base", "ETH", 1_000_000, "from_exchange", from_label="Coinbase 5")
        _mv("arbitrum", "USDC", 1_000_000, "to_exchange", to_label="Binance 8")
        out = OnChainMarketPulseUseCase().execute(hours=24)

        assert out["status"] == "OK"
        assert out["verdict"] == "ACUMULACION"
        assert out["outflow_usd"] == 4_000_000.0 and out["inflow_usd"] == 1_000_000.0
        assert out["net_flow_usd"] == 3_000_000.0 and out["pressure"] > 0
        chains = {c["chain"] for c in out["chains"]}
        assert {"ethereum", "base", "arbitrum"} <= chains
        # Exchanges agregados por entidad (Binance, no 'Binance 14'/'Binance 8')
        exchanges = {e["exchange"] for e in out["exchanges"]}
        assert "Binance" in exchanges and "Coinbase" in exchanges
        assert len(out["series"]) >= 1

    @pytest.mark.integration
    def test_insufficient_when_empty(self, db):
        from core.application.use_cases.onchain_market_pulse import OnChainMarketPulseUseCase
        assert OnChainMarketPulseUseCase().execute()["status"] == "INSUFICIENTE"

    @pytest.mark.integration
    def test_window_excludes_old_movements(self, db):
        from core.application.use_cases.onchain_market_pulse import OnChainMarketPulseUseCase
        _mv("ethereum", "ETH", 5_000_000, "from_exchange", from_label="Kraken 2", hours_ago=100)
        assert OnChainMarketPulseUseCase().execute(hours=24)["status"] == "INSUFICIENTE"


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/pulse/").status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_pulse(self, authenticated_client, db):
        from django.core.cache import cache
        cache.delete("onchain_pulse:24")
        _mv("ethereum", "ETH", 1_500_000, "to_exchange", to_label="Binance 1")
        _mv("ethereum", "ETH", 500_000, "from_exchange", from_label="Binance 1")
        resp = authenticated_client.get("/api/blockchain/pulse/")
        assert resp.status_code == 200
        assert set(resp.data) >= {"status", "verdict", "net_flow_usd", "chains", "series"}
