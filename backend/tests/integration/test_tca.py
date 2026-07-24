"""
test_tca.py — Analítica de coste de ejecución (TCA).
"""

import pytest

from core.domain.services.tca import order_cost, aggregate_tca


# ── Dominio ─────────────────────────────────────────────────────────

class TestDomain:
    def test_buy_worse_is_positive_cost(self):
        c = order_cost("buy", 100_000.0, 100_020.0, 100.0)
        assert c["slippage_bps"] == pytest.approx(2.0)
        assert c["cost_usd"] == pytest.approx(0.02)

    def test_sell_lower_is_positive_cost(self):
        c = order_cost("sell", 100_000.0, 99_960.0, 100.0)
        assert c["slippage_bps"] == pytest.approx(4.0)

    def test_none_without_fill(self):
        assert order_cost("buy", 100.0, None, 10.0) is None

    def test_aggregate_notional_weighted(self):
        orders = [
            {"side": "buy", "ref_price": 100_000.0, "fill_price": 100_020.0, "notional_usd": 100.0, "symbol": "BTC"},
            {"side": "sell", "ref_price": 100_000.0, "fill_price": 99_960.0, "notional_usd": 100.0, "symbol": "BTC"},
        ]
        out = aggregate_tca(orders, total_attempts=3)
        assert out["status"] == "OK" and out["fills"] == 2
        assert out["avg_slippage_bps"] == pytest.approx(3.0)
        assert out["total_cost_usd"] == pytest.approx(0.06)
        assert out["fill_rate_pct"] == pytest.approx(66.7)
        assert out["worst"]["slippage_bps"] == pytest.approx(4.0)

    def test_empty(self):
        assert aggregate_tca([], total_attempts=0)["status"] == "EMPTY"


# ── Integración ─────────────────────────────────────────────────────

def _account(test_user, symbol="BTC"):
    from core.infrastructure.persistence.models import (
        CryptoAsset, ExchangeConnection, PaperTradingAccount, StrategyDefinition,
    )
    from core.infrastructure.security.crypto import encrypt_secret
    asset, _ = CryptoAsset.objects.get_or_create(symbol=symbol, defaults={"name": symbol})
    strat = StrategyDefinition.objects.create(
        asset=asset, name="s", spec={"x": 1}, spec_hash=f"h{symbol}", interval="1d")
    conn = ExchangeConnection.objects.create(
        owner=test_user, exchange="binance",
        api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"))
    return PaperTradingAccount.objects.create(
        strategy=strat, owner=test_user, asset_symbol=symbol, interval="1d",
        initial_capital=10000.0, cash=10000.0), conn


def _record(account, conn, side, ref, fill, status="sent"):
    from core.infrastructure.persistence.models import LiveOrderRecord
    return LiveOrderRecord.objects.create(
        account=account, connection=conn, symbol=f"{account.asset_symbol}/USDT",
        side=side, amount=0.001, ref_price=ref, fill_price=fill,
        notional_usd=round(0.001 * ref, 2), is_testnet=True, status=status)


@pytest.mark.django_db
class TestUseCaseAndApi:
    def test_use_case_computes_tca(self, test_user):
        acc, conn = _account(test_user)
        _record(acc, conn, "buy", 100_000.0, 100_020.0)
        _record(acc, conn, "sell", 100_000.0, 99_960.0)
        _record(acc, conn, "buy", 100_000.0, None, status="failed")  # fallida: baja el fill rate
        from core.application.use_cases.tca import ExecutionTcaUseCase
        out = ExecutionTcaUseCase().execute(owner=test_user)
        assert out["status"] == "OK" and out["fills"] == 2
        assert out["avg_slippage_bps"] == pytest.approx(3.0)
        assert out["fill_rate_pct"] == pytest.approx(66.7)

    def test_empty_without_orders(self, test_user):
        from core.application.use_cases.tca import ExecutionTcaUseCase
        assert ExecutionTcaUseCase().execute(owner=test_user)["status"] == "EMPTY"

    def test_endpoint(self, authenticated_client):
        r = authenticated_client.get("/api/oms/tca/")
        assert r.status_code == 200 and r.data["status"] in ("EMPTY", "OK")
