"""
broker_trading.py — Casos de uso de trading real multi-exchange (manual).

Ejecución MANUAL desde la UI: el usuario conecta su exchange (claves cifradas,
testnet por defecto), consulta balance, lanza órdenes market/limit y gestiona
las abiertas. Nada opera solo: cada orden es una decisión explícita del usuario.

Seguridad:
  · Credenciales cifradas (Fernet) al guardar; la API nunca las devuelve.
  · La conexión se VERIFICA contra el exchange antes de guardarse.
  · Testnet por defecto; operar en real exige is_testnet=false explícito.
  · Validaciones de orden en servidor (lado, tipo, cantidad, precio en limit).
"""

import logging

logger = logging.getLogger(__name__)

_VALID_SIDES = ("buy", "sell")
_VALID_TYPES = ("market", "limit")


def _serialize_connection(c) -> dict:
    return {
        "id": c.id,
        "exchange": c.exchange,
        "label": c.label or None,
        "is_testnet": c.is_testnet,
        "is_active": c.is_active,
        "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
        "created_at": c.created_at.isoformat(),
    }


def _broker_for(connection):
    from core.infrastructure.external_apis.ccxt_broker import CcxtBroker
    return CcxtBroker(connection)


def _get_connection(owner, connection_id):
    from core.infrastructure.persistence.models import ExchangeConnection
    return ExchangeConnection.objects.filter(
        id=connection_id, owner=owner, is_active=True,
    ).first()


def _touch(connection) -> None:
    from django.utils import timezone
    connection.last_used_at = timezone.now()
    connection.save(update_fields=["last_used_at", "updated_at"])


class ConnectExchangeUseCase:
    """Guarda una conexión cifrada tras VERIFICARLA contra el exchange."""

    def __init__(self, broker_factory=None) -> None:
        self._factory = broker_factory or _broker_for

    def execute(self, owner, exchange: str, api_key: str, api_secret: str,
                api_password: str = "", is_testnet: bool = True, label: str = "") -> dict:
        from core.infrastructure.external_apis.ccxt_broker import BrokerError, SUPPORTED_EXCHANGES
        from core.infrastructure.persistence.models import ExchangeConnection
        from core.infrastructure.security.crypto import encrypt_secret

        exchange = (exchange or "").strip().lower()
        if exchange not in SUPPORTED_EXCHANGES:
            return {"error": f"Exchange no soportado. Disponibles: {list(SUPPORTED_EXCHANGES)}"}
        if not api_key.strip() or not api_secret.strip():
            return {"error": "Faltan la API key o el secret."}

        connection = ExchangeConnection(
            owner=owner,
            exchange=exchange,
            label=(label or "").strip()[:80],
            api_key_enc=encrypt_secret(api_key.strip()),
            api_secret_enc=encrypt_secret(api_secret.strip()),
            api_password_enc=encrypt_secret(api_password.strip()) if api_password.strip() else "",
            is_testnet=bool(is_testnet),
        )

        # Verificación real antes de persistir: una conexión que no puede leer
        # su balance no sirve para operar y no debe guardarse.
        try:
            self._factory(connection).fetch_balance()
        except BrokerError as exc:
            return {"error": f"Verificación fallida: {exc}"}

        connection.save()
        logger.info("exchange conectado: %s (%s) usuario=%s",
                    exchange, "testnet" if connection.is_testnet else "REAL", owner.id)
        return _serialize_connection(connection)


class ListConnectionsUseCase:

    def execute(self, owner) -> dict:
        from core.infrastructure.persistence.models import ExchangeConnection
        qs = ExchangeConnection.objects.filter(owner=owner, is_active=True)
        return {"count": qs.count(), "results": [_serialize_connection(c) for c in qs]}


class RemoveConnectionUseCase:

    def execute(self, owner, connection_id: int) -> dict:
        connection = _get_connection(owner, connection_id)
        if connection is None:
            return {"error": "Conexión no encontrada."}
        connection.is_active = False
        connection.save(update_fields=["is_active", "updated_at"])
        return {"id": connection_id, "removed": True}


class GetBrokerBalanceUseCase:

    def __init__(self, broker_factory=None) -> None:
        self._factory = broker_factory or _broker_for

    def execute(self, owner, connection_id: int) -> dict:
        from core.infrastructure.external_apis.ccxt_broker import BrokerError

        connection = _get_connection(owner, connection_id)
        if connection is None:
            return {"error": "Conexión no encontrada."}
        try:
            balance = self._factory(connection).fetch_balance()
        except BrokerError as exc:
            return {"error": str(exc)}
        _touch(connection)
        return {"connection": _serialize_connection(connection), **balance}


class PlaceOrderUseCase:
    """Orden manual market/limit con validaciones de servidor."""

    def __init__(self, broker_factory=None) -> None:
        self._factory = broker_factory or _broker_for

    def execute(self, owner, connection_id: int, symbol: str, side: str,
                order_type: str, amount, price=None) -> dict:
        from core.infrastructure.external_apis.ccxt_broker import BrokerError

        connection = _get_connection(owner, connection_id)
        if connection is None:
            return {"error": "Conexión no encontrada."}

        symbol = (symbol or "").strip().upper()
        side = (side or "").strip().lower()
        order_type = (order_type or "").strip().lower()
        if "/" not in symbol:
            return {"error": "Símbolo inválido: usa el formato BASE/QUOTE (p. ej. BTC/USDT)."}
        if side not in _VALID_SIDES:
            return {"error": "Lado inválido: debe ser buy o sell."}
        if order_type not in _VALID_TYPES:
            return {"error": "Tipo inválido: debe ser market o limit."}
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            return {"error": "Cantidad inválida."}
        if amount <= 0:
            return {"error": "La cantidad debe ser mayor que 0."}
        if order_type == "limit":
            try:
                price = float(price)
            except (TypeError, ValueError):
                return {"error": "Una orden limit necesita precio."}
            if price <= 0:
                return {"error": "El precio debe ser mayor que 0."}
        else:
            price = None

        try:
            order = self._factory(connection).create_order(symbol, side, order_type, amount, price)
        except BrokerError as exc:
            return {"error": str(exc)}
        _touch(connection)
        logger.info("orden %s %s %s x%s usuario=%s conexión=%s (%s)",
                    order_type, side, symbol, amount, owner.id, connection.id,
                    "testnet" if connection.is_testnet else "REAL")
        return {"order": order, "is_testnet": connection.is_testnet}


class OpenOrdersUseCase:

    def __init__(self, broker_factory=None) -> None:
        self._factory = broker_factory or _broker_for

    def execute(self, owner, connection_id: int, symbol: str | None = None) -> dict:
        from core.infrastructure.external_apis.ccxt_broker import BrokerError

        connection = _get_connection(owner, connection_id)
        if connection is None:
            return {"error": "Conexión no encontrada."}
        try:
            orders = self._factory(connection).fetch_open_orders(symbol or None)
        except BrokerError as exc:
            return {"error": str(exc)}
        return {"count": len(orders), "orders": orders}


class CancelOrderUseCase:

    def __init__(self, broker_factory=None) -> None:
        self._factory = broker_factory or _broker_for

    def execute(self, owner, connection_id: int, order_id: str, symbol: str) -> dict:
        from core.infrastructure.external_apis.ccxt_broker import BrokerError

        connection = _get_connection(owner, connection_id)
        if connection is None:
            return {"error": "Conexión no encontrada."}
        if not order_id or not symbol:
            return {"error": "Faltan order_id o symbol."}
        try:
            return self._factory(connection).cancel_order(order_id, symbol.upper())
        except BrokerError as exc:
            return {"error": str(exc)}
