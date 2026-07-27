"""
tests/integration/test_broker_trading.py — Trading real multi-exchange (manual).

Verifica el cifrado de credenciales (round-trip, nunca en claro en BD), la
verificación de la conexión antes de guardar, testnet por defecto, las
validaciones de orden en servidor, el aislamiento por usuario y los endpoints.
El broker ccxt se mockea: los tests no tocan ningún exchange.
"""

import pytest

from core.application.use_cases.broker_trading import (
    CancelOrderUseCase, ConnectExchangeUseCase, GetBrokerBalanceUseCase,
    ListConnectionsUseCase, PlaceOrderUseCase, RemoveConnectionUseCase,
)
from core.infrastructure.external_apis.ccxt_broker import BrokerError
from core.infrastructure.security.crypto import decrypt_secret, encrypt_secret


class _FakeBroker:
    """Broker falso con las operaciones del panel manual."""

    def __init__(self, connection=None, fail_auth=False):
        self.connection = connection
        self.fail_auth = fail_auth
        self.orders: list[dict] = []

    def fetch_balance(self):
        if self.fail_auth:
            raise BrokerError("Credenciales rechazadas por el exchange: revisa la API key y sus permisos.")
        return {"balances": [{"asset": "USDT", "total": 1000.0, "free": 900.0, "used": 100.0}]}

    def create_order(self, symbol, side, order_type, amount, price=None):
        order = {"id": "42", "symbol": symbol, "side": side, "type": order_type,
                 "amount": amount, "price": price, "filled": 0, "status": "open",
                 "datetime": "2026-07-01T10:00:00Z"}
        self.orders.append(order)
        return order

    def fetch_open_orders(self, symbol=None):
        return list(self.orders)

    def cancel_order(self, order_id, symbol):
        return {"id": order_id, "status": "canceled"}


def _factory(broker):
    return lambda connection: broker


class TestCrypto:

    @pytest.mark.unit
    def test_encrypt_decrypt_roundtrip(self):
        token = encrypt_secret("mi-api-key-secreta")
        assert token != "mi-api-key-secreta"
        assert decrypt_secret(token) == "mi-api-key-secreta"


class TestConnect:

    @pytest.mark.integration
    def test_connect_verifies_and_stores_encrypted(self, test_user):
        from core.infrastructure.persistence.models import ExchangeConnection
        broker = _FakeBroker()
        r = ConnectExchangeUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, exchange="binance", api_key="KEY", api_secret="SECRET",
        )
        assert "error" not in r
        assert r["is_testnet"] is True                      # testnet por defecto
        conn = ExchangeConnection.objects.get(id=r["id"])
        assert conn.api_key_enc != "KEY"                    # nunca en claro
        assert decrypt_secret(conn.api_key_enc) == "KEY"
        assert decrypt_secret(conn.api_secret_enc) == "SECRET"

    @pytest.mark.integration
    def test_failed_verification_does_not_store(self, test_user):
        from core.infrastructure.persistence.models import ExchangeConnection
        r = ConnectExchangeUseCase(broker_factory=_factory(_FakeBroker(fail_auth=True))).execute(
            owner=test_user, exchange="binance", api_key="BAD", api_secret="BAD",
        )
        assert "error" in r and "Verificación fallida" in r["error"]
        assert ExchangeConnection.objects.count() == 0

    @pytest.mark.integration
    def test_unsupported_exchange_rejected(self, test_user):
        r = ConnectExchangeUseCase(broker_factory=_factory(_FakeBroker())).execute(
            owner=test_user, exchange="mtgox", api_key="K", api_secret="S",
        )
        assert "error" in r

    @pytest.mark.integration
    def test_list_never_returns_credentials(self, test_user):
        ConnectExchangeUseCase(broker_factory=_factory(_FakeBroker())).execute(
            owner=test_user, exchange="binance", api_key="KEY", api_secret="SECRET",
        )
        out = ListConnectionsUseCase().execute(owner=test_user)
        assert out["count"] == 1
        serialized = str(out)
        assert "KEY" not in serialized and "SECRET" not in serialized
        assert "api_key" not in out["results"][0]


