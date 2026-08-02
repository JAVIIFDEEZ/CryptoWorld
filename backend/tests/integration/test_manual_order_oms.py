"""
tests/integration/test_manual_order_oms.py — Gobierno de la orden manual real.

La promoción automática paper→real ya pasaba por el OMS (límite de pérdida
diaria, límite de concentración) y dejaba rastro de auditoría. La orden manual
—el mismo dinero, en el mismo exchange— no pasaba por nada de eso. Estos tests
fijan el comportamiento corregido:

  · toda orden manual queda registrada (enviada / fallida / bloqueada);
  · las barreras de riesgo se aplican a las COMPRAS y nunca a las ventas;
  · `client_order_id` hace la petición idempotente: un reintento no manda una
    segunda orden real al exchange;
  · el rastro de auditoría, el TCA y la exposición del libro ven las órdenes
    manuales, no solo las espejadas.
"""

import pytest

from core.application.use_cases.broker_trading import PlaceOrderUseCase
from core.infrastructure.external_apis.ccxt_broker import BrokerError
from core.infrastructure.security.crypto import encrypt_secret


class _FakeBroker:
    """Broker falso que cuenta cuántas órdenes ha recibido de verdad."""

    def __init__(self, fail: str = "") -> None:
        self.fail = fail
        self.orders: list[dict] = []

    def create_order(self, symbol, side, order_type, amount, price=None):
        if self.fail:
            raise BrokerError(self.fail)
        order = {"id": f"ord-{len(self.orders) + 1}", "symbol": symbol, "side": side,
                 "type": order_type, "amount": amount, "price": price,
                 "average": price or 100.0, "status": "closed"}
        self.orders.append(order)
        return order


def _factory(broker):
    return lambda connection: broker


@pytest.fixture
def connection(db, test_user):
    from core.infrastructure.persistence.models import ExchangeConnection
    return ExchangeConnection.objects.create(
        owner=test_user, exchange="binance",
        api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"),
        is_testnet=True,
    )


@pytest.fixture
def btc(db):
    """Activo con precio conocido: da el precio de referencia de las market."""
    from core.infrastructure.persistence.models import CryptoAsset
    return CryptoAsset.objects.create(symbol="BTC", name="Bitcoin", current_price=100)


class TestAuditTrail:
    """Toda orden manual deja rastro, salga como salga."""

    @pytest.mark.integration
    def test_sent_order_is_recorded(self, test_user, connection, btc):
        from core.infrastructure.persistence.models import LiveOrderRecord

        broker = _FakeBroker()
        result = PlaceOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
            symbol="btc/usdt", side="buy", order_type="market", amount="2",
        )

        assert "error" not in result
        record = LiveOrderRecord.objects.get(id=result["record_id"])
        assert record.status == "sent"
        assert record.source == "manual"
        assert record.owner_id == test_user.id
        assert record.account_id is None          # una orden manual no nace de una cartera
        assert record.symbol == "BTC/USDT"
        assert record.broker_order_id == "ord-1"
        assert record.notional_usd == pytest.approx(200.0)   # 2 unidades × 100 USD

    @pytest.mark.integration
    def test_failed_order_is_recorded_with_reason(self, test_user, connection, btc):
        from core.infrastructure.persistence.models import LiveOrderRecord

        broker = _FakeBroker(fail="Saldo insuficiente en el exchange.")
        result = PlaceOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
            symbol="BTC/USDT", side="buy", order_type="market", amount="1",
        )

        assert "Saldo insuficiente" in result["error"]
        record = LiveOrderRecord.objects.get(id=result["record_id"])
        assert record.status == "failed"
        assert "Saldo insuficiente" in record.error

    @pytest.mark.integration
    def test_rejected_input_never_reaches_the_exchange(self, test_user, connection):
        from core.infrastructure.persistence.models import LiveOrderRecord

        broker = _FakeBroker()
        result = PlaceOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
            symbol="BTCUSDT", side="buy", order_type="market", amount="1",
        )

        assert "error" in result
        assert broker.orders == []
        # Una petición mal formada no es un intento de operar: no ensucia la auditoría.
        assert LiveOrderRecord.objects.count() == 0


