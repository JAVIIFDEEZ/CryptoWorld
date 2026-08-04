"""
chain_metrics_store.py — Almacén histórico del módulo de blockchain.

El módulo on-chain no guardaba nada. Cada panel consultaba en vivo y mostraba
una foto, con tres consecuencias que el usuario sufre directamente: si la fuente
falla el panel queda vacío, no hay tendencias, y no hay gráficas porque un punto
no se dibuja.

Este módulo es al módulo de blockchain lo que `ohlcv_store` es al de mercado, y
por la misma razón: un actor serio acumula un histórico propio en vez de
depender de que una API pública responda en el instante exacto en que alguien
mira la pantalla.

Tres capacidades que solo existen con historia
──────────────────────────────────────────────
· **Repliegue honesto.** Si la fuente falla, se sirve el último dato guardado
  DICIENDO QUE ES VIEJO. Mostrar un dato de hace tres horas como si fuera de
  ahora sería peor que no mostrar nada; mostrarlo con su edad es mejor que un
  panel en blanco.
· **Percentiles propios.** «El gas está a 12 Gwei» no significa nada suelto. «El
  gas está más barato que el 82 % de los últimos 30 días» sí, y además se
  autocalibra: los umbrales fijos por red son constantes arbitrarias que
  envejecen con el mercado.
· **Series.** Tendencias, gráficas y comparativas entre cadenas.

Capa de aplicación: usa el ORM, sin dependencias externas.
"""

import logging
import time

logger = logging.getLogger(__name__)

# Resolución del almacén. Sin cubos, cada visita de cada usuario crearía una
# fila y el histórico crecería con el TRÁFICO en vez de con el tiempo.
BUCKET_MS = 300_000          # 5 minutos
_DAY_MS = 86_400_000

# Métricas que se guardan de una lectura de salud de red. Lista explícita a
# propósito: persistir todo lo que devuelva la API metería identificadores y
# textos en una tabla de series numéricas.
HEALTH_METRICS = (
    "gas_slow", "gas_average", "gas_fast",
    "network_utilization_pct", "block_time_sec",
    "transactions_today", "coin_price_usd",
)


def _now_ms() -> int:
    return int(time.time() * 1000)


