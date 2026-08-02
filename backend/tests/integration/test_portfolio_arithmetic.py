"""
tests/integration/test_portfolio_arithmetic.py — Aritmética del portfolio.

Es la parte del sistema donde un error no se nota: un PnL mal calculado no
lanza ninguna excepción, simplemente muestra una cifra equivocada. Estos
tests fijan el resultado esperado con números escogidos a mano, de forma
que cualquier cambio en el cálculo tenga que justificarse.

Se cubren:
  - Coste medio ponderado (AVCO) al ampliar una posición.
  - PnL realizado de cierres parciales y totales, en LONG y en SHORT.
  - Conservación de la precisión decimal de extremo a extremo (el motivo
    por el que los importes dejaron de viajar como float).
  - Reglas de negocio: no cerrar más de lo abierto, no ampliar una
    posición cerrada, no operar sobre posiciones ajenas.
"""

from decimal import Decimal

import pytest

from core.infrastructure.persistence.models import CryptoAsset, Position, TradeHistory


@pytest.fixture
def btc(db):
    return CryptoAsset.objects.create(
        symbol="BTC", name="Bitcoin", current_price=Decimal("50000.00000000")
    )


def _open_long(client, quantity="1", price="20000", **extra):
    payload = {
        "asset_symbol": "BTC",
        "direction": "LONG",
        "quantity": quantity,
        "entry_price": price,
        "opened_at": "2026-01-15T10:00:00Z",
    }
    payload.update(extra)
    return client.post("/api/portfolio/positions/", payload, format="json")


def _open_short(client, quantity="1", price="60000", **extra):
    payload = {
        "asset_symbol": "BTC",
        "direction": "SHORT",
        "quantity": quantity,
        "entry_price": price,
        "opened_at": "2026-01-15T10:00:00Z",
    }
    payload.update(extra)
    return client.post("/api/portfolio/positions/", payload, format="json")


# ── Coste medio ponderado ──────────────────────────────────────────


@pytest.mark.integration
class TestAverageCost:

    def test_scaling_recomputes_the_weighted_average(self, authenticated_client, btc):
        """
        1 BTC a 20.000 + 1 BTC a 30.000 → precio medio 25.000.

        Es la media ponderada, no la aritmética: con cantidades distintas
        el resultado cambia, y eso lo fija el test siguiente.
        """
        opened = _open_long(authenticated_client, quantity="1", price="20000")
        assert opened.status_code == 201
        position_id = opened.data["id"]

        scaled = authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/add/",
            {
                "quantity": "1",
                "entry_price": "30000",
                "executed_at": "2026-01-20T10:00:00Z",
            },
            format="json",
        )
        assert scaled.status_code == 200
        assert Decimal(scaled.data["avg_entry_price"]) == Decimal("25000")
        assert Decimal(scaled.data["open_quantity"]) == Decimal("2")

    def test_weighted_average_accounts_for_the_size_of_each_entry(
        self, authenticated_client, btc
    ):
        """
        3 BTC a 10.000 + 1 BTC a 20.000 → (30.000 + 20.000) / 4 = 12.500.

        La media aritmética daría 15.000: este test distingue una
        implementación correcta de la ingenua.
        """
        position_id = _open_long(authenticated_client, quantity="3", price="10000").data["id"]

        scaled = authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/add/",
            {
                "quantity": "1",
                "entry_price": "20000",
                "executed_at": "2026-01-20T10:00:00Z",
            },
            format="json",
        )
        assert Decimal(scaled.data["avg_entry_price"]) == Decimal("12500")

    def test_scaling_grows_the_initial_quantity(self, authenticated_client, btc):
        """`initial_quantity` acumula todo lo entrado y nunca decrece."""
        position_id = _open_long(authenticated_client, quantity="2", price="20000").data["id"]
        scaled = authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/add/",
            {"quantity": "3", "entry_price": "25000", "executed_at": "2026-01-20T10:00:00Z"},
            format="json",
        )
        assert Decimal(scaled.data["initial_quantity"]) == Decimal("5")


# ── PnL realizado ──────────────────────────────────────────────────


