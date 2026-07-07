"""
tests/integration/test_oms.py — OMS delgado (roadmap institucional #2).

Verifica: slippage real medido por orden y agregado, límite de pérdida diaria
global (bloquea compras, nunca ventas, sin desactivar la promoción),
reconciliación posición esperada ↔ balance real con tolerancia, y el endpoint
de la política de riesgo.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.application.use_cases.paper_trading import (
    LiveOrdersUseCase, ReconcileLivePositionsUseCase, _apply_signal,
    _mirror_live, daily_live_realized_pnl,
)


def _account(test_user, symbol="BTC", cap=100.0):
    from core.infrastructure.persistence.models import (
        CryptoAsset, ExchangeConnection, PaperTradingAccount, StrategyDefinition,
    )
    from core.infrastructure.security.crypto import encrypt_secret

    asset, _ = CryptoAsset.objects.get_or_create(symbol=symbol, defaults={"name": symbol})
    strat = StrategyDefinition.objects.create(
        asset=asset, name="s", spec={"x": 1}, spec_hash=f"h{symbol}", interval="1d",
    )
    conn = ExchangeConnection.objects.create(
        owner=test_user, exchange="binance",
        api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"),
    )
    return PaperTradingAccount.objects.create(
        strategy=strat, owner=test_user, asset_symbol=symbol, interval="1d",
        initial_capital=10000.0, cash=10000.0,
        live_connection=conn, live_enabled=True, live_cap_usd=cap,
    ), conn


def _record(account, conn, side, amount, ref, fill, days_ago=0, status="sent"):
    from core.infrastructure.persistence.models import LiveOrderRecord
    r = LiveOrderRecord.objects.create(
        account=account, connection=conn, symbol=f"{account.asset_symbol}/USDT",
        side=side, amount=amount, ref_price=ref, fill_price=fill,
        notional_usd=round(amount * ref, 2), is_testnet=True, status=status,
    )
    if days_ago:
        LiveOrderRecord.objects.filter(id=r.id).update(
            created_at=timezone.now() - timedelta(days=days_ago))
    return r


class TestSlippage:

    @pytest.mark.integration
    def test_slippage_signed_per_side_and_aggregated(self, db, test_user):
        acc, conn = _account(test_user)
        # Compra 2 bps peor que la referencia; venta 4 bps peor (fill más bajo)
        _record(acc, conn, "buy", 0.001, 100000.0, 100020.0)
        _record(acc, conn, "sell", 0.001, 100000.0, 99960.0)
        out = LiveOrdersUseCase().execute(owner=test_user, account_id=acc.id)
        by_side = {i["side"]: i for i in out["orders"]}
        assert by_side["buy"]["slippage_bps"] == pytest.approx(2.0)
        assert by_side["sell"]["slippage_bps"] == pytest.approx(4.0)
        assert out["slippage"]["n_filled"] == 2
        assert out["slippage"]["avg_slippage_bps"] == pytest.approx(3.0)
        assert out["slippage"]["modeled_slippage_bps"] == 5.0


class TestDailyLossLimit:

    def _lose_today(self, acc, conn, loss_usd):
        """Compra ayer, venta HOY con pérdida `loss_usd` (nocional 1000)."""
        _record(acc, conn, "buy", 0.01, 100000.0, 100000.0, days_ago=1)
        _record(acc, conn, "sell", 0.01, 100000.0 - loss_usd * 100, 100000.0 - loss_usd * 100)

    @pytest.mark.integration
    def test_daily_pnl_counts_only_today_sells(self, db, test_user):
        acc, conn = _account(test_user)
        self._lose_today(acc, conn, loss_usd=60.0)
        assert daily_live_realized_pnl(test_user) == pytest.approx(-60.0, abs=0.01)

    @pytest.mark.integration
    def test_limit_blocks_buys_but_never_sells(self, db, test_user):
        from core.infrastructure.persistence.models import LiveOrderRecord, LiveRiskPolicy

        acc, conn = _account(test_user)
        LiveRiskPolicy.objects.create(owner=test_user, daily_loss_limit_usd=50.0)
        self._lose_today(acc, conn, loss_usd=60.0)   # pérdida hoy: −60 < −50

        sent_orders = []
        class _Broker:
            def create_order(self, symbol, side, otype, amount, price=None):
                sent_orders.append(side)
                return {"id": "1", "average": 100000.0}

        # COMPRA: bloqueada (registro "blocked", promoción sigue activa)
        trade = _apply_signal(acc, "BUY", price=100000.0)
        _mirror_live(acc, trade, 100000.0, broker_factory=lambda c: _Broker())
        assert sent_orders == []
        blocked = LiveOrderRecord.objects.filter(account=acc, status="blocked").first()
        assert blocked is not None and "Límite de pérdida diaria" in blocked.error
        assert acc.live_enabled is True          # no es un kill-switch

        # VENTA: siempre permitida (reducir exposición jamás se bloquea)
        acc.live_base_position = 0.01
        trade = _apply_signal(acc, "SELL", price=100000.0)
        _mirror_live(acc, trade, 100000.0, broker_factory=lambda c: _Broker())
        assert sent_orders == ["sell"]

    @pytest.mark.integration
    def test_no_policy_means_no_blocking(self, db, test_user):
        acc, conn = _account(test_user)
        self._lose_today(acc, conn, loss_usd=500.0)
        sent = []
        class _Broker:
            def create_order(self, *a, **kw):
                sent.append(1); return {"id": "1", "average": 100000.0}
        trade = _apply_signal(acc, "BUY", price=100000.0)
        _mirror_live(acc, trade, 100000.0, broker_factory=lambda c: _Broker())
        assert sent == [1]


class TestReconciliation:

    @pytest.mark.integration
    def test_mismatch_recorded_and_match_marks_zero(self, db, test_user, monkeypatch):
        acc, _ = _account(test_user)
        acc.live_base_position = 0.5
        acc.save(update_fields=["live_base_position"])
        acc2, _ = _account(test_user, symbol="ETH")
        acc2.live_base_position = 2.0
        acc2.save(update_fields=["live_base_position"])

        notified = []
        monkeypatch.setattr(
            "core.interfaces.ws.broadcast.broadcast_notification",
            lambda user_id, data: notified.append(user_id) or True,
        )

        class _Broker:
            def __init__(self, balances): self._b = balances
            def fetch_balance(self): return self._b

        def factory(conn):
            # BTC: cuadra (0.5); ETH: el exchange solo tiene 1.2 (Δ −0.8)
            return _Broker([
                {"asset": "BTC", "free": 0.5, "used": 0.0, "total": 0.5},
                {"asset": "ETH", "free": 1.0, "used": 0.2, "total": 1.2},
            ])

        out = ReconcileLivePositionsUseCase(broker_factory=factory).execute()
        assert out == {"checked": 2, "mismatches": 1}
        acc.refresh_from_db(); acc2.refresh_from_db()
        assert acc.live_discrepancy == 0.0 and acc.live_reconciled_at is not None
        assert acc2.live_discrepancy == pytest.approx(-0.8)
        assert notified == [test_user.id]


class TestRiskPolicyApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/trading/risk-policy/").status_code == 401

    @pytest.mark.integration
    def test_get_put_roundtrip_with_clamp(self, authenticated_client):
        resp = authenticated_client.get("/api/trading/risk-policy/")
        assert resp.status_code == 200 and resp.data["daily_loss_limit_usd"] is None

        put = authenticated_client.put("/api/trading/risk-policy/",
                                       {"daily_loss_limit_usd": 3}, format="json")
        assert put.status_code == 200 and put.data["daily_loss_limit_usd"] == 10.0  # clamp mínimo

        off = authenticated_client.put("/api/trading/risk-policy/",
                                       {"daily_loss_limit_usd": None}, format="json")
        assert off.status_code == 200 and off.data["daily_loss_limit_usd"] is None
