"""
test_derivatives.py — Microestructura de perpetuos (funding / basis / OI).
"""

from unittest.mock import patch

import pytest

from core.domain.services.derivatives_metrics import compute_derivatives_snapshot

_PREMIUM = {"symbol": "BTCUSDT", "markPrice": "65200", "indexPrice": "65000",
            "lastFundingRate": "0.0005"}
_OI = {"symbol": "BTCUSDT", "openInterest": "1000"}


class TestDomain:
    def test_funding_annualized_and_basis(self):
        s = compute_derivatives_snapshot(_PREMIUM, _OI)
        assert s["available"] is True
        assert s["funding_annualized_pct"] == round(0.0005 * 3 * 365 * 100, 2)  # 54.75
        assert s["funding_verdict"] == "LARGOS SOBRECALENTADOS"
        assert abs(s["basis_pct"] - (200 / 65000 * 100)) < 1e-3   # redondeado a 4 dec.
        assert s["basis_verdict"] == "contango"
        assert s["open_interest_usd"] == 1000 * 65200

    def test_hot_short_funding(self):
        s = compute_derivatives_snapshot({**_PREMIUM, "lastFundingRate": "-0.0005"}, _OI)
        assert s["funding_verdict"] == "CORTOS SOBRECALENTADOS"

    def test_neutral_funding(self):
        s = compute_derivatives_snapshot({**_PREMIUM, "lastFundingRate": "0.00001"}, _OI)
        assert s["funding_verdict"] == "NEUTRAL"

    def test_backwardation(self):
        s = compute_derivatives_snapshot({**_PREMIUM, "markPrice": "64500", "indexPrice": "65000"}, _OI)
        assert s["basis_verdict"] in ("backwardation", "backwardation fuerte")

    def test_unavailable_without_mark(self):
        s = compute_derivatives_snapshot({"lastFundingRate": "0.0001"}, _OI)
        assert s["available"] is False


class TestUseCase:
    def test_maps_symbol_and_builds_snapshot(self):
        with patch("core.infrastructure.external_apis.binance_client.BinancePublicClient.premium_index",
                   return_value=_PREMIUM), \
             patch("core.infrastructure.external_apis.binance_client.BinancePublicClient.open_interest",
                   return_value=_OI):
            from core.application.use_cases.get_derivatives import GetDerivativesUseCase
            out = GetDerivativesUseCase().execute("btc")
        assert out["available"] is True
        assert out["perp_symbol"] == "BTCUSDT" and out["symbol"] == "BTC"

    def test_graceful_when_source_fails(self):
        from core.infrastructure.external_apis.binance_client import BinanceClientError
        with patch("core.infrastructure.external_apis.binance_client.BinancePublicClient.premium_index",
                   side_effect=BinanceClientError("boom")):
            from core.application.use_cases.get_derivatives import GetDerivativesUseCase
            out = GetDerivativesUseCase().execute("DOGE")
        assert out["available"] is False and out["symbol"] == "DOGE"


@pytest.mark.django_db
class TestApi:
    def test_endpoint(self, authenticated_client):
        with patch("core.infrastructure.external_apis.binance_client.BinancePublicClient.premium_index",
                   return_value=_PREMIUM), \
             patch("core.infrastructure.external_apis.binance_client.BinancePublicClient.open_interest",
                   return_value=_OI):
            r = authenticated_client.get("/api/analysis/derivatives/?asset_symbol=BTC")
        assert r.status_code == 200
        assert r.data["available"] is True and r.data["funding_verdict"] == "LARGOS SOBRECALENTADOS"

    def test_endpoint_requires_symbol(self, authenticated_client):
        r = authenticated_client.get("/api/analysis/derivatives/")
        assert r.status_code == 400
