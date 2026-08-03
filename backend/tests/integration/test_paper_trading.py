"""
tests/integration/test_paper_trading.py — Cartera virtual que sigue una
estrategia generada (verificación hacia delante, sin riesgo).

Verifica la mecánica de la cartera (abrir en BUY, cerrar en SELL con costes y
P&L realizado), la evaluación periódica end-to-end y los endpoints REST.
"""

import numpy as np
import pandas as pd
import pytest
from django.utils import timezone

from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult
from core.application.use_cases.paper_trading import (
    EvaluatePaperTradingUseCase, PaperTradingDetailUseCase, _apply_signal, _check_decay,
)


@pytest.fixture
def strategy(db):
    """Estrategia RSI mínima asociada a un activo BTC."""
    from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition
    asset = CryptoAsset.objects.create(symbol="BTC", name="Bitcoin")
    spec = {
        "entry": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 30.0}]},
        "exit": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 70.0}]},
    }
    return StrategyDefinition.objects.create(
        asset=asset, name="RSI reversal", spec=spec, spec_hash="abc", interval="1d",
        passed_gating=True, status="validated",
    )


def _account(strategy, owner=None, capital=10000.0):
    from core.infrastructure.persistence.models import PaperTradingAccount
    return PaperTradingAccount.objects.create(
        strategy=strategy, owner=owner, asset_symbol="BTC", interval="1d",
        initial_capital=capital, cash=capital,
    )


class TestMechanics:

    @pytest.mark.integration
    def test_buy_opens_position_and_consumes_cash(self, strategy):
        acc = _account(strategy)
        trade = _apply_signal(acc, "BUY", price=100.0)
        assert trade is not None and trade.side == "BUY"
        assert acc.units > 0 and acc.cash == 0.0
        # El coste (comisión+slippage) hace que el patrimonio inicial baje algo.
        assert acc.equity < acc.initial_capital
        # entry_price incluye el coste → mayor que el precio de mercado.
        assert acc.entry_price > 100.0

    @pytest.mark.integration
    def test_sell_closes_with_profit(self, strategy):
        acc = _account(strategy)
        _apply_signal(acc, "BUY", price=100.0)
        units = acc.units
        trade = _apply_signal(acc, "SELL", price=130.0)   # +30% de mercado
        assert trade is not None and trade.side == "SELL"
        assert acc.units == 0.0 and acc.entry_price is None
        assert acc.trades_count == 1 and acc.wins == 1
        assert acc.realized_pnl > 0 and trade.pnl_pct > 0
        # Tras cerrar, todo es efectivo y el patrimonio supera el inicial.
        assert acc.cash > acc.initial_capital and acc.units == 0
        assert trade.units == pytest.approx(units)

    @pytest.mark.integration
    def test_sell_closes_with_loss_counts_no_win(self, strategy):
        acc = _account(strategy)
        _apply_signal(acc, "BUY", price=100.0)
        _apply_signal(acc, "SELL", price=80.0)            # -20%
        assert acc.trades_count == 1 and acc.wins == 0
        assert acc.realized_pnl < 0

    @pytest.mark.integration
    def test_buy_when_already_in_position_is_noop(self, strategy):
        acc = _account(strategy)
        _apply_signal(acc, "BUY", price=100.0)
        units_before = acc.units
        trade = _apply_signal(acc, "BUY", price=110.0)
        assert trade is None and acc.units == units_before

    @pytest.mark.integration
    def test_hold_marks_to_market_without_trading(self, strategy):
        acc = _account(strategy)
        _apply_signal(acc, "BUY", price=100.0)
        trade = _apply_signal(acc, "HOLD", price=150.0)
        assert trade is None
        assert acc.last_price == 150.0
        assert acc.equity == pytest.approx(acc.units * 150.0)   # latente, sin cerrar


def _df_with_signal(rsi_target: str, n=120):
    """OHLCV diseñado para que el RSI dispare entrada (sobreventa) o salida."""
    if rsi_target == "buy":
        close = np.linspace(200, 100, n)        # caída sostenida → RSI bajo → entrada
    else:
        close = np.linspace(100, 200, n)        # subida sostenida → RSI alto → salida
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(n)],
        "open": close, "high": close + 1, "low": close - 1, "close": close,
        "volume": [1000.0] * n,
    })


