"""
get_multichain_stats.py — Caso de uso: estadísticas on-chain multi-chain.

Fuente: Blockchair API (gratuita, sin auth).
Chains soportadas: BTC, ETH, LTC, DOGE, BCH, XRP, ADA, DOT, XLM, XMR.

El plan gratuito de Blockchair NO devuelve series históricas (las peticiones de
agregación responden HTTP 430), así que este caso de uso solo podía dar una
foto. Una foto de «dificultad: 1,2e14» no dice nada: sin saber de dónde viene,
ese número es ilegible.

Ahora cada lectura se guarda en el almacén propio (`chain_metrics_store`), lo
que aporta las dos cosas que faltaban:

  · **Variación.** Cada estadística viaja con su cambio frente a hace 24 h y 7
    días. «Hashrate +12 % en 7 días» es interpretable; el valor absoluto no.
  · **Repliegue.** Si Blockchair no responde —con ~1 petición/minuto de límite
    y sin clave, ocurre— se sirve la última lectura MARCADA COMO VIEJA en vez
    de dejar el panel vacío, que es lo que pasaba antes.

Para series históricas de BTC también está GetOnChainMetricsUseCase
(Blockchain.com).
"""

import logging
from typing import Optional

from core.infrastructure.external_apis.blockchair_client import (
    BlockchairClient,
    BlockchairClientError,
    SUPPORTED_SYMBOLS,
    COMMON_FIELDS,
    ETH_EXTRA_FIELDS,
)

logger = logging.getLogger(__name__)

# Formato de grandes números para las etiquetas de unidad
_FIELD_FORMATTERS: dict[str, str] = {
    "hashrate_24h": "TH/s",  # se convierte desde H/s
}


def _build_stat_item(key: str, label: str, unit: str, raw_value) -> dict:
    """Construye un ítem de estadística normalizado."""
    value = raw_value
    display_unit = unit

    # Conversión especial: hash rate de H/s a TH/s
    if key == "hashrate_24h" and isinstance(value, (int, float)) and value > 0:
        value = round(value / 1e12, 4)
        display_unit = "TH/s"

    # Conversión wei → ETH para burned_24h
    if key == "burned_24h" and isinstance(value, (int, float)) and value > 0:
        value = round(value / 1e18, 4)
        display_unit = "ETH"

    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": display_unit,
    }


