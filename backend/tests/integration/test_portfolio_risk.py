"""
tests/integration/test_portfolio_risk.py — Riesgo agregado del libro (caso de uso).

Verifica la agregación de exposición por los tres libros (manual LONG/SHORT +
paper + real), el VaR/CVaR sobre el almacén histórico propio, la exclusión
honesta de activos sin histórico y el endpoint.
"""

import time

import numpy as np
import pytest
from django.utils import timezone

from core.application.use_cases.portfolio_risk import PortfolioRiskUseCase

_D = 86_400_000  # 1 día en ms


def _seed_history(symbol: str, n: int, seed: int) -> None:
    from core.application.use_cases import ohlcv_store
    from core.infrastructure.persistence.models import OhlcvCandle

    rng = np.random.default_rng(seed)
    now = int(time.time() * 1000)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.03, n)))
    rows = [
        OhlcvCandle(symbol=symbol, interval="1d", open_time=now - (n - i) * _D,
                    open=c, high=c * 1.01, low=c * 0.99, close=c, volume=1000.0,
                    source="test")
        for i, c in enumerate(closes)
    ]
    OhlcvCandle.objects.bulk_create(rows)
    assert ohlcv_store.load_dataframe(symbol, "1d", n).shape[0] == n


@pytest.fixture
def book(db, test_user):
    """Un libro con exposición en los tres canales."""
    from core.infrastructure.persistence.models import (
        CryptoAsset, PaperTradingAccount, Position, StrategyDefinition,
    )

    btc = CryptoAsset.objects.create(symbol="BTC", name="Bitcoin", current_price=50000)
    eth = CryptoAsset.objects.create(symbol="ETH", name="Ethereum", current_price=3000)

    # Manual: LONG 0.5 BTC (=25 000) y SHORT 2 ETH (=−6 000)
    Position.objects.create(user=test_user, asset=btc, direction="LONG", status="OPEN",
                            avg_entry_price=48000, open_quantity="0.5", initial_quantity="0.5",
                            opened_at=timezone.now())
    Position.objects.create(user=test_user, asset=eth, direction="SHORT", status="OPEN",
                            avg_entry_price=3100, open_quantity="2", initial_quantity="2",
                            opened_at=timezone.now())

    # Paper: posición abierta de 0.1 BTC marcada a 50 000 (=5 000) + real 0.02 BTC (=1 000)
    strat = StrategyDefinition.objects.create(
        asset=btc, name="s", spec={"x": 1}, spec_hash="h", interval="1d")
    PaperTradingAccount.objects.create(
        strategy=strat, owner=test_user, asset_symbol="BTC", interval="1d",
        units=0.1, last_price=50000.0, is_active=True,
        live_enabled=True, live_base_position=0.02, live_cap_usd=1000.0,
    )
    return test_user


class TestAggregation:

    @pytest.mark.integration
    def test_signed_exposure_across_three_books(self, book):
        _seed_history("BTC", 300, seed=1)
        _seed_history("ETH", 300, seed=2)
        out = PortfolioRiskUseCase().execute(owner=book)
        assert out["status"] == "OK"
        by_symbol = {r["symbol"]: r for r in out["exposures"]}
        # BTC: 25 000 (manual) + 5 000 (paper) + 1 000 (real) = 31 000
        assert by_symbol["BTC"]["net_usd"] == pytest.approx(31000.0, abs=1.0)
        assert by_symbol["BTC"]["by_book"] == {"manual": 25000.0, "paper": 5000.0, "live": 1000.0}
        # ETH: SHORT 2 × 3000 = −6 000
        assert by_symbol["ETH"]["net_usd"] == pytest.approx(-6000.0, abs=1.0)
        # Bruto = 37 000, neto = 25 000
        assert out["gross_usd"] == pytest.approx(37000.0, abs=1.0)
        assert out["net_usd"] == pytest.approx(25000.0, abs=1.0)
        assert out["long_usd"] == pytest.approx(31000.0) and out["short_usd"] == pytest.approx(-6000.0)

    @pytest.mark.integration
    def test_var_and_stress_present_with_history(self, book):
        _seed_history("BTC", 300, seed=3)
        _seed_history("ETH", 300, seed=4)
        out = PortfolioRiskUseCase().execute(owner=book)
        assert out["var"]["status"] == "OK" and out["var"]["var95_usd"] > 0
        assert out["var_symbols_excluded"] == []
        windows = {sc["window_days"] for sc in out["stress"]}
        assert windows == {1, 7, 30}

    @pytest.mark.integration
    def test_asset_without_history_excluded_from_var_not_exposure(self, book, monkeypatch):
        _seed_history("BTC", 300, seed=5)   # ETH sin histórico
        # Evitar que el fetcher remoto rescate a ETH en el test
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda *a, **kw: None,
        )
        out = PortfolioRiskUseCase().execute(owner=book)
        assert "ETH" in out["var_symbols_excluded"]
        # …pero ETH SIGUE contando en la exposición del libro
        assert any(r["symbol"] == "ETH" for r in out["exposures"])

    @pytest.mark.integration
    def test_empty_book(self, db, test_user):
        out = PortfolioRiskUseCase().execute(owner=test_user)
        assert out["status"] == "EMPTY" and out["gross_usd"] == 0.0


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/portfolio/risk/").status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_risk(self, authenticated_client):
        resp = authenticated_client.get("/api/portfolio/risk/")
        assert resp.status_code == 200
        assert set(resp.data) >= {"status", "exposures", "gross_usd", "net_usd"}