class TestRiskBarriers:
    """Las barreras del OMS gobiernan también la vía manual."""

    @pytest.fixture
    def losing_day(self, db, test_user, connection):
        """Deja al usuario con una pérdida realizada hoy de −50 USD y un
        límite diario de 10 USD: cualquier compra debe quedar bloqueada."""
        from core.infrastructure.persistence.models import LiveOrderRecord, LiveRiskPolicy

        LiveRiskPolicy.objects.create(owner=test_user, daily_loss_limit_usd=10.0)
        # Compra a 100 y venta a 50 sobre el mismo símbolo → −50 USD realizados.
        LiveOrderRecord.objects.create(
            owner=test_user, connection=connection, source="manual", symbol="BTC/USDT",
            side="buy", amount=1.0, ref_price=100.0, fill_price=100.0,
            notional_usd=100.0, status="sent",
        )
        LiveOrderRecord.objects.create(
            owner=test_user, connection=connection, source="manual", symbol="BTC/USDT",
            side="sell", amount=1.0, ref_price=50.0, fill_price=50.0,
            notional_usd=50.0, status="sent",
        )

    @pytest.mark.integration
    def test_daily_loss_limit_blocks_manual_buy(self, test_user, connection, btc, losing_day):
        from core.infrastructure.persistence.models import LiveOrderRecord

        broker = _FakeBroker()
        result = PlaceOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
            symbol="BTC/USDT", side="buy", order_type="market", amount="1",
        )

        assert result["blocked_by"] == "oms"
        assert "pérdida diaria" in result["error"]
        assert broker.orders == []                       # nunca llegó al exchange
        record = LiveOrderRecord.objects.get(id=result["record_id"])
        assert record.status == "blocked"

    @pytest.mark.integration
    def test_daily_loss_limit_never_blocks_a_sell(self, test_user, connection, btc, losing_day):
        """Reducir exposición siempre está permitido, incluso en un día perdedor."""
        broker = _FakeBroker()
        result = PlaceOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
            symbol="BTC/USDT", side="sell", order_type="market", amount="1",
        )

        assert "error" not in result
        assert len(broker.orders) == 1

    @pytest.mark.integration
    def test_concentration_limit_blocks_manual_buy(self, test_user, connection, btc):
        from core.infrastructure.persistence.models import LiveRiskPolicy

        # Sin más libro, esta compra dejaría a BTC al 100% de la exposición.
        LiveRiskPolicy.objects.create(owner=test_user, max_concentration_pct=50.0)

        broker = _FakeBroker()
        result = PlaceOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
            symbol="BTC/USDT", side="buy", order_type="market", amount="5",
        )

        assert result["blocked_by"] == "oms"
        assert "concentración" in result["error"]
        assert broker.orders == []

    @pytest.mark.integration
    def test_buy_passes_when_no_policy_configured(self, test_user, connection, btc):
        """Sin política declarada no hay barrera: el usuario opera con libertad."""
        broker = _FakeBroker()
        result = PlaceOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
            symbol="BTC/USDT", side="buy", order_type="market", amount="1",
        )

        assert "error" not in result
        assert len(broker.orders) == 1


