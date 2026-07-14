"""
get_onchain_risk.py — Casos de uso: riesgo, aprobaciones y grafo de entidad.

Orquesta el cliente Blockscout con el dominio puro (onchain_risk). Tres
capacidades de cumplimiento/seguridad sobre datos públicos:

  · AddressRiskUseCase:  puntuación 0-100 (etiquetas de la dirección y sus
                        contrapartes + patrones de flujo).
  · ApprovalsUseCase:    aprobaciones ERC-20 vivas y su peligrosidad.
  · EntityGraphUseCase:  agrupa direcciones que se mueven juntas (co-movimiento).

Cada uno extrae de las transacciones/logs del explorador exactamente lo que el
dominio necesita y cachea por objetivo. Degrada con honestidad si falta un dato.
"""

import logging

from core.domain.services import onchain_risk as risk
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


def _party_label(obj: dict) -> str | None:
    """Etiqueta pública/entidad de un nodo from/to de Blockscout (o None)."""
    obj = obj or {}
    label = obj.get("name") or obj.get("ens_domain_name")
    if not label:
        tags = (obj.get("metadata") or {}).get("tags") or []
        named = [t.get("name") for t in tags if t.get("name")]
        if named:
            label = named[0]
    if not label:
        public = obj.get("public_tags") or []
        if public:
            label = public[0] if isinstance(public[0], str) else (public[0] or {}).get("display_name")
    return label or None


class AddressRiskUseCase:
    """Puntuación de riesgo 0-100 de una dirección."""

    def __init__(self, client=None):
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, address: str) -> dict:
        if not is_valid_address(address):
            return {"error": "Dirección EVM no válida (esperado 0x + 40 hex)."}
        from django.core.cache import cache

        key = f"risk_score:{chain}:{address.lower()}"
        cached = cache.get(key)
        if cached is not None:
            return cached

        try:
            info = self._client.get_address(chain, address)
            raw_txs = self._client.get_transactions(chain, address)
        except BlockscoutClientError as exc:
            return {"error": str(exc)}

        self_labels = [lbl for lbl in [_party_label(info)] if lbl]
        # Contrapartes con su etiqueta (dedup por dirección).
        counterparties: dict[str, dict] = {}
        addr_low = address.lower()
        for tx in raw_txs or []:
            for side in ("from", "to"):
                node = tx.get(side) or {}
                h = (node.get("hash") or "").lower()
                if not h or h == addr_low:
                    continue
                lbl = _party_label(node)
                if h not in counterparties or (lbl and not counterparties[h].get("label")):
                    counterparties[h] = {"address": h, "label": lbl}

        # Patrones: reutiliza el rastreador de flujos a 1 salto (barato).
        patterns = []
        try:
            from core.domain.services import onchain_forensics as forensics
            from core.application.use_cases.get_onchain_forensics import _normalize_native_txs
            flow = forensics.build_flow_tree(
                address, lambda a: _normalize_native_txs(raw_txs) if a == addr_low else [],
                depth=1)
            patterns = flow.get("patterns", [])
        except Exception as exc:  # noqa: BLE001 — los patrones son opcionales
            logger.warning("risk patterns %s: %s", address, exc)

        score = risk.address_risk_score(self_labels, list(counterparties.values()), patterns, None)
        result = {"status": "OK", "chain": chain, "address": addr_low,
                  "self_labels": self_labels, "counterparties_analyzed": len(counterparties),
                  **score}
        cache.set(key, result, _CACHE_TTL)
        return result


