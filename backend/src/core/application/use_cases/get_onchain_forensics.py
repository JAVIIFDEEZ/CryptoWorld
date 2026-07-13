"""
get_onchain_forensics.py — Casos de uso del submódulo forense on-chain.

Orquesta el cliente Blockscout (multi-cadena, datos reales) con el dominio puro
(onchain_forensics). Tres capacidades:

  · TraceFlowUseCase:          árbol de flujo saliente de una dirección + patrones.
  · TokenConcentrationUseCase: radiografía de concentración de un token (Gini/HHI).
  · WalletFingerprintUseCase:  huella conductual de una dirección (heatmap/arquetipo).

Cada uno normaliza las transacciones/tenedores del explorador a la forma que el
dominio espera y devuelve un payload JSON-safe. Cacheado por (cadena, objetivo).
"""

import logging
import time

from core.domain.services import onchain_forensics as forensics
from core.infrastructure.external_apis.blockscout_client import (
    BlockscoutClient, BlockscoutClientError, is_valid_address,
)

logger = logging.getLogger(__name__)

_CACHE_TTL = 600  # 10 min


def _to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _iso_to_epoch(value) -> int:
    """Timestamp de Blockscout (ISO-8601) → epoch segundos. 0 si no se puede."""
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        from datetime import datetime
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return 0


def _normalize_native_txs(raw: list[dict]) -> list[dict]:
    """Transacciones nativas de Blockscout → [{from,to,value,timestamp}] con
    direcciones en minúsculas y value en unidades del nativo (wei → ETH)."""
    out = []
    for tx in raw or []:
        frm = ((tx.get("from") or {}).get("hash") or "").lower()
        to = ((tx.get("to") or {}).get("hash") or "").lower()
        if not frm:
            continue
        out.append({
            "from": frm,
            "to": to or None,
            "value": _to_float(tx.get("value")) / 1e18,   # wei → nativo
            "timestamp": _iso_to_epoch(tx.get("timestamp")),
        })
    return out


class TraceFlowUseCase:
    """Árbol de flujo saliente de una dirección con detección de patrones."""

    def __init__(self, client=None):
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, address: str, depth: int = 2) -> dict:
        if not is_valid_address(address):
            return {"error": "Dirección EVM no válida (esperado 0x + 40 hex)."}
        from django.core.cache import cache

        depth = max(1, min(int(depth), 3))
        key = f"forensics_flow:{chain}:{address.lower()}:{depth}"
        cached = cache.get(key)
        if cached is not None:
            return cached

        def fetch(addr: str) -> list[dict]:
            return _normalize_native_txs(self._client.get_transactions(chain, addr))

        try:
            tree = forensics.build_flow_tree(address, fetch, depth=depth)
        except BlockscoutClientError as exc:
            return {"error": str(exc)}
        result = {"status": "OK", "chain": chain, "address": address.lower(), **tree,
                  "note": ("Flujo SALIENTE de valor nativo, top contrapartes por salto. "
                           "Etiquetas de patrón (fan-out, peel chain) son heurísticas.")}
        cache.set(key, result, _CACHE_TTL)
        return result


class TokenConcentrationUseCase:
    """Radiografía de concentración de tenedores de un token ERC-20."""

    def __init__(self, client=None):
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, token: str) -> dict:
        if not is_valid_address(token):
            return {"error": "Dirección de token EVM no válida."}
        from django.core.cache import cache

        key = f"forensics_conc:{chain}:{token.lower()}"
        cached = cache.get(key)
        if cached is not None:
            return cached

        try:
            info = self._client.get_token_info(chain, token)
            raw_holders = self._client.get_token_holders(chain, token, pages=1)
        except BlockscoutClientError as exc:
            return {"error": str(exc)}

        decimals = int(_to_float((info or {}).get("decimals"), 18))
        holders = []
        for h in raw_holders or []:
            addr_obj = h.get("address") or {}
            holders.append({
                "address": addr_obj.get("hash"),
                "value": _to_float(h.get("value")) / (10 ** decimals if decimals >= 0 else 1),
                "is_contract": bool(addr_obj.get("is_contract")),
            })
        total = None
        try:
            total = int(_to_float((info or {}).get("holders") or (info or {}).get("holders_count")))
        except (TypeError, ValueError):
            total = None

        conc = forensics.holder_concentration(holders, holders_count_total=total or None)
        result = {
            "status": "OK", "chain": chain, "token": token.lower(),
            "token_name": (info or {}).get("name"),
            "token_symbol": (info or {}).get("symbol"),
            "concentration": conc,
        }
        cache.set(key, result, _CACHE_TTL)
        return result


class WalletFingerprintUseCase:
    """Huella conductual de una dirección (heatmap, cadencia, arquetipo)."""

    def __init__(self, client=None):
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, address: str, now_ts: int | None = None) -> dict:
        if not is_valid_address(address):
            return {"error": "Dirección EVM no válida (esperado 0x + 40 hex)."}
        from django.core.cache import cache

        key = f"forensics_fp:{chain}:{address.lower()}"
        cached = cache.get(key)
        if cached is not None:
            return cached

        try:
            raw = self._client.get_transactions(chain, address)
        except BlockscoutClientError as exc:
            return {"error": str(exc)}

        txs = _normalize_native_txs(raw)
        fp = forensics.wallet_fingerprint(
            address, txs, now_ts if now_ts is not None else int(time.time()))
        result = {"status": "OK", "chain": chain, "address": address.lower(),
                  "fingerprint": fp}
        cache.set(key, result, _CACHE_TTL)
        return result