class TestIdempotency:
    """Un reintento no puede convertirse en una segunda orden real."""

    @pytest.mark.integration
    def test_same_client_order_id_is_not_resent(self, test_user, connection, btc):
        from core.infrastructure.persistence.models import LiveOrderRecord

        broker = _FakeBroker()
        use_case = PlaceOrderUseCase(broker_factory=_factory(broker))
        payload = dict(owner=test_user, connection_id=connection.id, symbol="BTC/USDT",
                       side="buy", order_type="market", amount="1",
                       client_order_id="cli-abc-123")

        first = use_case.execute(**payload)
        second = use_case.execute(**payload)

        assert len(broker.orders) == 1                    # una sola orden real
        assert second["idempotent_replay"] is True
        assert second["record_id"] == first["record_id"]
        assert LiveOrderRecord.objects.filter(client_order_id="cli-abc-123").count() == 1

    @pytest.mark.integration
    def test_blocked_attempt_replays_the_block(self, test_user, connection, btc):
        from core.infrastructure.persistence.models import LiveRiskPolicy

        LiveRiskPolicy.objects.create(owner=test_user, max_concentration_pct=10.0)
        broker = _FakeBroker()
        use_case = PlaceOrderUseCase(broker_factory=_factory(broker))
        payload = dict(owner=test_user, connection_id=connection.id, symbol="BTC/USDT",
                       side="buy", order_type="market", amount="3",
                       client_order_id="cli-blocked")

        use_case.execute(**payload)
        replay = use_case.execute(**payload)

        assert replay["blocked_by"] == "oms"
        assert replay["idempotent_replay"] is True
        assert broker.orders == []

    @pytest.mark.integration
    def test_distinct_ids_are_distinct_orders(self, test_user, connection, btc):
        broker = _FakeBroker()
        use_case = PlaceOrderUseCase(broker_factory=_factory(broker))
        for cid in ("cli-1", "cli-2"):
            use_case.execute(owner=test_user, connection_id=connection.id,
                             symbol="BTC/USDT", side="buy", order_type="market",
                             amount="1", client_order_id=cid)

        assert len(broker.orders) == 2

    @pytest.mark.integration
    def test_id_is_claimed_before_touching_the_exchange(self, test_user, connection, btc):
        """La reserva ocurre ANTES de llamar al broker.

        Si el identificador se reservara después, dos peticiones simultáneas
        pasarían las dos la comprobación previa y ambas enviarían la orden: la
        restricción única llegaría tarde, con el dinero ya movido.
        """
        from core.infrastructure.persistence.models import LiveOrderRecord

        seen: list[str] = []

        class _ObservingBroker:
            def create_order(self, symbol, side, order_type, amount, price=None):
                # En el momento de llamar al exchange, el intento ya debe estar
                # persistido y con su client_order_id reclamado.
                seen.append(
                    LiveOrderRecord.objects
                    .get(owner=test_user, client_order_id="cli-carrera").status
                )
                return {"id": "ok", "average": 100.0}

        PlaceOrderUseCase(broker_factory=lambda c: _ObservingBroker()).execute(
            owner=test_user, connection_id=connection.id, symbol="BTC/USDT",
            side="buy", order_type="market", amount="1", client_order_id="cli-carrera",
        )

        assert seen == ["pending"]

    @pytest.mark.integration
    def test_concurrent_claim_does_not_resend(self, test_user, connection, btc):
        """Si otra petición gana la carrera por el identificador, esta no envía
        nada: reproduce el resultado de la ganadora."""
        from core.infrastructure.persistence.models import LiveOrderRecord

        # Simula a la ganadora: el registro ya existe cuando llega la segunda.
        LiveOrderRecord.objects.create(
            owner=test_user, connection=connection, source="manual", symbol="BTC/USDT",
            side="buy", amount=1.0, ref_price=100.0, fill_price=100.0,
            notional_usd=100.0, status="sent", broker_order_id="ganadora",
            client_order_id="cli-duelo",
        )

        broker = _FakeBroker()
        result = PlaceOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id, symbol="BTC/USDT",
            side="buy", order_type="market", amount="1", client_order_id="cli-duelo",
        )

        assert broker.orders == []
        assert result["idempotent_replay"] is True
        assert result["order"]["id"] == "ganadora"
        assert LiveOrderRecord.objects.filter(client_order_id="cli-duelo").count() == 1

    @pytest.mark.integration
    def test_client_order_id_is_scoped_per_user(self, db, test_user, connection, btc):
        """El identificador de otro usuario no puede colisionar con el mío."""
        from django.contrib.auth import get_user_model
        from core.infrastructure.persistence.models import ExchangeConnection

        other = get_user_model().objects.create_user(
            email="otro@example.com", username="otro", password="x-clave-larga-1",
        )
        other_conn = ExchangeConnection.objects.create(
            owner=other, exchange="binance",
            api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"),
        )

        broker = _FakeBroker()
        use_case = PlaceOrderUseCase(broker_factory=_factory(broker))
        use_case.execute(owner=test_user, connection_id=connection.id, symbol="BTC/USDT",
                         side="buy", order_type="market", amount="1", client_order_id="shared")
        result = use_case.execute(owner=other, connection_id=other_conn.id, symbol="BTC/USDT",
                                  side="buy", order_type="market", amount="1",
                                  client_order_id="shared")

        assert "error" not in result
        assert result.get("idempotent_replay") is None
        assert len(broker.orders) == 2


