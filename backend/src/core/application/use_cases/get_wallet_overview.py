"""
get_wallet_overview.py — Caso de uso: explorador on-chain de una wallet.

Fuente: Blockscout API REST v2 (gratuita, sin auth), multi-cadena.

Dada una dirección y una red, consolida un retrato on-chain REAL:
  · saldo nativo (ETH/xDAI…) y su valor en USD,
  · cartera de tokens ERC-20 valorada y ordenada por valor en USD,
  · valor total estimado de la cartera,
  · transacciones recientes (con dirección entrante/saliente),
  · si la dirección es un contrato y su nombre ENS.

Toda la aritmética de saldos ajusta por los `decimals` de cada token (los saldos
on-chain vienen en la unidad mínima, sin decimales).
"""

import logging
from typing import Optional

from core.infrastructure.external_apis.blockscout_client import (
    BlockscoutClient,
    BlockscoutClientError,
    SUPPORTED_CHAINS,
    is_valid_address,
)

logger = logging.getLogger(__name__)

_MAX_TOKENS = 25       # tokens mostrados (ordenados por valor USD)
_MAX_TXS = 15          # transacciones recientes mostradas


def _to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _adjust(raw_amount, decimals) -> float:
    """Convierte un saldo en unidades mínimas a su valor real según `decimals`."""
    amount = _to_float(raw_amount)
    dec = int(_to_float(decimals, 0))
    return amount / (10 ** dec) if dec >= 0 else amount


class GetWalletOverviewUseCase:
    """Retrato on-chain consolidado de una dirección en una red soportada."""

    def __init__(self, client: Optional[BlockscoutClient] = None) -> None:
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, address: str) -> dict:
        chain = (chain or "").strip().lower()
        address = (address or "").strip()

        if chain not in SUPPORTED_CHAINS:
            return {"error": f"Red '{chain}' no soportada. Disponibles: {SUPPORTED_CHAINS}"}
        if not is_valid_address(address):
            return {"error": "Dirección inválida: debe ser 0x seguido de 40 caracteres hexadecimales."}

        try:
            info = self._client.get_address(chain, address)
            tokens_raw = self._client.get_token_balances(chain, address)
            txs_raw = self._client.get_transactions(chain, address)
        except BlockscoutClientError as exc:
            logger.warning("wallet_overview %s/%s: %s", chain, address, exc)
            return {"error": str(exc)}

        from core.infrastructure.external_apis.blockscout_client import CHAINS
        meta = CHAINS[chain]

        # ── Saldo nativo + valoración ──
        native_amount = _adjust(info.get("coin_balance"), 18)
        native_price = _to_float(info.get("exchange_rate"))
        native_value_usd = round(native_amount * native_price, 2) if native_price else None

        # ── Tokens ERC-20 valorados ──
        tokens, tokens_value_usd = self._build_tokens(tokens_raw)

        portfolio_usd = None
        if native_value_usd is not None or tokens_value_usd:
            portfolio_usd = round((native_value_usd or 0.0) + (tokens_value_usd or 0.0), 2)

        return {
            "chain": chain,
            "chain_name": meta["name"],
            "explorer_url": f"{meta['base_url']}/address/{address}",
            "address": address,
            "ens_name": info.get("ens_domain_name"),
            "is_contract": bool(info.get("is_contract")),
            "is_verified": bool(info.get("is_verified")),
            "native_symbol": meta["native"],
            "native_balance": round(native_amount, 8),
            "native_price_usd": native_price or None,
            "native_value_usd": native_value_usd,
            "token_count": len(tokens),
            "tokens_value_usd": tokens_value_usd,
            "portfolio_value_usd": portfolio_usd,
            "tokens": tokens[:_MAX_TOKENS],
            "transactions": self._build_txs(txs_raw, address),
            "source": "blockscout",
        }

    @staticmethod
    def _build_tokens(tokens_raw: list) -> tuple[list, Optional[float]]:
        """Normaliza y valora los tokens ERC-20, ordenados por valor USD desc."""
        out = []
        total = 0.0
        any_priced = False
        for entry in tokens_raw:
            token = entry.get("token") or {}
            if (token.get("type") or "").upper() not in ("ERC-20", "ERC20", ""):
                continue  # solo fungibles; se ignoran NFTs (ERC-721/1155)
            decimals = token.get("decimals")
            if decimals in (None, ""):
                continue
            balance = _adjust(entry.get("value"), decimals)
            if balance <= 0:
                continue
            price = _to_float(token.get("exchange_rate"))
            value_usd = round(balance * price, 2) if price else None
            if value_usd is not None:
                total += value_usd
                any_priced = True
            out.append({
                "address": token.get("address"),
                "name": token.get("name") or "?",
                "symbol": token.get("symbol") or "?",
                "balance": round(balance, 6),
                "price_usd": price or None,
                "value_usd": value_usd,
            })
        # Orden: con valor USD primero (desc), luego por saldo.
        out.sort(key=lambda t: (t["value_usd"] is None, -(t["value_usd"] or 0.0)))
        return out, (round(total, 2) if any_priced else None)

    @staticmethod
    def _build_txs(txs_raw: list, address: str) -> list:
        """Simplifica las transacciones recientes con su dirección (in/out)."""
        addr_lower = address.lower()
        out = []
        for tx in txs_raw[:_MAX_TXS]:
            from_hash = ((tx.get("from") or {}).get("hash") or "").lower()
            to_hash = ((tx.get("to") or {}).get("hash") or "").lower()
            direction = "out" if from_hash == addr_lower else ("in" if to_hash == addr_lower else "self")
            out.append({
                "hash": tx.get("hash"),
                "method": tx.get("method"),
                "direction": direction,
                "from": (tx.get("from") or {}).get("hash"),
                "to": (tx.get("to") or {}).get("hash"),
                "value_native": round(_adjust(tx.get("value"), 18), 8),
                "status": tx.get("status") or tx.get("result"),
                "timestamp": tx.get("timestamp"),
            })
        return out