class TestEvaluateUseCase:

    @pytest.mark.integration
    def test_evaluation_opens_position_on_buy_signal(self, strategy, monkeypatch):
        acc = _account(strategy)
        df = _df_with_signal("buy")
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=200, **kw: OhlcvFetchResult(df=df, source="binance"),
        )
        out = EvaluatePaperTradingUseCase().execute()
        assert out["evaluated"] == 1
        acc.refresh_from_db()
        assert acc.last_signal == "BUY" and acc.units > 0
        assert acc.trades.filter(side="BUY").exists()

    @pytest.mark.integration
    def test_evaluation_records_equity_snapshot(self, strategy, monkeypatch):
        acc = _account(strategy)
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=200, **kw: OhlcvFetchResult(df=_df_with_signal("buy"), source="binance"),
        )
        EvaluatePaperTradingUseCase().execute()
        acc.refresh_from_db()
        assert acc.equity_snapshots.count() == 1   # mark-to-market en cada evaluación
        assert acc.peak_equity >= acc.initial_capital

    @pytest.mark.integration
    def test_inactive_accounts_are_skipped(self, strategy, monkeypatch):
        acc = _account(strategy)
        acc.is_active = False
        acc.save(update_fields=["is_active"])
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=200, **kw: OhlcvFetchResult(df=_df_with_signal("buy"), source="binance"),
        )
        out = EvaluatePaperTradingUseCase().execute()
        assert out["evaluated"] == 0


class TestDecay:

    @pytest.mark.integration
    def test_drawdown_marks_decayed_on_transition(self, strategy):
        from django.utils import timezone
        acc = _account(strategy)
        acc.trades_count = 6
        acc.peak_equity = 12000.0
        acc.cash = 8000.0   # equity 8000 → drawdown 33%, total return -20%
        decayed = _check_decay(acc, timezone.now())
        assert decayed is True and acc.decayed is True and acc.decayed_at is not None

    @pytest.mark.integration
    def test_not_enough_trades_does_not_decay(self, strategy):
        from django.utils import timezone
        acc = _account(strategy)
        acc.trades_count = 2
        acc.peak_equity = 12000.0
        acc.cash = 8000.0
        assert _check_decay(acc, timezone.now()) is False and acc.decayed is False

    @pytest.mark.integration
    def test_healthy_account_does_not_decay(self, strategy):
        from django.utils import timezone
        acc = _account(strategy)
        acc.trades_count = 8
        acc.peak_equity = 10500.0
        acc.cash = 10400.0   # casi en máximos
        assert _check_decay(acc, timezone.now()) is False

    @pytest.mark.integration
    def test_already_decayed_does_not_retrigger(self, strategy):
        from django.utils import timezone
        acc = _account(strategy)
        acc.trades_count = 6
        acc.peak_equity = 12000.0
        acc.cash = 8000.0
        acc.decayed = True
        assert _check_decay(acc, timezone.now()) is False   # ya decaída: no re-dispara

    @pytest.mark.integration
    def test_evaluation_returns_decayed_pairs(self, strategy, monkeypatch):
        # Cartera ya degradada: la evaluación la marca y la devuelve para reoptimizar.
        acc = _account(strategy)
        acc.trades_count = 6
        acc.peak_equity = 12000.0
        acc.cash = 8000.0
        acc.save(update_fields=["trades_count", "peak_equity", "cash"])
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=200, **kw: OhlcvFetchResult(df=_df_with_signal("sell"), source="binance"),
        )
        out = EvaluatePaperTradingUseCase().execute()
        assert ("BTC", "1d") in out["decayed_pairs"]
        acc.refresh_from_db()
        assert acc.decayed is True


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/strategies/paper/").status_code == 401

    @pytest.mark.integration
    def test_create_lists_and_stop(self, authenticated_client, strategy):
        # Crear cartera
        resp = authenticated_client.post("/api/strategies/paper/", {"strategy_id": strategy.id, "initial_capital": 5000}, format="json")
        assert resp.status_code == 201
        acc_id = resp.data["id"]
        assert resp.data["initial_capital"] == 5000 and resp.data["is_active"] is True

        # Crear de nuevo la misma → no duplica, devuelve la existente (200)
        again = authenticated_client.post("/api/strategies/paper/", {"strategy_id": strategy.id}, format="json")
        assert again.status_code == 200 and again.data["id"] == acc_id

        # Listar
        lst = authenticated_client.get("/api/strategies/paper/")
        assert lst.status_code == 200 and lst.data["count"] == 1

        # Detalle con trades y curva de equity
        det = authenticated_client.get(f"/api/strategies/paper/{acc_id}/")
        assert det.status_code == 200 and "trades" in det.data and "equity_curve" in det.data
        assert "drawdown_pct" in det.data and "decayed" in det.data

        # Detener
        stop = authenticated_client.delete(f"/api/strategies/paper/{acc_id}/")
        assert stop.status_code == 200 and stop.data["is_active"] is False

    @pytest.mark.integration
    def test_create_unknown_strategy_404(self, authenticated_client):
        resp = authenticated_client.post("/api/strategies/paper/", {"strategy_id": 999999}, format="json")
        assert resp.status_code == 404

    @pytest.mark.integration
    def test_detail_of_other_user_not_found(self, authenticated_client, strategy, test_user):
        # Cartera de otro dueño (None) no es accesible
        acc = _account(strategy, owner=None)
        data = PaperTradingDetailUseCase().execute(owner=test_user, account_id=acc.id)
        assert data is None


