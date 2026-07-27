"""
test_execution_audit.py — Rastro de auditoría de la ejecución real.
"""

import pytest

from core.domain.services.execution_audit import summarize


class TestSummarize:
    def test_counts_notional_and_reasons(self):
        records = [
            {"status": "sent", "symbol": "BTC/USDT", "fill_price": 100.0, "notional_usd": 100.0, "error": ""},
            {"status": "sent", "symbol": "ETH/USDT", "fill_price": None, "notional_usd": 50.0, "error": ""},
            {"status": "failed", "symbol": "BTC/USDT", "fill_price": None, "notional_usd": 0.0, "error": "insufficient balance"},
            {"status": "blocked", "symbol": "BTC/USDT", "fill_price": None, "notional_usd": 0.0, "error": "daily loss limit"},
            {"status": "blocked", "symbol": "BTC/USDT", "fill_price": None, "notional_usd": 0.0, "error": "daily loss limit"},
        ]
        s = summarize(records)
        assert s["total_attempts"] == 5 and s["sent"] == 2
        assert s["failed"] == 1 and s["blocked"] == 2
        assert s["executed_notional_usd"] == 100.0     # solo la enviada con fill
        assert s["fill_rate_pct"] == 40.0
        assert s["distinct_symbols"] == 2
        assert s["blocked_reasons"][0] == {"reason": "daily loss limit", "count": 2}
        assert s["failed_reasons"][0] == {"reason": "insufficient balance", "count": 1}

    def test_empty(self):
        s = summarize([])
        assert s["total_attempts"] == 0 and s["fill_rate_pct"] is None


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


def _record(account, conn, status, fill=None, error=""):
    from core.infrastructure.persistence.models import LiveOrderRecord
    return LiveOrderRecord.objects.create(
        account=account, connection=conn, symbol=f"{account.asset_symbol}/USDT",
        side="buy", amount=0.001, ref_price=100.0, fill_price=fill,
        notional_usd=0.1, is_testnet=True, status=status, error=error)


@pytest.mark.django_db
class TestUseCaseAndApi:
    def test_audit_summary_and_filter(self, test_user):
        acc, conn = _account(test_user)
        _record(acc, conn, "sent", fill=100.05)
        _record(acc, conn, "failed", error="boom")
        _record(acc, conn, "blocked", error="límite de pérdida diaria")
        from core.application.use_cases.execution_audit import ExecutionAuditUseCase
        out = ExecutionAuditUseCase().execute(owner=test_user)
        assert out["status"] == "OK"
        assert out["summary"]["total_attempts"] == 3 and out["summary"]["blocked"] == 1
        assert len(out["entries"]) == 3
        # Filtro por estado
        blocked = ExecutionAuditUseCase().execute(owner=test_user, status_filter="blocked")
        assert len(blocked["entries"]) == 1 and blocked["entries"][0]["status"] == "blocked"

    def test_empty(self, test_user):
        from core.application.use_cases.execution_audit import ExecutionAuditUseCase
        assert ExecutionAuditUseCase().execute(owner=test_user)["status"] == "EMPTY"

    def test_endpoint(self, authenticated_client):
        r = authenticated_client.get("/api/oms/audit/")
        assert r.status_code == 200 and r.data["status"] in ("EMPTY", "OK")
