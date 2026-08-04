"""
get_chain_health.py — Caso de uso: salud de red y rastreador de gas.

Fuente: Blockscout API REST v2 (`/api/v2/stats`), por red.

Consolida el estado actual de una cadena: precios de gas (lento/medio/rápido en
Gwei), utilización de la red, tiempo medio de bloque, precio del nativo y totales
(transacciones, bloques, direcciones). Clasifica el coste de gas como
barato/normal/caro con umbrales específicos por red (en L2 el gas es órdenes de
magnitud menor que en Ethereum mainnet), para un aviso accionable de "buen
momento para operar".
"""

import logging
from typing import Optional

from core.infrastructure.external_apis.blockscout_client import (
    CHAINS,
    BlockscoutClient,
    BlockscoutClientError,
    SUPPORTED_CHAINS,
)

logger = logging.getLogger(__name__)


def _to_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class GetChainHealthUseCase:
    """Salud de red + rastreador de gas de una cadena soportada."""

    def __init__(self, client: Optional[BlockscoutClient] = None) -> None:
        self._client = client or BlockscoutClient()

    def execute(self, chain: str) -> dict:
        chain = (chain or "").strip().lower()
        if chain not in SUPPORTED_CHAINS:
            return {"error": f"Red '{chain}' no soportada. Disponibles: {SUPPORTED_CHAINS}"}

        try:
            stats = self._client.get_chain_stats(chain)
        except BlockscoutClientError as exc:
            logger.warning("chain_health %s: %s", chain, exc)
            # Repliegue al almacén propio antes de rendirse. Una API pública sin
            # clave falla a menudo, y hasta ahora eso dejaba el panel en blanco.
            return self._from_store(chain, str(exc))

        meta = CHAINS[chain]
        gas = stats.get("gas_prices") or {}
        gas_slow = _to_float(gas.get("slow"))
        gas_avg = _to_float(gas.get("average"))
        gas_fast = _to_float(gas.get("fast"))

        block_time_ms = _to_float(stats.get("average_block_time"))
        payload_metrics = {
            "gas_slow": gas_slow, "gas_average": gas_avg, "gas_fast": gas_fast,
            "network_utilization_pct": _to_float(stats.get("network_utilization_percentage")),
            "block_time_sec": round(block_time_ms / 1000.0, 2) if block_time_ms else None,
            "transactions_today": _to_float(stats.get("transactions_today")),
            "coin_price_usd": _to_float(stats.get("coin_price")),
        }

        # Acumulación oportunista: todo lo que se trae de fuera se guarda. Es lo
        # que convierte el módulo de una foto en una serie, y lo que permite
        # sobrevivir a la próxima caída de la fuente.
        gas_context = None
        try:
            from core.application.use_cases import chain_metrics_store as store
            store.persist_metrics(chain, payload_metrics, source="blockscout")
            if gas_avg is not None:
                gas_context = store.percentile_of(chain, "gas_average", gas_avg)
        except Exception:  # noqa: BLE001 — persistir nunca rompe una consulta
            logger.debug("chain_health %s: almacén no disponible", chain, exc_info=True)

        gas_level, gas_text, gas_basis = self._classify_gas(gas_avg, meta, gas_context)

        return {
            "stale": False,
            "gas_percentile": gas_context,
            "gas_basis": gas_basis,
            "chain": chain,
            "chain_name": meta["name"],
            "native_symbol": meta["native"],
            "explorer_url": meta["base_url"],
            "gas_slow": gas_slow,
            "gas_average": gas_avg,
            "gas_fast": gas_fast,
            "gas_level": gas_level,          # cheap | normal | high | unknown
            "gas_text": gas_text,
            "gas_unit": "Gwei",
            "gas_updated_at": stats.get("gas_price_updated_at"),
            "network_utilization_pct": _to_float(stats.get("network_utilization_percentage")),
            "block_time_sec": round(block_time_ms / 1000.0, 2) if block_time_ms else None,
            "coin_price_usd": _to_float(stats.get("coin_price")),
            "coin_price_change_pct": _to_float(stats.get("coin_price_change_percentage")),
            "total_transactions": stats.get("total_transactions"),
            "total_blocks": stats.get("total_blocks"),
            "total_addresses": stats.get("total_addresses"),
            "transactions_today": stats.get("transactions_today"),
            "source": "blockscout",
        }

    def _from_store(self, chain: str, reason: str) -> dict:
        """
        Última lectura guardada, marcada como VIEJA.

        Mostrar un dato de hace tres horas como si fuera de ahora sería peor que
        no mostrar nada. Mostrarlo con su edad es mejor que un panel en blanco,
        que es lo que había antes. La distinción la marca `stale`, y quien pinte
        la pantalla tiene la obligación de reflejarla.
        """
        meta = CHAINS[chain]
        try:
            from core.application.use_cases import chain_metrics_store as store
            snap = store.latest(chain, store.HEALTH_METRICS)
        except Exception:  # noqa: BLE001 — sin BD no hay repliegue posible
            return {"error": reason}

        if not snap.get("metrics"):
            return {"error": reason}

        m = snap["metrics"]
        gas_avg = m.get("gas_average")
        gas_level, gas_text, gas_basis = self._classify_gas(gas_avg, meta, None)
        age_min = (snap["age_seconds"] or 0) // 60
        return {
            "stale": True,
            "stale_reason": reason,
            "data_age_seconds": snap["age_seconds"],
            "chain": chain,
            "chain_name": meta["name"],
            "native_symbol": meta["native"],
            "explorer_url": meta["base_url"],
            "gas_slow": m.get("gas_slow"),
            "gas_average": gas_avg,
            "gas_fast": m.get("gas_fast"),
            "gas_level": gas_level,
            "gas_text": gas_text,
            "gas_basis": gas_basis,
            "gas_unit": "Gwei",
            "network_utilization_pct": m.get("network_utilization_pct"),
            "block_time_sec": m.get("block_time_sec"),
            "coin_price_usd": m.get("coin_price_usd"),
            "transactions_today": m.get("transactions_today"),
            "source": "store",
            "note": (f"La fuente en vivo no responde. Estos datos son del almacén "
                     f"propio y tienen {age_min} min de antigüedad."),
        }

    @staticmethod
    def _classify_gas(gas_avg, meta, context: dict | None) -> tuple[str, str, str]:
        """
        Clasifica el gas como barato/normal/caro.

        Con historia suficiente manda el PERCENTIL sobre la propia serie de esa
        red: «más barato que el 82 % de los últimos 30 días» se autocalibra y
        sigue siendo cierto dentro de un año. Los umbrales fijos (10/30 Gwei)
        son constantes arbitrarias que envejecen con el mercado, y quedan como
        repliegue mientras el almacén se llena.

        El tercer valor devuelto dice CUÁL de los dos criterios se usó: un
        veredicto sin su base no es interpretable.
        """
        if gas_avg is None:
            return "unknown", "Precio de gas no disponible.", "none"

        if context is not None:
            pct = context["percentile"]
            if pct <= 25.0:
                return ("cheap",
                        f"Gas barato: más bajo que el {100 - pct:.0f}% de los últimos "
                        f"{context['days']} días ({gas_avg:g} Gwei).", "history")
            if pct >= 75.0:
                return ("high",
                        f"Gas caro: por encima del {pct:.0f}% de los últimos "
                        f"{context['days']} días ({gas_avg:g} Gwei).", "history")
            return ("normal",
                    f"Gas en su rango habitual (percentil {pct:.0f} de los últimos "
                    f"{context['days']} días, {gas_avg:g} Gwei).", "history")

        cheap = meta.get("gas_cheap", 10.0)
        high = meta.get("gas_high", 30.0)
        if gas_avg <= cheap:
            return "cheap", f"Gas barato ({gas_avg:g} Gwei): buen momento para operar.", "fixed"
        if gas_avg >= high:
            return "high", f"Gas caro ({gas_avg:g} Gwei): conviene esperar si no es urgente.", "fixed"
        return "normal", f"Gas en niveles normales ({gas_avg:g} Gwei).", "fixed"