class _FakeLiveBroker:
    """Broker falso que registra órdenes o falla según se configure."""

    def __init__(self, fail=False):
        self.fail = fail
        self.orders = []

    def create_order(self, symbol, side, order_type, amount, price=None):
        from core.infrastructure.external_apis.ccxt_broker import BrokerError
        if self.fail:
            raise BrokerError("Fondos insuficientes para esta orden.")
        self.orders.append({"symbol": symbol, "side": side, "type": order_type, "amount": amount})
        return {"id": "1", "symbol": symbol, "side": side, "status": "closed"}


def _live_account(strategy, owner, cap=100.0):
    from core.infrastructure.persistence.models import ExchangeConnection, PaperTradingAccount
    from core.infrastructure.security.crypto import encrypt_secret
    conn = ExchangeConnection.objects.create(
        owner=owner, exchange="binance",
        api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"),
        is_testnet=True,
    )
    acc = PaperTradingAccount.objects.create(
        strategy=strategy, owner=owner, asset_symbol="BTC", interval="1d",
        initial_capital=10000.0, cash=10000.0,
        live_connection=conn, live_enabled=True, live_cap_usd=cap,
    )
    return acc, conn


def _incubate(acc):
    """Envejece la cartera para que supere la puerta de incubación.

    Promocionar a real exige un periodo mínimo en simulado con operaciones
    suficientes (ver domain/services/incubation.py). Los tests de este bloque
    verifican OTRAS cosas —el tope de nocional, el kill-switch, la propiedad de
    la conexión—, así que la incubación se da por cumplida en lugar de repetirse
    en cada uno. Su gate tiene sus propios tests en test_incubation.py.
    """
    from datetime import timedelta
    from django.utils import timezone
    from core.infrastructure.persistence.models import PaperTradingAccount

    PaperTradingAccount.objects.filter(id=acc.id).update(
        started_at=timezone.now() - timedelta(days=30), trades_count=10,
    )
    acc.refresh_from_db()
    return acc