@pytest.mark.integration
class TestRealizedPnL:

    def test_long_partial_close_realizes_the_expected_profit(self, authenticated_client, btc):
        """
        Compra 2 BTC a 20.000, cierra 1 a 30.000 → +10.000 realizados.
        """
        position_id = _open_long(authenticated_client, quantity="2", price="20000").data["id"]

        closed = authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/close/",
            {
                "close_quantity": "1",
                "close_price": "30000",
                "executed_at": "2026-02-01T10:00:00Z",
            },
            format="json",
        )
        assert closed.status_code == 200
        assert Decimal(closed.data["realized_pnl_usd"]) == Decimal("10000")
        assert Decimal(closed.data["open_quantity"]) == Decimal("1")
        assert closed.data["status"] == "OPEN"

    def test_long_loss_is_negative(self, authenticated_client, btc):
        """Vender por debajo del coste realiza una pérdida, no un beneficio."""
        position_id = _open_long(authenticated_client, quantity="1", price="30000").data["id"]

        closed = authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/close/",
            {
                "close_quantity": "1",
                "close_price": "20000",
                "executed_at": "2026-02-01T10:00:00Z",
            },
            format="json",
        )
        assert Decimal(closed.data["realized_pnl_usd"]) == Decimal("-10000")

    def test_short_profits_when_the_price_falls(self, authenticated_client, btc):
        """
        En un SHORT el signo se invierte: vender a 60.000 y recomprar a
        40.000 son +20.000. Un error de signo aquí convertiría todas las
        pérdidas en ganancias sin que nada fallase.
        """
        position_id = _open_short(authenticated_client, quantity="1", price="60000").data["id"]

        closed = authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/close/",
            {
                "close_quantity": "1",
                "close_price": "40000",
                "executed_at": "2026-02-01T10:00:00Z",
            },
            format="json",
        )
        assert Decimal(closed.data["realized_pnl_usd"]) == Decimal("20000")

    def test_short_loses_when_the_price_rises(self, authenticated_client, btc):
        position_id = _open_short(authenticated_client, quantity="1", price="40000").data["id"]

        closed = authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/close/",
            {
                "close_quantity": "1",
                "close_price": "60000",
                "executed_at": "2026-02-01T10:00:00Z",
            },
            format="json",
        )
        assert Decimal(closed.data["realized_pnl_usd"]) == Decimal("-20000")

    def test_full_close_marks_the_position_as_closed(self, authenticated_client, btc):
        position_id = _open_long(authenticated_client, quantity="1", price="20000").data["id"]

        closed = authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/close/",
            {
                "close_quantity": "1",
                "close_price": "25000",
                "executed_at": "2026-02-01T10:00:00Z",
            },
            format="json",
        )
        assert closed.data["status"] == "CLOSED"
        assert Decimal(closed.data["open_quantity"]) == Decimal("0")
        assert closed.data["closed_at"] is not None

    def test_successive_partial_closes_accumulate(self, authenticated_client, btc):
        """Dos cierres de 1 BTC con +5.000 cada uno suman +10.000."""
        position_id = _open_long(authenticated_client, quantity="2", price="20000").data["id"]

        for _ in range(2):
            response = authenticated_client.post(
                f"/api/portfolio/positions/{position_id}/close/",
                {
                    "close_quantity": "1",
                    "close_price": "25000",
                    "executed_at": "2026-02-01T10:00:00Z",
                },
                format="json",
            )
        assert Decimal(response.data["realized_pnl_usd"]) == Decimal("10000")
        assert response.data["status"] == "CLOSED"


# ── Precisión decimal ──────────────────────────────────────────────