class TestSurfacesSeeManualOrders:
    """Auditoría, TCA y exposición dejan de ignorar las órdenes manuales."""

    @pytest.mark.integration
    def test_execution_audit_includes_manual_orders(self, test_user, connection, btc):
        from core.application.use_cases.execution_audit import ExecutionAuditUseCase

        PlaceOrderUseCase(broker_factory=_factory(_FakeBroker())).execute(
            owner=test_user, connection_id=connection.id, symbol="BTC/USDT",
            side="buy", order_type="market", amount="1",
        )

        out = ExecutionAuditUseCase().execute(owner=test_user)
        assert out["summary"]["total_attempts"] == 1
        assert out["entries"][0]["symbol"] == "BTC/USDT"

    @pytest.mark.integration
    def test_tca_includes_manual_orders(self, test_user, connection, btc):
        from core.application.use_cases.tca import ExecutionTcaUseCase

        PlaceOrderUseCase(broker_factory=_factory(_FakeBroker())).execute(
            owner=test_user, connection_id=connection.id, symbol="BTC/USDT",
            side="buy", order_type="market", amount="1",
        )

        out = ExecutionTcaUseCase().execute(owner=test_user)
        assert out["status"] != "EMPTY"
        assert out["orders_analyzed"] == 1

    @pytest.mark.integration
    def test_manual_position_counts_in_book_exposure(self, test_user, connection, btc):
        from core.application.use_cases.portfolio_risk import PortfolioRiskUseCase

        PlaceOrderUseCase(broker_factory=_factory(_FakeBroker())).execute(
            owner=test_user, connection_id=connection.id, symbol="BTC/USDT",
            side="buy", order_type="market", amount="3",
        )

        exposures = PortfolioRiskUseCase._aggregate_exposures(test_user)
        assert exposures["BTC"]["by_book"]["live"] == pytest.approx(300.0)

    @pytest.mark.integration
    def test_sold_manual_position_leaves_no_exposure(self, test_user, connection, btc):
        from core.application.use_cases.portfolio_risk import PortfolioRiskUseCase

        use_case = PlaceOrderUseCase(broker_factory=_factory(_FakeBroker()))
        use_case.execute(owner=test_user, connection_id=connection.id, symbol="BTC/USDT",
                         side="buy", order_type="market", amount="2")
        use_case.execute(owner=test_user, connection_id=connection.id, symbol="BTC/USDT",
                         side="sell", order_type="market", amount="2")

        assert PortfolioRiskUseCase._aggregate_exposures(test_user) == {}


class TestApi:

    @pytest.mark.integration
    def test_blocked_order_returns_409(self, authenticated_client, test_user, connection, btc, monkeypatch):
        """Una orden válida frenada por la política de riesgo no es un 400:
        el cliente necesita distinguir 'petición mal formada' de 'te lo impide
        tu propio límite de riesgo'."""
        from core.infrastructure.persistence.models import LiveRiskPolicy

        LiveRiskPolicy.objects.create(owner=test_user, max_concentration_pct=10.0)

        resp = authenticated_client.post(
            f"/api/trading/connections/{connection.id}/orders/",
            {"symbol": "BTC/USDT", "side": "buy", "type": "market", "amount": 5},
            format="json",
        )

        assert resp.status_code == 409
        assert resp.data["blocked_by"] == "oms"