class GetWalletBalanceHistoryUseCase:
    """Serie diaria del saldo nativo de una dirección (curva de patrimonio
    on-chain). Devuelve el saldo exacto en unidades nativas y, como referencia, su
    valor al precio ACTUAL del nativo (no histórico: Blockscout no da precio por
    día, así que se etiqueta claramente como valoración al precio de hoy)."""

    def __init__(self, client: Optional[BlockscoutClient] = None) -> None:
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, address: str) -> dict:
        chain = (chain or "").strip().lower()
        address = (address or "").strip()
        if chain not in SUPPORTED_CHAINS:
            return {"error": f"Red '{chain}' no soportada. Disponibles: {SUPPORTED_CHAINS}"}
        if not is_valid_address(address):
            return {"error": "Dirección inválida: debe ser 0x seguido de 40 caracteres hexadecimales."}

        try:
            raw = self._client.get_balance_history(chain, address)
            info = self._client.get_address(chain, address)
        except BlockscoutClientError as exc:
            logger.warning("balance_history %s/%s: %s", chain, address, exc)
            return {"error": str(exc)}

        from core.infrastructure.external_apis.blockscout_client import CHAINS
        meta = CHAINS[chain]
        price_now = _to_float(info.get("exchange_rate"))

        history = []
        for point in raw:
            balance = _adjust(point.get("value"), 18)
            history.append({
                "date": point.get("date"),
                "balance": round(balance, 8),
                "value_usd_at_today_price": round(balance * price_now, 2) if price_now else None,
            })
        history.sort(key=lambda p: p["date"] or "")

        return {
            "chain": chain,
            "address": address,
            "native_symbol": meta["native"],
            "price_now_usd": price_now or None,
            "points": len(history),
            "history": history,
            "note": "Saldo nativo exacto por día; la valoración usa el precio actual, no el histórico.",
            "source": "blockscout",
        }


class GetSupportedChainsUseCase:
    """Lista de redes soportadas por el explorador de wallets."""

    def execute(self) -> dict:
        return {"chains": BlockscoutClient.supported_chains()}