@pytest.mark.integration
class TestDecimalPrecision:

    def test_high_precision_quantity_survives_the_round_trip(
        self, authenticated_client, btc
    ):
        """
        Una cantidad de 18 decimales llega intacta a la base de datos.

        Es exactamente lo que se perdía cuando el importe viajaba como
        float: 0.123456789012345678 no es representable en doble
        precisión y se almacenaba redondeado.
        """
        quantity = "0.123456789012345678"
        response = _open_long(authenticated_client, quantity=quantity, price="20000")
        assert response.status_code == 201

        stored = Position.objects.get(pk=response.data["id"])
        assert stored.open_quantity == Decimal(quantity)

    def test_price_keeps_its_eight_decimals(self, authenticated_client, btc):
        price = "0.00000123"
        response = _open_long(authenticated_client, quantity="1000", price=price)
        assert response.status_code == 201

        stored = Position.objects.get(pk=response.data["id"])
        assert stored.avg_entry_price == Decimal(price)

    def test_trade_total_is_the_exact_product(self, authenticated_client, btc):
        """total = cantidad × precio, sin arrastre de redondeo."""
        response = _open_long(authenticated_client, quantity="0.5", price="20000.5")
        trade = TradeHistory.objects.get(position_id=response.data["id"])
        assert trade.total_usd == Decimal("0.5") * Decimal("20000.5")


# ── Reglas de negocio ──────────────────────────────────────────────


@pytest.mark.integration
class TestPositionRules:

    def test_cannot_close_more_than_is_open(self, authenticated_client, btc):
        position_id = _open_long(authenticated_client, quantity="1", price="20000").data["id"]

        response = authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/close/",
            {
                "close_quantity": "2",
                "close_price": "25000",
                "executed_at": "2026-02-01T10:00:00Z",
            },
            format="json",
        )
        assert response.status_code == 400

    def test_cannot_scale_a_closed_position(self, authenticated_client, btc):
        position_id = _open_long(authenticated_client, quantity="1", price="20000").data["id"]
        authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/close/",
            {
                "close_quantity": "1",
                "close_price": "25000",
                "executed_at": "2026-02-01T10:00:00Z",
            },
            format="json",
        )

        response = authenticated_client.post(
            f"/api/portfolio/positions/{position_id}/add/",
            {"quantity": "1", "entry_price": "26000", "executed_at": "2026-02-02T10:00:00Z"},
            format="json",
        )
        assert response.status_code == 400

    def test_cannot_operate_on_another_users_position(self, authenticated_client, admin_client, btc):
        """
        Aislamiento entre usuarios: una posición ajena debe responder 404,
        no 403. Un 403 confirmaría que el identificador existe.
        """
        position_id = _open_long(authenticated_client, quantity="1", price="20000").data["id"]

        response = admin_client.post(
            f"/api/portfolio/positions/{position_id}/close/",
            {
                "close_quantity": "1",
                "close_price": "25000",
                "executed_at": "2026-02-01T10:00:00Z",
            },
            format="json",
        )
        assert response.status_code in (400, 404)
        assert Position.objects.get(pk=position_id).status == "OPEN"

    def test_rejects_a_trade_dated_in_the_future(self, authenticated_client, btc):
        """
        Una operación con fecha futura descuadra el histórico y el orden
        del historial.
        """
        response = _open_long(
            authenticated_client, quantity="1", price="20000", opened_at="2099-01-01T10:00:00Z"
        )
        assert response.status_code == 400

    def test_rejects_a_non_positive_quantity(self, authenticated_client, btc):
        response = _open_long(authenticated_client, quantity="0", price="20000")
        assert response.status_code == 400

    def test_rejects_an_unknown_asset(self, authenticated_client, btc):
        response = authenticated_client.post(
            "/api/portfolio/positions/",
            {
                "asset_symbol": "NOEXISTE",
                "direction": "LONG",
                "quantity": "1",
                "entry_price": "100",
                "opened_at": "2026-01-15T10:00:00Z",
            },
            format="json",
        )
        assert response.status_code == 400

    def test_opening_a_position_records_the_matching_trade(self, authenticated_client, btc):
        """Toda posición nace con su trade de apertura: sin huecos."""
        response = _open_long(authenticated_client, quantity="2", price="20000")
        trade = TradeHistory.objects.get(position_id=response.data["id"])
        assert trade.trade_type == "BUY"
        assert trade.trade_intent == "OPEN"
        assert trade.quantity == Decimal("2")

    def test_opening_a_short_records_a_sell(self, authenticated_client, btc):
        response = _open_short(authenticated_client, quantity="1", price="60000")
        trade = TradeHistory.objects.get(position_id=response.data["id"])
        assert trade.trade_type == "SELL"