class ApprovalsUseCase:
    """Aprobaciones ERC-20 vivas de una dirección y su peligrosidad."""

    def __init__(self, client=None):
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, address: str) -> dict:
        if not is_valid_address(address):
            return {"error": "Dirección EVM no válida (esperado 0x + 40 hex)."}
        from django.core.cache import cache

        key = f"approvals:{chain}:{address.lower()}"
        cached = cache.get(key)
        if cached is not None:
            return cached

        try:
            raw = self._client.get_transactions(chain, address)
        except BlockscoutClientError as exc:
            return {"error": str(exc)}

        approvals = []
        for tx in raw or []:
            if (tx.get("method") or "").lower() != "approve":
                continue
            spender, amount = self._decode_approve(tx.get("decoded_input"))
            if spender is None:
                continue
            token_node = tx.get("to") or {}
            approvals.append({
                "token": (token_node.get("hash") or "").lower(),
                "token_symbol": (token_node.get("name") or "token"),
                "spender": spender.lower(),
                "spender_label": None,       # el input decodificado no trae etiqueta del gastador
                "amount": amount,
                "spender_verified": bool(token_node.get("is_verified")),
                "_ts": tx.get("timestamp"),
            })
        # Orden cronológico ascendente para que analyze_approvals conserve la última.
        approvals.sort(key=lambda a: a.get("_ts") or "")
        for a in approvals:
            a.pop("_ts", None)

        result = {"status": "OK", "chain": chain, "address": address.lower(),
                  **risk.analyze_approvals(approvals)}
        cache.set(key, result, _CACHE_TTL)
        return result

    @staticmethod
    def _decode_approve(decoded_input) -> tuple:
        """Extrae (spender, amount_float | None) de un approve(address,uint256)."""
        if not isinstance(decoded_input, dict):
            return None, None
        params = decoded_input.get("parameters") or []
        spender = None
        amount = None
        for p in params:
            name = (p.get("name") or "").lower()
            val = p.get("value")
            if name in ("spender", "guy", "_spender", "to") or (p.get("type") == "address" and spender is None):
                spender = val
            elif name in ("amount", "value", "wad", "_value", "tokens") or p.get("type", "").startswith("uint"):
                amount = _to_float(val, default=None) if val is not None else None
        return spender, amount


class EntityGraphUseCase:
    """Grafo de entidad: agrupa direcciones que se mueven junto a la raíz."""

    def __init__(self, client=None):
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, address: str, max_neighbors: int = 8) -> dict:
        if not is_valid_address(address):
            return {"error": "Dirección EVM no válida (esperado 0x + 40 hex)."}
        from django.core.cache import cache
        from collections import Counter

        key = f"entity:{chain}:{address.lower()}"
        cached = cache.get(key)
        if cached is not None:
            return cached

        addr_low = address.lower()
        try:
            root_txs = self._client.get_transactions(chain, address)
        except BlockscoutClientError as exc:
            return {"error": str(exc)}

        # Aristas raíz↔contraparte por nº de transferencias (fuerza de conexión).
        edge_weight: Counter = Counter()
        counterparty_freq: Counter = Counter()
        for tx in root_txs or []:
            for side in ("from", "to"):
                h = ((tx.get(side) or {}).get("hash") or "").lower()
                if h and h != addr_low:
                    counterparty_freq[h] += 1
        top = [a for a, _ in counterparty_freq.most_common(max_neighbors)]
        for a in top:
            edge_weight[(addr_low, a)] = counterparty_freq[a]

        # Segundo salto: aristas entre las contrapartes principales (co-movimiento).
        neighbor_set = set(top)
        for a in top:
            try:
                txs = self._client.get_transactions(chain, a)
            except BlockscoutClientError:
                continue
            for tx in txs or []:
                for side in ("from", "to"):
                    h = ((tx.get(side) or {}).get("hash") or "").lower()
                    if h and h != a and h in neighbor_set:
                        pair = tuple(sorted((a, h)))
                        edge_weight[pair] += 1

        edges = [{"a": p[0], "b": p[1], "weight": w} for p, w in edge_weight.items()]
        graph = risk.build_entity_graph(address, edges, min_weight=2.0)
        result = {"status": "OK", "chain": chain, "neighbors_scanned": len(top), **graph}
        cache.set(key, result, _CACHE_TTL)
        return result
