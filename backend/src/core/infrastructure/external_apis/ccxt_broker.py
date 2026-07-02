"""
ccxt_broker.py — Adaptador de trading real multi-exchange (ccxt).

ccxt es el estándar de facto para operar contra exchanges con una API unificada
(Binance, Kraken, Coinbase, Bybit, OKX…). Este adaptador construye el cliente a
partir de una ExchangeConnection (descifrando las credenciales SOLO aquí), activa
el sandbox del exchange cuando la conexión es testnet, y expone las operaciones
mínimas del panel manual: balance, ticker, crear orden, órdenes abiertas y
cancelación — con errores traducidos a mensajes accionables.

Principio: Adapter Pattern (Arquitectura Hexagonal). Ninguna otra capa importa
ccxt ni ve credenciales en claro.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_EXCHANGES = ("binance", "kraken", "coinbase", "bybit", "okx")

# Exchanges cuyo sandbox soporta ccxt.set_sandbox_mode. Para el resto, testnet
# se rechaza con un mensaje claro en lugar de operar en real por sorpresa.
SANDBOX_CAPABLE = ("binance", "bybit", "okx")


class BrokerError(Exception):
    """Error operando contra el exchange, con mensaje apto para el usuario."""


def _friendly(exc: Exception) -> str:
    import ccxt

    if isinstance(exc, ccxt.AuthenticationError):
        return "Credenciales rechazadas por el exchange: revisa la API key y sus permisos."
    if isinstance(exc, ccxt.InsufficientFunds):
        return "Fondos insuficientes para esta orden."
    if isinstance(exc, ccxt.InvalidOrder):
        return f"Orden inválida para el exchange: {exc}"
    if isinstance(exc, ccxt.BadSymbol):
        return "Par no soportado por el exchange (usa el formato BASE/QUOTE, p. ej. BTC/USDT)."
    if isinstance(exc, ccxt.RateLimitExceeded):
        return "Límite de peticiones del exchange alcanzado: espera unos segundos."
    if isinstance(exc, ccxt.NetworkError):
        return "Error de red hablando con el exchange: reintenta."
    return f"Error del exchange: {exc}"


class CcxtBroker:
    """Cliente de trading construido desde una ExchangeConnection."""

    def __init__(self, connection) -> None:
        import ccxt

        exchange_id = connection.exchange
        if exchange_id not in SUPPORTED_EXCHANGES:
            raise BrokerError(f"Exchange '{exchange_id}' no soportado.")
        if connection.is_testnet and exchange_id not in SANDBOX_CAPABLE:
            raise BrokerError(
                f"{exchange_id} no ofrece sandbox vía ccxt: desactiva el modo testnet "
                f"explícitamente si quieres operar en real."
            )

        from core.infrastructure.security.crypto import decrypt_secret

        params: dict[str, Any] = {
            "apiKey": decrypt_secret(connection.api_key_enc),
            "secret": decrypt_secret(connection.api_secret_enc),
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        if connection.api_password_enc:
            params["password"] = decrypt_secret(connection.api_password_enc)

        self._client = getattr(ccxt, exchange_id)(params)
        if connection.is_testnet:
            self._client.set_sandbox_mode(True)

    # ── Operaciones ────────────────────────────────────────────────

    def fetch_balance(self) -> dict:
        """Saldos con total > 0, ordenados por total descendente."""
        try:
            raw = self._client.fetch_balance()
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(_friendly(exc)) from exc
        totals = raw.get("total") or {}
        free = raw.get("free") or {}
        used = raw.get("used") or {}
        rows = [
            {"asset": k, "total": float(v), "free": float(free.get(k) or 0.0),
             "used": float(used.get(k) or 0.0)}
            for k, v in totals.items()
            if v and float(v) > 0
        ]
        rows.sort(key=lambda r: r["total"], reverse=True)
        return {"balances": rows}

    def fetch_ticker(self, symbol: str) -> dict:
        try:
            t = self._client.fetch_ticker(symbol)
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(_friendly(exc)) from exc
        return {"symbol": symbol, "last": t.get("last"), "bid": t.get("bid"), "ask": t.get("ask")}

    def create_order(self, symbol: str, side: str, order_type: str,
                     amount: float, price: float | None = None) -> dict:
        try:
            order = self._client.create_order(
                symbol=symbol, type=order_type, side=side, amount=amount, price=price,
            )
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(_friendly(exc)) from exc
        return _order_dto(order)

    def fetch_open_orders(self, symbol: str | None = None) -> list[dict]:
        try:
            orders = self._client.fetch_open_orders(symbol)
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(_friendly(exc)) from exc
        return [_order_dto(o) for o in orders]

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        try:
            self._client.cancel_order(order_id, symbol)
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(_friendly(exc)) from exc
        return {"id": order_id, "status": "canceled"}


def _order_dto(order: dict) -> dict:
    return {
        "id": str(order.get("id")),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "type": order.get("type"),
        "amount": order.get("amount"),
        "price": order.get("price"),
        "filled": order.get("filled"),
        "average": order.get("average"),
        "status": order.get("status"),
        "datetime": order.get("datetime"),
    }
