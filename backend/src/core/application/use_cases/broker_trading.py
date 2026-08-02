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
  · Las MISMAS barreras del OMS que gobiernan la promoción paper→real
    (pérdida diaria y concentración por activo) se aplican aquí: una orden
    manual no puede saltarse la política de riesgo del usuario.
  · Todo intento queda en la auditoría (`LiveOrderRecord`): enviado, fallido o
    bloqueado, con su motivo.
  · Idempotencia por `client_order_id`: reintentar una petición no duplica la
    orden en el exchange.
"""

import logging

logger = logging.getLogger(__name__)
# Canal de cumplimiento: nunca se silencia por nivel de log (ver settings).
audit_logger = logging.getLogger("core.audit")

_VALID_SIDES = ("buy", "sell")
_VALID_TYPES = ("market", "limit")
_MAX_CLIENT_ORDER_ID = 64


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


def _reference_price(symbol: str, explicit_price: float | None) -> float:
    """Precio de referencia para valorar la orden (nocional y barreras).

    En una orden limit el precio lo fija el usuario. En una market hay que
    estimarlo: se usa el último precio conocido del activo en el catálogo
    local. Si no hay dato, se devuelve 0.0 y las barreras que dependen del
    nocional no pueden evaluarse — se registra igualmente el intento.
    """
    if explicit_price:
        return float(explicit_price)
    try:
        from core.infrastructure.persistence.models import CryptoAsset

        base = symbol.split("/")[0].upper()
        asset = CryptoAsset.objects.filter(symbol__iexact=base).only("current_price").first()
        return float(asset.current_price) if asset and asset.current_price else 0.0
    except Exception:  # noqa: BLE001 — sin precio se opera igual, solo sin barrera de nocional
        logger.exception("no se pudo resolver el precio de referencia de %s", symbol)
        return 0.0


class PlaceOrderUseCase:
    """Orden manual market/limit: validación, barreras del OMS y auditoría.

    El orden de los pasos importa y es el de una mesa real:
      1. validar la petición (nada llega al exchange sin forma correcta);
      2. resolver idempotencia (¿es un reintento de una orden ya cursada?);
      3. aplicar las barreras de riesgo — solo a las COMPRAS: reducir
         exposición nunca se bloquea;
      4. reservar el intento en la auditoría, que es lo que impide que dos
         peticiones simultáneas envíen dos órdenes;
      5. enviar al exchange y cerrar el registro con el resultado, salga bien
         o mal.
    """

    def __init__(self, broker_factory=None) -> None:
        self._factory = broker_factory or _broker_for

    def execute(self, owner, connection_id: int, symbol: str, side: str,
                order_type: str, amount, price=None, client_order_id: str = "") -> dict:
        from core.infrastructure.external_apis.ccxt_broker import BrokerError
        from core.infrastructure.persistence.models import LiveOrderRecord

        connection = _get_connection(owner, connection_id)
        if connection is None:
            return {"error": "Conexión no encontrada."}

        symbol = (symbol or "").strip().upper()
        side = (side or "").strip().lower()
        order_type = (order_type or "").strip().lower()
        client_order_id = (client_order_id or "").strip()[:_MAX_CLIENT_ORDER_ID]
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

        # ── Idempotencia (comprobación temprana) ──────────────────────
        # Un reintento de red o un doble clic no puede convertirse en dos
        # órdenes reales. Si ya existe un intento con este identificador se
        # devuelve su resultado sin volver a tocar el exchange.
        if client_order_id:
            previous = LiveOrderRecord.objects.filter(
                owner=owner, client_order_id=client_order_id,
            ).first()
            if previous is not None:
                logger.info("orden idempotente reutilizada (client_order_id=%s, estado=%s)",
                            client_order_id, previous.status)
                return _replay(previous)

        ref_price = _reference_price(symbol, price)
        notional = round(amount * ref_price, 2)

        record = LiveOrderRecord(
            owner=owner, connection=connection, source="manual",
            symbol=symbol, side=side, order_type=order_type, amount=amount,
            ref_price=ref_price, notional_usd=notional,
            is_testnet=connection.is_testnet, client_order_id=client_order_id,
        )

        # ── Barreras del OMS (solo compras) ───────────────────────────
        # Son las mismas que gobiernan la promoción paper→real. Sin esto, la
        # orden manual era la puerta trasera que dejaba sin efecto la política
        # de riesgo del usuario.
        if side == "buy":
            block_reason = _manual_buy_block_reason(owner, symbol, notional)
            if block_reason is not None:
                record.status = "blocked"
                record.error = block_reason[:300]
                if not _claim(record, client_order_id):
                    return _replay(_existing(owner, client_order_id))
                audit_logger.warning(
                    "OMS: orden manual bloqueada", extra={
                        "event": "live_order_blocked", "user_id": owner.id,
                        "connection_id": connection.id, "symbol": symbol,
                        "side": side, "amount": amount, "notional_usd": notional,
                        "reason": block_reason, "record_id": record.id,
                    },
                )
                return {"error": block_reason, "blocked_by": "oms", "record_id": record.id}

        # ── Reserva del intento ANTES de tocar el exchange ────────────
        # La comprobación de arriba no basta contra la concurrencia: dos
        # peticiones simultáneas la pasarían las dos y ambas enviarían la orden.
        # Persistir aquí hace que sea la restricción única de la base de datos
        # —y no una comprobación en memoria— la que decida quién llega primero.
        record.status = "pending"
        if not _claim(record, client_order_id):
            return _replay(_existing(owner, client_order_id))

        try:
            order = self._factory(connection).create_order(symbol, side, order_type, amount, price)
        except BrokerError as exc:
            record.status = "failed"
            record.error = str(exc)[:300]
            record.save()
            audit_logger.error(
                "orden manual fallida", extra={
                    "event": "live_order_failed", "user_id": owner.id,
                    "connection_id": connection.id, "symbol": symbol, "side": side,
                    "amount": amount, "error": str(exc), "record_id": record.id,
                },
            )
            return {"error": str(exc), "record_id": record.id}

        record.status = "sent"
        record.broker_order_id = str(order.get("id") or "")[:80]
        fill = order.get("average") or order.get("price")
        record.fill_price = float(fill) if fill else None
        record.save()

        _touch(connection)
        audit_logger.info(
            "orden manual enviada", extra={
                "event": "live_order_sent", "user_id": owner.id,
                "connection_id": connection.id, "symbol": symbol, "side": side,
                "order_type": order_type, "amount": amount,
                "notional_usd": notional, "record_id": record.id,
                "broker_order_id": record.broker_order_id,
                "mode": "testnet" if connection.is_testnet else "REAL",
            },
        )
        return {"order": order, "is_testnet": connection.is_testnet, "record_id": record.id}


def _claim(record, client_order_id: str) -> bool:
    """Persiste el intento reclamando su `client_order_id`.

    Devuelve False si otra petición concurrente ya lo había reclamado — la
    restricción única de la base de datos es la árbitra, no una comprobación
    previa en memoria, que siempre tiene una ventana de carrera.
    """
    from django.db import IntegrityError, transaction

    try:
        with transaction.atomic():
            record.save()
        return True
    except IntegrityError:
        if not client_order_id:
            raise           # No es un choque de idempotencia: es un error real.
        logger.info("client_order_id=%s reclamado por una petición concurrente",
                    client_order_id)
        return False


def _existing(owner, client_order_id: str):
    """El registro que ganó la carrera por ese `client_order_id`."""
    from core.infrastructure.persistence.models import LiveOrderRecord

    return LiveOrderRecord.objects.filter(
        owner=owner, client_order_id=client_order_id,
    ).first()


def _manual_buy_block_reason(owner, symbol: str, notional_usd: float) -> "str | None":
    """Barrera de riesgo para una COMPRA manual: motivo del bloqueo o None.

    Reutiliza literalmente los controles del OMS de la promoción paper→real
    para que ambas vías compartan una única definición de la política.
    """
    from core.application.use_cases.paper_trading import (
        _concentration_blocked, _daily_loss_blocked,
    )

    loss_today = _daily_loss_blocked(owner)
    if loss_today is not None:
        return (f"Límite de pérdida diaria alcanzado ({loss_today:+.2f} USD hoy): "
                "compra no enviada.")

    base = symbol.split("/")[0].upper()
    return _concentration_blocked(owner, base, notional_usd)


def _replay(record) -> dict:
    """Respuesta equivalente al intento ya registrado con ese client_order_id."""
    if record is None:
        # Solo puede pasar si el registro ganador se borró entre el choque y
        # esta lectura. Se responde con un error explícito en vez de reenviar
        # la orden: ante la duda, no se duplica dinero real.
        return {"error": "No se pudo confirmar el estado de la orden; consúltala en el exchange.",
                "idempotent_replay": True}
    if record.status == "pending":
        return {"error": "La orden ya está en curso; espera a que el exchange confirme.",
                "record_id": record.id, "idempotent_replay": True}
    if record.status == "sent":
        return {
            "order": {"id": record.broker_order_id, "symbol": record.symbol,
                      "side": record.side, "amount": record.amount,
                      "price": record.fill_price or record.ref_price},
            "is_testnet": record.is_testnet,
            "record_id": record.id,
            "idempotent_replay": True,
        }
    payload = {"error": record.error or "La orden no se cursó.",
               "record_id": record.id, "idempotent_replay": True}
    if record.status == "blocked":
        payload["blocked_by"] = "oms"
    return payload


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
