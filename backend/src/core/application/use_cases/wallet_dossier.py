"""
wallet_dossier.py — Dossier de inteligencia de una dirección (Blockchain).

Cruza TODO lo que el sistema sabe de una wallet en una sola vista:
  · Perfil base (Blockscout): balance, actividad, etiquetas públicas.
  · Contrapartes: con quién opera (top por nº de interacciones y volumen),
    marcando cuáles son exchanges (mismo etiquetado que el escáner de presión).
  · Comportamiento: % de actividad contra exchanges, flujo neto enviado/recibido
    y una lectura heurística honesta (acumulación/distribución/mixto).
  · Cruce con el HISTÓRICO PROPIO: apariciones en los movimientos de ballenas
    registrados por el escáner (WhaleMovementSnapshot) y su clasificación.
  · Presencia multi-cadena: en qué otras redes soportadas existe la dirección
    (mismo hash EVM), con su balance nativo.

Todos los datos son reales (Blockscout + histórico propio); cuando una fuente
falla se degrada por partes con `partial=True`, nunca con una página rota.
"""

import logging
from typing import Optional

from core.domain.services.onchain_flow import is_exchange_label
from core.infrastructure.external_apis.blockscout_client import (
    SUPPORTED_CHAINS,
    BlockscoutClient,
    BlockscoutClientError,
    is_valid_address,
)

logger = logging.getLogger(__name__)

_MAX_COUNTERPARTIES = 8
_MULTICHAIN_LIMIT = 6   # nº de redes a sondear para la presencia multi-cadena


def _to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _wei(value) -> float:
    return _to_float(value) / 1e18


def _party_label(party: dict | None) -> str | None:
    """Etiqueta pública de una contraparte según Blockscout (nombre o tags)."""
    if not party:
        return None
    name = party.get("name")
    if name:
        return str(name)
    tags = party.get("public_tags") or party.get("metadata", {}).get("tags") if isinstance(party.get("metadata"), dict) else None
    if isinstance(tags, list) and tags:
        first = tags[0]
        return str(first.get("name") if isinstance(first, dict) else first)
    return None


