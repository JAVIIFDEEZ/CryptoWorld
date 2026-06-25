"""
get_whale_movements.py — Caso de uso: mayores movimientos on-chain recientes.

Fuente: Blockscout API REST v2, por red.

Inspirado en herramientas tipo Whale Alert / Arkham / Etherscan "large txns":
combina las transferencias recientes de la moneda nativa (`/transactions`) y de
tokens ERC-20 (`/token-transfers`), las valora en USD, descarta las pequeñas y
devuelve las MAYORES ordenadas por valor. Surfacea además etiquetas de entidad
(exchange, contrato, ENS) cuando Blockscout las conoce, para leer el flujo de un
vistazo ("de wallet desconocida a Binance").

Honestidad de alcance: son los mayores movimientos entre las transacciones
RECIENTES (últimas páginas indexadas), no un histórico global —Blockscout no
permite ordenar por valor en el servidor—. La UI lo deja claro.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_NATIVE_DECIMALS = 18


def _to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _adjust(raw_amount, decimals) -> float:
    amount = _to_float(raw_amount)
    dec = int(_to_float(decimals, 0))
    return amount / (10 ** dec) if dec >= 0 else amount


def _party(obj: dict) -> dict:
    """Extrae {address, label, is_contract} de un nodo from/to de Blockscout.
    `label` es el nombre de entidad si lo hay (etiqueta pública, ENS, contrato)."""
    obj = obj or {}
    label = obj.get("name") or obj.get("ens_domain_name")
    if not label:
        tags = (obj.get("metadata") or {}).get("tags") or []
        named = [t.get("name") for t in tags if t.get("name") and t.get("tagType") in ("name", "generic", "classifier")]
        if named:
            label = named[0]
    if not label:
        public = obj.get("public_tags") or []
        if public:
            label = public[0] if isinstance(public[0], str) else public[0].get("display_name")
    return {"address": obj.get("hash"), "label": label or None, "is_contract": bool(obj.get("is_contract"))}


class GetWhaleMovementsUseCase:
    """Mayores movimientos on-chain recientes (nativos + tokens) por valor en USD."""

    def __init__(self, client: Optional["object"] = None) -> None:
        from core.infrastructure.external_apis.blockscout_client import BlockscoutClient
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, min_usd: float = 100_000.0, limit: int = 25,
                pages: int = 2) -> dict:
        from core.infrastructure.external_apis.blockscout_client import (
            CHAINS, SUPPORTED_CHAINS, BlockscoutClientError,
        )

        chain = (chain or "").strip().lower()
        if chain not in SUPPORTED_CHAINS:
            return {"error": f"Red '{chain}' no soportada. Disponibles: {SUPPORTED_CHAINS}"}

        min_usd = max(_to_float(min_usd, 100_000.0), 0.0)
        limit = min(max(int(limit), 1), 100)
        pages = min(max(int(pages), 1), 5)
        meta = CHAINS[chain]

        try:
            stats = self._client.get_chain_stats(chain)
        except BlockscoutClientError:
            stats = {}
        coin_price = _to_float(stats.get("coin_price"))

        # Cada fuente se consulta de forma independiente: si una falla (timeout,
        # endpoint no disponible en esa instancia), seguimos con la otra en vez de
        # dejar la tabla vacía. Solo erramos si fallan AMBAS.
        native_txs, native_err = self._safe(lambda: self._client.get_recent_transactions(chain, pages=pages))
        token_txs, token_err = self._safe(lambda: self._client.get_recent_token_transfers(chain, pages=pages))
        if native_err and token_err:
            logger.warning("whale_movements %s: ambas fuentes fallaron: %s / %s", chain, native_err, token_err)
            return {"error": native_err or token_err}

        movements = []
        movements.extend(self._native_movements(native_txs, coin_price, meta["native"]))
        movements.extend(self._token_movements(token_txs))

        movements = [m for m in movements if m["value_usd"] is not None and m["value_usd"] >= min_usd]
        movements.sort(key=lambda m: m["value_usd"], reverse=True)
        top = movements[:limit]

        for m in top:
            m["explorer_url"] = f"{meta['base_url']}/tx/{m['hash']}" if m["hash"] else None

        return {
            "chain": chain,
            "chain_name": meta["name"],
            "native_symbol": meta["native"],
            "min_usd": min_usd,
            "scanned": len(native_txs) + len(token_txs),
            "count": len(top),
            "movements": top,
            "partial": bool(native_err or token_err),
            "note": "Mayores movimientos entre las transacciones recientes (no histórico global).",
            "source": "blockscout",
        }

    @staticmethod
    def _safe(fn):
        """Ejecuta una consulta y captura su error: devuelve (items, error_str)."""
        from core.infrastructure.external_apis.blockscout_client import BlockscoutClientError
        try:
            return fn() or [], None
        except BlockscoutClientError as exc:
            return [], str(exc)
        except Exception as exc:  # noqa: BLE001 — una fuente rota no debe tumbar el feed
            return [], str(exc)

    @staticmethod
    def _native_movements(txs: list, coin_price: float, symbol: str) -> list:
        out = []
        for tx in txs:
            amount = _adjust(tx.get("value"), _NATIVE_DECIMALS)
            if amount <= 0:
                continue  # interacción con contrato sin transferencia de valor
            value_usd = round(amount * coin_price, 2) if coin_price else None
            out.append({
                "kind": "native",
                "symbol": symbol,
                "amount": round(amount, 6),
                "value_usd": value_usd,
                "from": _party(tx.get("from") or {}),
                "to": _party(tx.get("to") or {}),
                "hash": tx.get("hash"),
                "method": tx.get("method"),
                "timestamp": tx.get("timestamp"),
            })
        return out

    @staticmethod
    def _token_movements(transfers: list) -> list:
        out = []
        for tr in transfers:
            token = tr.get("token") or {}
            if (token.get("type") or "").upper() not in ("ERC-20", "ERC20"):
                continue
            total = tr.get("total") or {}
            decimals = total.get("decimals", token.get("decimals"))
            if decimals in (None, ""):
                continue
            amount = _adjust(total.get("value"), decimals)
            if amount <= 0:
                continue
            price = _to_float(token.get("exchange_rate"))
            value_usd = round(amount * price, 2) if price else None
            out.append({
                "kind": "token",
                "symbol": token.get("symbol") or "?",
                "token_name": token.get("name"),
                "amount": round(amount, 6),
                "value_usd": value_usd,
                "from": _party(tr.get("from") or {}),
                "to": _party(tr.get("to") or {}),
                "hash": tr.get("tx_hash") or tr.get("transaction_hash"),
                "method": tr.get("method"),
                "timestamp": tr.get("timestamp") or tr.get("block_timestamp"),
            })
        return out
