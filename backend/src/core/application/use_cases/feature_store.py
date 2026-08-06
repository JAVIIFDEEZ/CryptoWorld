"""
feature_store.py — Carga de variables exógenas desde el almacén propio.

Este módulo hace UNA cosa: sacar de la base de datos las series que la
plataforma lleva meses recogiendo y entregárselas al dominio
(`exogenous_features`) para que las alinee a la rejilla de velas. Toda la lógica
temporal —el join as-of, la caducidad, los z-scores rezagados— vive allí, en
Python puro y testeable sin base de datos. Aquí solo hay consultas.

La separación no es ceremonia. La fuga que este trabajo intenta cerrar se comete
alineando series, no leyéndolas, y esa parte tiene que poder auditarse sola.

Por qué la lista de fuentes es más corta de lo que parece
────────────────────────────────────────────────────────
La auditoría enumera funding, open interest, ratio long/short, taker buy/sell,
flujos on-chain, smart money, profundidad de order book y régimen, y da por
hecho que la plataforma «ya los posee». Los sabe LEER —hay clientes y endpoints
que los consultan— pero solo archiva la serie de algunos:

  · **Funding** (`FundingRateRecord`) — histórico completo por símbolo. ✅
  · **Movimientos de ballenas** (`WhaleMovementSnapshot`) — con `moved_at` y
    dirección ya clasificada. ✅
  · **Métricas de cadena** (`ChainMetricPoint`) — series por cadena y métrica. ✅
  · Open interest, long/short, taker buy/sell, profundidad — **se consultan en
    vivo y no se guardan**. ❌

Para las últimas no hay feature posible hoy, y las dos salidas fáciles son
inaceptables: propagar hacia atrás el valor de hoy es lookahead del peor tipo, y
crear la columna vacía en silencio haría que el estudio concluyera «no aporta»
cuando lo cierto es «no se ha medido». Se declaran como ausentes con su motivo.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from core.domain.services import exogenous_features as ex

logger = logging.getLogger(__name__)

# Cadena sobre la que vive cada activo, para las métricas de red. Solo los que
# tienen cadena propia: un token ERC-20 hereda la salud de Ethereum, pero eso es
# una decisión de modelado que no toca hacer aquí sin evidencia.
# La clave del almacén lleva el prefijo `bc:` cuando la fuente es Blockchair y
# el símbolo va en minúsculas (ver `GetMultichainStats._chain_key`): `ethereum`
# (gas, vía Blockscout) y `bc:eth` (mempool, vía Blockchair) son series
# distintas de la misma red y no deben mezclarse.
_ASSET_CHAIN: dict[str, str] = {
    "BTC": "bc:btc",
    "ETH": "ethereum",
    "LTC": "bc:ltc",
    "DOGE": "bc:doge",
    "BNB": "bsc",
    "MATIC": "polygon",
    "POL": "polygon",
    "AVAX": "avalanche",
}

# Métrica de cadena que se usa como termómetro. Se elige UNA por cadena y se
# dice cuál, en vez de meterlas todas: cada métrica añadida es una prueba más en
# el estudio de importancia, y multiplicar pruebas sin hipótesis previa es
# exactamente lo que el control de multiplicidad existe para castigar.
#
# La elegida mide CONGESTIÓN, no estructura. La dificultad de Bitcoin sería el
# candidato obvio y es inútil aquí: se reajusta cada 2016 bloques —unas dos
# semanas— así que a un horizonte de cinco velas es prácticamente una constante.
# El mempool sí varía en la escala relevante y tiene una historia económica
# detrás: congestión es urgencia, y la urgencia precede al flujo.
_CHAIN_METRIC: dict[str, str] = {
    "bc:btc": "mempool_transactions",
    "bc:ltc": "mempool_transactions",
    "bc:doge": "mempool_transactions",
    "ethereum": "network_utilization_pct",
    "bsc": "network_utilization_pct",
    "polygon": "network_utilization_pct",
    "avalanche": "network_utilization_pct",
}

# Signo del flujo por dirección clasificada. Positivo = sale de exchange, que se
# lee como acumulación; negativo = entra, que se lee como intención de venta.
# `between_exchanges` y `unknown` valen cero: no aportan dirección y contarlos
# como cualquiera de los dos lados sería inventar una señal.
_FLOW_SIGN: dict[str, float] = {
    "from_exchange": 1.0,
    "to_exchange": -1.0,
    "between_exchanges": 0.0,
    "unknown": 0.0,
}


def _load_funding(symbol: str, start_ms: int, end_ms: int) -> list[tuple[int, float]]:
    from core.application.use_cases.funding_store import load_funding
    try:
        return load_funding(symbol, start_ms=start_ms, end_ms=end_ms)
    except Exception:  # noqa: BLE001 — una fuente caída deja su bloque vacío, no rompe
        logger.info("feature_store: funding no disponible para %s", symbol)
        return []


def _load_whale_flow(symbol: str, start_ms: int, end_ms: int) -> list[tuple[int, float]]:
    """Movimientos con su signo ya resuelto, en epoch ms."""
    from core.infrastructure.persistence.models import WhaleMovementSnapshot
    try:
        rows = (WhaleMovementSnapshot.objects
                .filter(symbol=symbol.upper(),
                        moved_at__gte=pd.Timestamp(start_ms, unit="ms", tz="UTC"),
                        moved_at__lte=pd.Timestamp(end_ms, unit="ms", tz="UTC"))
                .order_by("moved_at")
                .values_list("moved_at", "value_usd", "direction"))
    except Exception:  # noqa: BLE001
        logger.info("feature_store: movimientos no disponibles para %s", symbol)
        return []

    out = []
    for moved_at, value_usd, direction in rows:
        sign = _FLOW_SIGN.get(direction, 0.0)
        if sign == 0.0:
            continue
        out.append((int(moved_at.timestamp() * 1000), sign * float(value_usd)))
    return out


def _load_chain_metric(symbol: str, start_ms: int, end_ms: int) -> list[tuple[int, float]]:
    chain = _ASSET_CHAIN.get(symbol.upper())
    metric = _CHAIN_METRIC.get(chain or "")
    if not chain or not metric:
        return []

    from core.infrastructure.persistence.models import ChainMetricPoint
    try:
        rows = (ChainMetricPoint.objects
                .filter(chain=chain, metric=metric,
                        timestamp__gte=int(start_ms), timestamp__lte=int(end_ms))
                .order_by("timestamp")
                .values_list("timestamp", "value"))
    except Exception:  # noqa: BLE001
        logger.info("feature_store: métricas de cadena no disponibles para %s", symbol)
        return []
    return [(int(t), float(v)) for t, v in rows]


def build_exogenous_features(symbol: str, timestamps) -> pd.DataFrame:
    """
    Variables exógenas alineadas a `timestamps` (epoch ms de apertura de vela).

    El resultado tiene SIEMPRE las mismas columnas, tenga o no datos el activo:
    los bloques sin fuente salen a NaN con su bandera de disponibilidad a cero.
    Que el número de columnas dependiera del activo haría que dos estudios no
    fueran comparables entre sí.

    Solo se consultan registros dentro del rango de las velas. Un margen previo
    haría falta para calentar las ventanas, pero pedirlo aquí obligaría a
    decidir cuánto —y esa decisión pertenece a quien construye el estudio, que
    es quien sabe qué ventanas va a usar.
    """
    ts = np.asarray(timestamps, dtype=np.int64)
    if ts.size == 0:
        return ex.assemble(ts)

    start_ms, end_ms = int(ts.min()), int(ts.max())
    return ex.assemble(
        ts,
        funding=_load_funding(symbol, start_ms, end_ms),
        whale=_load_whale_flow(symbol, start_ms, end_ms),
        chain=_load_chain_metric(symbol, start_ms, end_ms),
    )


def exogenous_coverage(symbol: str, timestamps) -> dict:
    """
    Qué bloques exógenos tiene realmente este activo, y cuáles no existen.

    Es el paso previo obligatorio de cualquier estudio de importancia: sin él,
    un bloque que sale sin importancia no se puede distinguir de un bloque que
    no se ha medido, y las dos conclusiones son opuestas.
    """
    frame = build_exogenous_features(symbol, timestamps)
    report = ex.coverage(frame)
    report["symbol"] = symbol.upper()
    report["chain"] = _ASSET_CHAIN.get(symbol.upper())
    report["chain_metric"] = _CHAIN_METRIC.get(report["chain"] or "")
    return report