def bucket_of(ts_ms: int | None = None) -> int:
    """Instante redondeado al cubo que lo contiene."""
    return ((ts_ms if ts_ms is not None else _now_ms()) // BUCKET_MS) * BUCKET_MS


def persist_metrics(chain: str, metrics: dict, source: str = "blockscout",
                    ts_ms: int | None = None) -> int:
    """
    Guarda las métricas numéricas de una lectura (idempotente por cubo).

    Los valores no numéricos y los no finitos se descartan en silencio: una
    tabla de series temporales con `None` o `NaN` dentro contamina cualquier
    percentil que se calcule después, y esos huecos son difíciles de rastrear.
    """
    from core.infrastructure.persistence.models import ChainMetricPoint

    chain = (chain or "").strip().lower()
    if not chain or not metrics:
        return 0

    bucket = bucket_of(ts_ms)
    rows = []
    for name, raw in metrics.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        value = float(raw)
        if value != value or value in (float("inf"), float("-inf")):
            continue
        rows.append(ChainMetricPoint(chain=chain, metric=str(name), timestamp=bucket,
                                     value=value, source=source))
    if not rows:
        return 0

    before = ChainMetricPoint.objects.filter(chain=chain, timestamp=bucket).count()
    ChainMetricPoint.objects.bulk_create(rows, ignore_conflicts=True)
    return ChainMetricPoint.objects.filter(chain=chain, timestamp=bucket).count() - before


def load_series(chain: str, metric: str, days: int = 30,
                limit: int = 2000) -> list[tuple[int, float]]:
    """Serie ascendente (instante, valor) de los últimos `days` días."""
    from core.infrastructure.persistence.models import ChainMetricPoint

    since = _now_ms() - int(days) * _DAY_MS
    qs = (ChainMetricPoint.objects
          .filter(chain=(chain or "").strip().lower(), metric=metric,
                  timestamp__gte=since)
          .order_by("-timestamp")
          .values_list("timestamp", "value")[:limit])
    return [(int(t), float(v)) for t, v in reversed(list(qs))]


def latest(chain: str, metrics=None) -> dict:
    """
    Última lectura guardada de cada métrica, con su antigüedad.

    `age_seconds` es lo que convierte esto en un repliegue honesto en vez de un
    engaño: quien lo consuma debe poder decir «hace 3 horas» en lugar de
    presentar el dato como actual.
    """
    from core.infrastructure.persistence.models import ChainMetricPoint

    chain = (chain or "").strip().lower()
    qs = ChainMetricPoint.objects.filter(chain=chain)
    if metrics:
        qs = qs.filter(metric__in=list(metrics))

    out: dict[str, float] = {}
    newest = 0
    # Orden descendente + primer valor por métrica: el más reciente de cada una.
    for metric, ts, value in qs.order_by("-timestamp").values_list("metric", "timestamp", "value"):
        if metric not in out:
            out[metric] = float(value)
            newest = max(newest, int(ts))
    if not out:
        return {"metrics": {}, "timestamp": None, "age_seconds": None}
    return {
        "metrics": out,
        "timestamp": newest,
        "age_seconds": max(0, (_now_ms() - newest) // 1000),
    }


def percentile_of(chain: str, metric: str, value: float, days: int = 30,
                  min_points: int = 48) -> dict | None:
    """
    Dónde cae `value` dentro de su propia historia reciente.

    Es la versión autocalibrada de «¿está caro el gas?». Un umbral fijo de 10
    Gwei es una constante arbitraria que envejece con el mercado; el percentil
    se ajusta solo a cada red y a cada época.

    Devuelve `None` por debajo de `min_points` (4 horas de historia a un punto
    cada 5 minutos). Un percentil sobre seis lecturas es un número con apariencia
    de rigor y nada detrás, y eso es peor que no darlo.
    """
    series = load_series(chain, metric, days=days)
    if len(series) < min_points:
        return None

    values = sorted(v for _, v in series)
    below = sum(1 for v in values if v < value)
    equal = sum(1 for v in values if v == value)
    # Percentil medio en los empates: con muchos valores repetidos —gas plano en
    # una L2, por ejemplo— contar solo los estrictamente menores daría 0 y
    # contarlos todos daría 100 para el mismo dato.
    pct = (below + equal / 2.0) / len(values) * 100.0
    return {
        "percentile": round(pct, 1),
        "n_points": len(values),
        "days": days,
        "min": round(values[0], 6),
        "median": round(values[len(values) // 2], 6),
        "max": round(values[-1], 6),
    }


def coverage(chain: str) -> dict:
    """Cuánta historia hay para una cadena (observabilidad del almacén)."""
    from django.db.models import Count, Max, Min
    from core.infrastructure.persistence.models import ChainMetricPoint

    chain = (chain or "").strip().lower()
    agg = (ChainMetricPoint.objects.filter(chain=chain)
           .aggregate(n=Count("id"), first=Min("timestamp"), last=Max("timestamp")))
    if not agg["n"]:
        return {"chain": chain, "points": 0, "metrics": 0, "first": None, "last": None,
                "span_days": 0.0,
                "note": "Sin histórico: los paneles de esta cadena dependen por "
                        "completo de que la fuente externa responda ahora mismo."}

    metrics = (ChainMetricPoint.objects.filter(chain=chain)
               .values_list("metric", flat=True).distinct().count())
    span = (agg["last"] - agg["first"]) / _DAY_MS
    return {
        "chain": chain,
        "points": agg["n"],
        "metrics": metrics,
        "first": int(agg["first"]),
        "last": int(agg["last"]),
        "span_days": round(span, 2),
        "note": (f"{agg['n']} puntos de {metrics} métricas cubriendo {span:.1f} días. "
                 "Con historia, los paneles sobreviven a una caída de la fuente y "
                 "los umbrales dejan de ser constantes arbitrarias."),
    }


def prune(older_than_days: int = 400) -> int:
    """
    Poda del histórico. Un almacén que solo crece acaba siendo un problema
    operativo, y más de un año de gas a 5 minutos no aporta nada que no diga el
    último mes.
    """
    from core.infrastructure.persistence.models import ChainMetricPoint

    cutoff = _now_ms() - int(older_than_days) * _DAY_MS
    deleted, _ = ChainMetricPoint.objects.filter(timestamp__lt=cutoff).delete()
    return deleted