class GetMultiChainStatsUseCase:
    """
    Devuelve estadísticas actuales (snapshot) de una blockchain.

    Soporta: BTC, ETH, LTC, DOGE, BCH, XRP, ADA, DOT, XLM, XMR.
    Para BTC también están disponibles series históricas via Blockchain.com.
    """

    def __init__(self, client: Optional[BlockchairClient] = None) -> None:
        self._client = client or BlockchairClient()

    def execute(self, symbol: str) -> dict:
        symbol = symbol.upper()

        if symbol not in SUPPORTED_SYMBOLS:
            return {
                "error": (
                    f"Chain '{symbol}' no soportada en estadísticas multi-chain. "
                    f"Disponibles: {SUPPORTED_SYMBOLS}"
                ),
                "supported": SUPPORTED_SYMBOLS,
                "stats": [],
            }

        try:
            raw = self._client.get_stats(symbol)
        except BlockchairClientError as exc:
            logger.warning("Blockchair no disponible para %s: %s", symbol, exc)
            return self._from_store(symbol, str(exc))

        stats = []

        # Campos comunes a todas las chains
        for key, label, unit in COMMON_FIELDS:
            value = raw.get(key)
            if value is not None:
                stats.append(_build_stat_item(key, label, unit, value))

        # Campos extra para ETH
        if symbol == "ETH":
            for key, label, unit in ETH_EXTRA_FIELDS:
                value = raw.get(key)
                if value is not None:
                    stats.append(_build_stat_item(key, label, unit, value))

        # Acumulación oportunista + variación frente al propio pasado.
        self._persist(symbol, stats)
        self._annotate_changes(symbol, stats)

        # Extraer best_block_time como dato informativo
        best_block_time = raw.get("best_block_time")
        best_block_height = raw.get("best_block_height")

        return {
            "symbol": symbol,
            "source": "blockchair.com",
            "stale": False,
            "best_block_time": best_block_time,
            "best_block_height": best_block_height,
            "supported": SUPPORTED_SYMBOLS,
            "stats": stats,
        }

    @staticmethod
    def _chain_key(symbol: str) -> str:
        """Clave del almacén. Se prefija para no colisionar con las cadenas EVM
        de Blockscout: `ethereum` (gas, Blockscout) y `ETH` (dificultad,
        Blockchair) son fuentes distintas de la misma red, y mezclarlas daría
        percentiles calculados sobre dos poblaciones diferentes."""
        return f"bc:{symbol.lower()}"

    def _persist(self, symbol: str, stats: list[dict]) -> None:
        """Guarda los valores numéricos de esta lectura (best-effort)."""
        try:
            from core.application.use_cases import chain_metrics_store as store
            numeric = {s["key"]: s["value"] for s in stats
                       if isinstance(s.get("value"), (int, float))
                       and not isinstance(s.get("value"), bool)}
            store.persist_metrics(self._chain_key(symbol), numeric, source="blockchair")
        except Exception:  # noqa: BLE001 — persistir nunca rompe una consulta
            logger.debug("multichain %s: almacén no disponible", symbol, exc_info=True)

    def _annotate_changes(self, symbol: str, stats: list[dict]) -> None:
        """
        Añade a cada estadística su variación frente a 24 h y 7 días atrás.

        Es lo que convierte un número ilegible en información. Si no hay
        histórico suficiente para una ventana, el campo queda a `None` en vez de
        a 0: «sin dato» y «no ha cambiado» son afirmaciones distintas.
        """
        try:
            from core.application.use_cases import chain_metrics_store as store
        except Exception:  # noqa: BLE001
            return

        chain = self._chain_key(symbol)
        for item in stats:
            value = item.get("value")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            for label, days in (("change_24h_pct", 1), ("change_7d_pct", 7)):
                item[label] = _pct_change_vs(store, chain, item["key"], value, days)

    def _from_store(self, symbol: str, reason: str) -> dict:
        """
        Última lectura guardada, marcada como VIEJA.

        Antes, una caída de Blockchair devolvía `stats: []` y el panel se
        quedaba en blanco. Servir lo guardado diciendo su antigüedad es mejor;
        servirlo como si fuera actual sería peor que el panel vacío.
        """
        try:
            from core.application.use_cases import chain_metrics_store as store
            snap = store.latest(self._chain_key(symbol))
        except Exception:  # noqa: BLE001 — sin BD no hay repliegue posible
            return {"error": reason, "supported": SUPPORTED_SYMBOLS, "stats": []}

        if not snap.get("metrics"):
            return {"error": reason, "supported": SUPPORTED_SYMBOLS, "stats": []}

        labels = {k: (lab, unit) for k, lab, unit in COMMON_FIELDS + ETH_EXTRA_FIELDS}
        stats = []
        for key, value in snap["metrics"].items():
            label, unit = labels.get(key, (key, ""))
            # El valor guardado ya está convertido (TH/s, ETH): se reusa la
            # unidad de presentación, no la cruda de la API.
            stats.append({"key": key, "label": label, "value": value,
                          "unit": "TH/s" if key == "hashrate_24h" else
                                  "ETH" if key == "burned_24h" else unit})
        self._annotate_changes(symbol, stats)
        age_min = (snap["age_seconds"] or 0) // 60
        return {
            "symbol": symbol,
            "source": "store",
            "stale": True,
            "stale_reason": reason,
            "data_age_seconds": snap["age_seconds"],
            "supported": SUPPORTED_SYMBOLS,
            "stats": stats,
            "note": (f"Blockchair no responde. Estos datos son del almacén propio "
                     f"y tienen {age_min} min de antigüedad."),
        }

    def get_supported_symbols(self) -> list[str]:
        return SUPPORTED_SYMBOLS


def _pct_change_vs(store, chain: str, metric: str, current: float, days: int):
    """
    Variación porcentual frente al valor de hace `days` días.

    Se toma el punto más ANTIGUO dentro de la ventana, no la media: la pregunta
    es «cuánto ha cambiado desde entonces», y una media respondería a otra
    distinta. Devuelve None si no hay dato con suficiente antigüedad —al menos
    la mitad de la ventana—, porque comparar contra hace dos horas y llamarlo
    «7 días» sería mentir sobre lo que se mide.
    """
    series = store.load_series(chain, metric, days=days)
    if len(series) < 2:
        return None
    oldest_ts, oldest = series[0]
    newest_ts = series[-1][0]
    if (newest_ts - oldest_ts) < days * 86_400_000 * 0.5:
        return None
    if not oldest:
        return None
    return round((current - oldest) / abs(oldest) * 100.0, 2)