class WalletDossierUseCase:
    """Construye el dossier cruzado de una dirección."""

    def __init__(self, client: Optional[BlockscoutClient] = None) -> None:
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, address: str) -> dict:
        chain = (chain or "").lower().strip()
        address = (address or "").strip()
        if chain not in SUPPORTED_CHAINS:
            return {"error": f"Red '{chain}' no soportada. Disponibles: {SUPPORTED_CHAINS}"}
        if not is_valid_address(address):
            return {"error": "Dirección no válida (se espera un hash EVM 0x…)."}

        partial = False

        # ── Perfil base ──
        profile: dict = {}
        try:
            info = self._client.get_address(chain, address)
            profile = {
                "balance_native": round(_wei(info.get("coin_balance")), 8),
                "exchange_rate": _to_float(info.get("exchange_rate"), 0.0) or None,
                "tx_count": int(_to_float(info.get("transactions_count") or info.get("transaction_count"), 0)),
                "is_contract": bool(info.get("is_contract")),
                "public_label": _party_label(info),
                "is_exchange": is_exchange_label(_party_label(info)),
            }
            rate = profile["exchange_rate"]
            profile["balance_usd"] = round(profile["balance_native"] * rate, 2) if rate else None
        except (BlockscoutClientError, Exception) as exc:  # noqa: BLE001
            logger.warning("dossier perfil %s/%s: %s", chain, address, exc)
            partial = True

        # ── Contrapartes y comportamiento (transacciones recientes) ──
        counterparties: list[dict] = []
        behavior: dict = {}
        try:
            txs = self._client.get_transactions(chain, address)
            agg: dict[str, dict] = {}
            sent = received = 0.0
            to_exchange = from_exchange = 0
            addr_lower = address.lower()
            for tx in txs:
                frm, to = tx.get("from") or {}, tx.get("to") or {}
                outgoing = (frm.get("hash") or "").lower() == addr_lower
                party = to if outgoing else frm
                p_hash = (party.get("hash") or "").lower()
                if not p_hash or p_hash == addr_lower:
                    continue
                value = _wei(tx.get("value"))
                label = _party_label(party)
                entry = agg.setdefault(p_hash, {
                    "address": party.get("hash"), "label": label,
                    "is_exchange": is_exchange_label(label),
                    "txs": 0, "sent_native": 0.0, "received_native": 0.0,
                })
                if label and not entry["label"]:
                    entry["label"], entry["is_exchange"] = label, is_exchange_label(label)
                entry["txs"] += 1
                if outgoing:
                    entry["sent_native"] += value
                    sent += value
                    to_exchange += int(entry["is_exchange"])
                else:
                    entry["received_native"] += value
                    received += value
                    from_exchange += int(entry["is_exchange"])

            counterparties = sorted(agg.values(), key=lambda e: e["txs"], reverse=True)[:_MAX_COUNTERPARTIES]
            for e in counterparties:
                e["sent_native"] = round(e["sent_native"], 6)
                e["received_native"] = round(e["received_native"], 6)

            n_analyzed = len(txs)
            exch_txs = to_exchange + from_exchange
            # Lectura heurística: retirar de exchanges = acumular; depositar = distribuir.
            if exch_txs >= 3 and from_exchange > to_exchange * 1.5:
                reading = "ACUMULA: retira de exchanges más de lo que deposita."
            elif exch_txs >= 3 and to_exchange > from_exchange * 1.5:
                reading = "DISTRIBUYE: deposita en exchanges más de lo que retira."
            elif exch_txs > 0:
                reading = "Actividad mixta con exchanges, sin sesgo claro."
            else:
                reading = "Sin interacción reciente con exchanges conocidos."
            behavior = {
                "txs_analyzed": n_analyzed,
                "sent_native": round(sent, 6),
                "received_native": round(received, 6),
                "net_native": round(received - sent, 6),
                "exchange_interaction_pct": round(exch_txs / n_analyzed * 100.0, 1) if n_analyzed else 0.0,
                "deposits_to_exchange": to_exchange,
                "withdrawals_from_exchange": from_exchange,
                "reading": reading,
            }
        except (BlockscoutClientError, Exception) as exc:  # noqa: BLE001
            logger.warning("dossier contrapartes %s/%s: %s", chain, address, exc)
            partial = True

        # ── Cruce con el histórico propio del escáner de ballenas ──
        whale_history = self._whale_history(chain, address)

        # ── Presencia multi-cadena (mismo hash EVM en otras redes) ──
        multichain = self._multichain_presence(chain, address)

        return {
            "chain": chain,
            "address": address,
            "profile": profile,
            "counterparties": counterparties,
            "behavior": behavior,
            "whale_history": whale_history,
            "multichain": multichain,
            "partial": partial,
            "note": (
                "Dossier cruzado: perfil y contrapartes vía Blockscout (datos reales), "
                "apariciones en el histórico propio del escáner de ballenas y presencia "
                "de la misma dirección en otras redes EVM soportadas."
            ),
        }

    @staticmethod
    def _whale_history(chain: str, address: str) -> dict:
        """Apariciones de la dirección en los movimientos grandes registrados
        por el escáner periódico (histórico propio, no una API externa)."""
        try:
            from django.db.models import Q, Sum
            from core.infrastructure.persistence.models import WhaleMovementSnapshot

            qs = WhaleMovementSnapshot.objects.filter(
                Q(from_address__iexact=address) | Q(to_address__iexact=address)
            )
            total = qs.count()
            if total == 0:
                return {"appearances": 0, "note": "Sin apariciones en el histórico del escáner."}
            as_sender = qs.filter(from_address__iexact=address)
            as_receiver = qs.filter(to_address__iexact=address)
            usd = qs.aggregate(v=Sum("value_usd"))["v"] or 0.0
            recent = [
                {
                    "chain": m.chain, "symbol": m.symbol,
                    "value_usd": m.value_usd, "direction_flow": m.direction,
                    "direction": "out" if (m.from_address or "").lower() == address.lower() else "in",
                    "moved_at": m.moved_at.isoformat() if m.moved_at else None,
                }
                for m in qs.order_by("-moved_at")[:5]
            ]
            return {
                "appearances": total,
                "as_sender": as_sender.count(),
                "as_receiver": as_receiver.count(),
                "total_usd": round(float(usd), 2),
                "recent": recent,
            }
        except Exception as exc:  # noqa: BLE001 — el cruce nunca rompe el dossier
            logger.warning("dossier whale_history: %s", exc)
            return {"appearances": 0, "note": "Histórico no disponible."}

    def _multichain_presence(self, home_chain: str, address: str) -> list[dict]:
        """Sondea la dirección en las demás redes soportadas: una wallet EVM
        conserva el hash entre cadenas, así que balance o actividad en otra red
        es presencia real (puentes, multi-chain farming…)."""
        out: list[dict] = []
        others = [c for c in SUPPORTED_CHAINS if c != home_chain][:_MULTICHAIN_LIMIT]
        for chain in others:
            try:
                info = self._client.get_address(chain, address)
                balance = _wei(info.get("coin_balance"))
                txs = int(_to_float(info.get("transactions_count") or info.get("transaction_count"), 0))
                if balance > 0 or txs > 0:
                    out.append({
                        "chain": chain,
                        "balance_native": round(balance, 8),
                        "tx_count": txs,
                    })
            except Exception:  # noqa: BLE001 — una red caída no rompe el resto
                continue
        return out