class TestLivePromotion:

    @pytest.mark.integration
    def test_buy_mirrors_with_cap(self, strategy, test_user, monkeypatch):
        from core.application.use_cases.paper_trading import EvaluatePaperTradingUseCase
        acc, _ = _live_account(strategy, test_user, cap=100.0)
        broker = _FakeLiveBroker()
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=200, **kw: OhlcvFetchResult(df=_df_with_signal("buy"), source="binance"),
        )
        EvaluatePaperTradingUseCase(broker_factory=lambda c: broker).execute()
        acc.refresh_from_db()
        assert len(broker.orders) == 1
        order = broker.orders[0]
        assert order["symbol"] == "BTC/USDT" and order["side"] == "buy"
        # Nocional capado a 100 USD: amount·precio ≤ 100 (+ redondeo)
        price = acc.last_price
        assert order["amount"] * price <= 100.0 + 1e-6
        assert acc.live_base_position == pytest.approx(order["amount"])
        assert acc.live_enabled is True

    @pytest.mark.integration
    def test_broker_error_triggers_kill_switch(self, strategy, test_user, monkeypatch):
        from core.application.use_cases.paper_trading import EvaluatePaperTradingUseCase
        acc, _ = _live_account(strategy, test_user)
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=200, **kw: OhlcvFetchResult(df=_df_with_signal("buy"), source="binance"),
        )
        EvaluatePaperTradingUseCase(broker_factory=lambda c: _FakeLiveBroker(fail=True)).execute()
        acc.refresh_from_db()
        assert acc.live_enabled is False                       # kill-switch
        assert "desactivada" in acc.live_error.lower()
        assert acc.live_disabled_at is not None                # sello para notificaciones
        # El paper sigue funcionando aunque el espejo falle
        assert acc.units > 0

    @pytest.mark.integration
    def test_reenable_clears_kill_switch_stamp(self, authenticated_client, strategy, test_user):
        from django.utils import timezone
        acc, conn = _live_account(strategy, test_user)
        acc.live_enabled = False
        acc.live_error = "Ejecución real desactivada: fondos insuficientes."
        acc.live_disabled_at = timezone.now()
        acc.save(update_fields=["live_enabled", "live_error", "live_disabled_at"])
        _incubate(acc)

        resp = authenticated_client.post(
            f"/api/strategies/paper/{acc.id}/live/",
            {"enable": True, "connection_id": conn.id, "cap_usd": 50},
            format="json",
        )
        assert resp.status_code == 200
        acc.refresh_from_db()
        assert acc.live_enabled is True
        assert acc.live_error == "" and acc.live_disabled_at is None

    @pytest.mark.integration
    def test_sell_liquidates_exactly_live_position(self, strategy, test_user, monkeypatch):
        from core.application.use_cases.paper_trading import _apply_signal, _mirror_live
        acc, _ = _live_account(strategy, test_user)
        broker = _FakeLiveBroker()
        # Compra en paper con espejo
        trade = _apply_signal(acc, "BUY", price=100.0)
        _mirror_live(acc, trade, 100.0, broker_factory=lambda c: broker)
        bought = acc.live_base_position
        assert bought > 0
        # Venta: liquida exactamente lo comprado en real
        trade = _apply_signal(acc, "SELL", price=120.0)
        _mirror_live(acc, trade, 120.0, broker_factory=lambda c: broker)
        assert broker.orders[-1]["side"] == "sell"
        assert broker.orders[-1]["amount"] == pytest.approx(bought)
        assert acc.live_base_position == 0.0

    @pytest.mark.integration
    def test_promotion_endpoint(self, authenticated_client, strategy, test_user):
        from core.infrastructure.persistence.models import ExchangeConnection
        from core.infrastructure.security.crypto import encrypt_secret
        acc = _incubate(_account(strategy, owner=test_user))
        conn = ExchangeConnection.objects.create(
            owner=test_user, exchange="binance",
            api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"),
        )
        # Activar con tope fuera de rango → se limita
        resp = authenticated_client.post(
            f"/api/strategies/paper/{acc.id}/live/",
            {"enable": True, "connection_id": conn.id, "cap_usd": 999999},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["live_enabled"] is True and resp.data["live_cap_usd"] == 10000.0

        # Desactivar
        off = authenticated_client.post(
            f"/api/strategies/paper/{acc.id}/live/", {"enable": False}, format="json",
        )
        assert off.status_code == 200 and off.data["live_enabled"] is False

    @pytest.mark.integration
    def test_promotion_requires_own_connection(self, authenticated_client, strategy, test_user, db):
        from core.infrastructure.persistence.models import ExchangeConnection, User
        from core.infrastructure.security.crypto import encrypt_secret
        # Incubada, para que el 400 salga por la conexión ajena y no por la
        # puerta de incubación: cada test debe fallar por su motivo.
        acc = _incubate(_account(strategy, owner=test_user))
        other = User.objects.create_user(email="o@e.com", username="other", password="x")
        foreign = ExchangeConnection.objects.create(
            owner=other, exchange="binance",
            api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"),
        )
        resp = authenticated_client.post(
            f"/api/strategies/paper/{acc.id}/live/",
            {"enable": True, "connection_id": foreign.id}, format="json",
        )
        assert resp.status_code == 400


class TestLiveOrderAudit:
    """Auditoría de órdenes reales: todo intento queda registrado."""

    @pytest.mark.integration
    def test_sent_order_recorded(self, strategy, test_user):
        from core.application.use_cases.paper_trading import _apply_signal, _mirror_live
        from core.infrastructure.persistence.models import LiveOrderRecord
        acc, conn = _live_account(strategy, test_user, cap=100.0)
        broker = _FakeLiveBroker()
        trade = _apply_signal(acc, "BUY", price=100.0)
        _mirror_live(acc, trade, 100.0, broker_factory=lambda c: broker)

        rec = LiveOrderRecord.objects.get()
        assert rec.status == "sent" and rec.side == "buy"
        assert rec.symbol == "BTC/USDT" and rec.is_testnet is True
        assert rec.notional_usd == pytest.approx(rec.amount * 100.0, rel=1e-6)
        assert rec.connection_id == conn.id and rec.broker_order_id == "1"

    @pytest.mark.integration
    def test_failed_order_recorded_with_error(self, strategy, test_user):
        from core.application.use_cases.paper_trading import _apply_signal, _mirror_live
        from core.infrastructure.persistence.models import LiveOrderRecord
        acc, _ = _live_account(strategy, test_user)
        trade = _apply_signal(acc, "BUY", price=100.0)
        _mirror_live(acc, trade, 100.0, broker_factory=lambda c: _FakeLiveBroker(fail=True))

        rec = LiveOrderRecord.objects.get()
        assert rec.status == "failed"
        assert "insuficientes" in rec.error.lower()
        assert acc.live_enabled is False   # kill-switch sigue funcionando

    @pytest.mark.integration
    def test_live_pnl_estimated_by_pairing(self, strategy, test_user):
        from core.application.use_cases.paper_trading import (
            LiveOrdersUseCase, _apply_signal, _mirror_live,
        )
        acc, _ = _live_account(strategy, test_user, cap=100.0)
        broker = _FakeLiveBroker()
        # Compra a 100 (≈1 unidad con tope 100) y venta a 120
        t1 = _apply_signal(acc, "BUY", price=100.0)
        _mirror_live(acc, t1, 100.0, broker_factory=lambda c: broker)
        t2 = _apply_signal(acc, "SELL", price=120.0)
        _mirror_live(acc, t2, 120.0, broker_factory=lambda c: broker)

        out = LiveOrdersUseCase().execute(owner=test_user, account_id=acc.id)
        assert out["orders_sent"] == 2 and out["orders_failed"] == 0
        # 1 unidad: vendida a 120 − comprada a 100 ≈ +20 USD (precios de referencia)
        assert out["live_realized_pnl_usd"] == pytest.approx(20.0, rel=0.01)
        assert out["pnl_is_estimate"] is True   # el broker falso no devuelve fill
        assert len(out["orders"]) == 2

    @pytest.mark.integration
    def test_orders_endpoint_and_ownership(self, authenticated_client, strategy, test_user, db):
        from core.infrastructure.persistence.models import User
        acc, _ = _live_account(strategy, test_user)
        resp = authenticated_client.get(f"/api/strategies/paper/{acc.id}/live/orders/")
        assert resp.status_code == 200
        assert set(resp.data) >= {"orders", "orders_sent", "live_realized_pnl_usd"}

        other = User.objects.create_user(email="x@e.com", username="x", password="x")
        from core.infrastructure.persistence.models import PaperTradingAccount
        foreign = PaperTradingAccount.objects.create(
            strategy=strategy, owner=other, asset_symbol="BTC", interval="1d",
            initial_capital=1000.0, cash=1000.0,
        )
        assert authenticated_client.get(f"/api/strategies/paper/{foreign.id}/live/orders/").status_code == 404