@pytest.fixture
def connection(db, test_user):
    from core.infrastructure.persistence.models import ExchangeConnection
    return ExchangeConnection.objects.create(
        owner=test_user, exchange="binance",
        api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"),
        is_testnet=True,
    )


class TestOrders:

    @pytest.mark.integration
    def test_market_order_placed(self, test_user, connection):
        broker = _FakeBroker()
        r = PlaceOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
            symbol="btc/usdt", side="BUY", order_type="market", amount="0.5",
        )
        assert "error" not in r
        assert r["order"]["symbol"] == "BTC/USDT" and r["order"]["side"] == "buy"
        assert r["is_testnet"] is True

    @pytest.mark.integration
    def test_limit_requires_price(self, test_user, connection):
        r = PlaceOrderUseCase(broker_factory=_factory(_FakeBroker())).execute(
            owner=test_user, connection_id=connection.id,
            symbol="BTC/USDT", side="buy", order_type="limit", amount=1,
        )
        assert "error" in r and "precio" in r["error"].lower()

    @pytest.mark.integration
    def test_invalid_inputs_rejected(self, test_user, connection):
        uc = PlaceOrderUseCase(broker_factory=_factory(_FakeBroker()))
        assert "error" in uc.execute(owner=test_user, connection_id=connection.id,
                                     symbol="BTCUSDT", side="buy", order_type="market", amount=1)
        assert "error" in uc.execute(owner=test_user, connection_id=connection.id,
                                     symbol="BTC/USDT", side="hold", order_type="market", amount=1)
        assert "error" in uc.execute(owner=test_user, connection_id=connection.id,
                                     symbol="BTC/USDT", side="buy", order_type="market", amount=-3)

    @pytest.mark.integration
    def test_other_users_connection_not_found(self, db, connection):
        from core.infrastructure.persistence.models import User
        other = User.objects.create_user(email="o@e.com", username="other", password="x")
        r = PlaceOrderUseCase(broker_factory=_factory(_FakeBroker())).execute(
            owner=other, connection_id=connection.id,
            symbol="BTC/USDT", side="buy", order_type="market", amount=1,
        )
        assert "error" in r and "no encontrada" in r["error"].lower()

    @pytest.mark.integration
    def test_balance_open_orders_and_cancel(self, test_user, connection):
        broker = _FakeBroker()
        bal = GetBrokerBalanceUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
        )
        assert bal["balances"][0]["asset"] == "USDT"

        PlaceOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
            symbol="BTC/USDT", side="buy", order_type="limit", amount=1, price=50_000,
        )
        from core.application.use_cases.broker_trading import OpenOrdersUseCase
        opened = OpenOrdersUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id,
        )
        assert opened["count"] == 1

        canceled = CancelOrderUseCase(broker_factory=_factory(broker)).execute(
            owner=test_user, connection_id=connection.id, order_id="42", symbol="BTC/USDT",
        )
        assert canceled["status"] == "canceled"

    @pytest.mark.integration
    def test_remove_connection(self, test_user, connection):
        out = RemoveConnectionUseCase().execute(owner=test_user, connection_id=connection.id)
        assert out["removed"] is True
        assert ListConnectionsUseCase().execute(owner=test_user)["count"] == 0


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/trading/connections/").status_code == 401

    @pytest.mark.integration
    def test_list_and_validation_via_api(self, authenticated_client):
        resp = authenticated_client.get("/api/trading/connections/")
        assert resp.status_code == 200 and resp.data["count"] == 0

        bad = authenticated_client.post("/api/trading/connections/",
                                        {"exchange": "mtgox", "api_key": "k", "api_secret": "s"},
                                        format="json")
        assert bad.status_code == 400

    @pytest.mark.integration
    def test_order_endpoint_validates(self, authenticated_client, test_user, connection):
        resp = authenticated_client.post(
            f"/api/trading/connections/{connection.id}/orders/",
            {"symbol": "BTCUSDT", "side": "buy", "type": "market", "amount": 1},
            format="json",
        )
        assert resp.status_code == 400 and "BASE/QUOTE" in resp.data["error"]
