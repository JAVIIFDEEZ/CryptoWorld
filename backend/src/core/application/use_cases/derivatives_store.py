"""
derivatives_store.py — Archivar la microestructura que solo existía como «ahora».

Qué se recoge y por qué exactamente esto
────────────────────────────────────────
Cuatro series, que son los ingredientes que faltaban para poder medir tensión de
mercado hacia atrás:

  · **open_interest_usd** — cuánto apalancamiento hay vivo.
  · **long_short_ratio** — cuántas CUENTAS están de cada lado; unilateralidad de
    la multitud.
  · **taker_buy_sell_ratio** — quién está cruzando el spread ahora; es flujo, no
    posicionamiento, y las dos cosas discrepan justo en los momentos
    interesantes.
  · **depth_2pct_usd** — cuánto dinero aguanta el libro a ±2 % antes de romperse.

Las tres primeras tienen 30 días de histórico accesible, así que una serie
arranca con un mes de pasado el primer día. La cuarta no tiene histórico de
ninguna forma: si no se archiva, no existe. Esa asimetría es el motivo de que
este módulo exista.

La disciplina que hace utilizable lo archivado
──────────────────────────────────────────────
Cada punto guarda CUÁNDO el valor era cierto (`observed_at`) y cuándo se escribió
(`created_at`). No es redundancia: es lo único que permite comprobar después que
un estudio no usó información que en su momento no existía. Sin esa pareja hay
que creerse el pipeline, y «créetelo» no es una propiedad auditable.

La escritura es idempotente por (activo, venue, métrica, instante), así que
reejecutar la ingesta sobre un tramo ya traído no duplica. Eso es lo que permite
rellenar huecos sin miedo, que a su vez es lo que hace que los huecos se
rellenen.

Lo que NO hace este módulo
──────────────────────────
No calcula nada. Alinear estas series a una rejilla de velas, con join as-of y
límite de caducidad, ya vive en `exogenous_features`, y ahí es donde tiene que
seguir viviendo: la fuga se comete alineando series, no leyéndolas, y esa parte
tiene que poder auditarse sola.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Nombres de métrica. Se fijan como constantes porque son la clave con la que se
# leerán dentro de meses: una errata aquí crea una serie paralela silenciosa que
# nadie encuentra hasta que alguien pregunta por qué faltan datos.
OPEN_INTEREST_USD = "open_interest_usd"
LONG_SHORT_RATIO = "long_short_ratio"
TAKER_BUY_SELL_RATIO = "taker_buy_sell_ratio"
DEPTH_2PCT_USD = "depth_2pct_usd"

HISTORICAL_METRICS = (OPEN_INTEREST_USD, LONG_SHORT_RATIO, TAKER_BUY_SELL_RATIO)
SNAPSHOT_METRICS = (DEPTH_2PCT_USD,)
ALL_METRICS = HISTORICAL_METRICS + SNAPSHOT_METRICS

# Profundidad del libro que se mide, como fracción del precio medio. ±2 % es el
# tramo donde una orden de tamaño prosumer se ejecuta de verdad; medir a ±0,1 %
# describiría el spread y a ±10 %, un libro que en un susto no está.
DEPTH_BAND = 0.02


def _pair(symbol: str) -> str:
    s = symbol.upper()
    return s if s.endswith("USDT") else f"{s}USDT"


def depth_within_band(book: dict, band: float = DEPTH_BAND) -> float | None:
    """
    Dinero disponible a ±`band` del precio medio, en USD, sumando ambos lados.

    Es una medida de resiliencia, no de precio: cuánto se puede ejecutar antes de
    que el libro se quede sin contrapartida. Se suman las dos caras porque la
    pregunta que responde —«¿cuánto aguanta esto antes de romperse?»— no depende
    de la dirección.

    Devuelve None si el libro llega vacío o malformado, en vez de cero: un cero
    significaría «no hay liquidez», que es una afirmación muy distinta de «no he
    podido mirar».
    """
    try:
        bids = [(float(p), float(q)) for p, q in (book.get("bids") or [])]
        asks = [(float(p), float(q)) for p, q in (book.get("asks") or [])]
    except (TypeError, ValueError):
        return None
    if not bids or not asks:
        return None

    medio = (bids[0][0] + asks[0][0]) / 2.0
    if medio <= 0:
        return None

    suelo, techo = medio * (1 - band), medio * (1 + band)
    total = sum(p * q for p, q in bids if p >= suelo)
    total += sum(p * q for p, q in asks if p <= techo)
    return float(total)


class IngestDerivativesUseCase:
    """Trae y archiva las series de microestructura de un activo."""

    def execute(self, asset_symbol: str, venue: str = "binance",
                period: str = "1h", limit: int = 500,
                client=None) -> dict:
        from core.infrastructure.external_apis.binance_client import BinancePublicClient

        symbol = asset_symbol.upper()
        par = _pair(symbol)
        cliente = client or BinancePublicClient()

        puntos: list[tuple[str, int, float]] = []
        errores: dict[str, str] = {}

        for metrica, traer in (
            (OPEN_INTEREST_USD, lambda: cliente.open_interest_history(par, period, limit)),
            (LONG_SHORT_RATIO, lambda: cliente.long_short_ratio_history(par, period, limit)),
            (TAKER_BUY_SELL_RATIO, lambda: cliente.taker_buy_sell_history(par, period, limit)),
        ):
            try:
                puntos.extend(self._parse(metrica, traer() or []))
            except Exception as exc:  # noqa: BLE001 — una fuente caída no frena las demás
                logger.info("derivatives_store: %s no disponible para %s (%s)",
                            metrica, symbol, type(exc).__name__)
                errores[metrica] = type(exc).__name__

        # La profundidad es una foto: un único punto, con el instante de ahora.
        try:
            from datetime import datetime, timezone as _tz

            libro = cliente.order_book_depth(par)
            profundidad = depth_within_band(libro)
            if profundidad is not None:
                ahora = int(datetime.now(_tz.utc).timestamp() * 1000)
                puntos.append((DEPTH_2PCT_USD, ahora, profundidad))
        except Exception as exc:  # noqa: BLE001
            logger.info("derivatives_store: profundidad no disponible para %s (%s)",
                        symbol, type(exc).__name__)
            errores[DEPTH_2PCT_USD] = type(exc).__name__

        guardados = self._persist(symbol, venue, puntos)
        return {
            "symbol": symbol,
            "venue": venue,
            "points_fetched": len(puntos),
            "points_stored": guardados,
            "metrics": sorted({m for m, _, _ in puntos}),
            "errors": errores,
            "note": (
                f"{guardados} puntos nuevos de {len(puntos)} traídos. Los repetidos "
                "no se duplican: la escritura es idempotente por activo, venue, "
                "métrica e instante."
            ),
        }

    # ------------------------------------------------------------------

    @staticmethod
    def _parse(metric: str, filas) -> list[tuple[str, int, float]]:
        """
        Traduce la respuesta de Binance a (métrica, instante, valor).

        Los tres endpoints devuelven el instante en `timestamp` y el valor en un
        campo distinto cada uno. Se toma el nocional en USD del interés abierto
        —no el número de contratos— porque los contratos no son comparables entre
        activos ni a lo largo del tiempo si el contrato se redefine.
        """
        campo = {
            OPEN_INTEREST_USD: "sumOpenInterestValue",
            LONG_SHORT_RATIO: "longShortRatio",
            TAKER_BUY_SELL_RATIO: "buySellRatio",
        }[metric]

        salida = []
        for fila in filas:
            try:
                instante = int(fila["timestamp"])
                valor = float(fila[campo])
            except (KeyError, TypeError, ValueError):
                continue
            if valor == valor:      # descarta NaN
                salida.append((metric, instante, valor))
        return salida

    @staticmethod
    def _persist(symbol: str, venue: str, puntos) -> int:
        """
        Escribe los puntos e informa de cuántos eran NUEVOS.

        Con `ignore_conflicts=True`, PostgreSQL no devuelve las claves primarias
        de las filas insertadas —es comportamiento documentado de Django, no una
        rareza—, así que mirar los objetos devueltos daría siempre cero. Se
        cuenta antes y después, que es la única forma fiable y además la que
        distingue «no se escribió nada porque ya estaba» de «no se escribió nada
        porque falló».
        """
        if not puntos:
            return 0
        from core.infrastructure.persistence.models import DerivativeMetricPoint

        base = DerivativeMetricPoint.objects.filter(symbol=symbol, venue=venue)
        antes = base.count()
        DerivativeMetricPoint.objects.bulk_create(
            [DerivativeMetricPoint(symbol=symbol, venue=venue, metric=metrica,
                                   observed_at=instante, value=valor)
             for metrica, instante, valor in puntos],
            ignore_conflicts=True,
        )
        return max(base.count() - antes, 0)


def coverage(symbol: str, venue: str = "binance") -> dict:
    """
    Qué series hay archivadas de este activo y desde cuándo.

    Es el paso previo obligatorio de cualquier estudio que las use: sin él, una
    métrica que sale sin importancia no se distingue de una que no se ha
    recogido, y las dos conclusiones son opuestas.
    """
    from core.infrastructure.persistence.models import DerivativeMetricPoint

    salida = {}
    for metrica in ALL_METRICS:
        qs = DerivativeMetricPoint.objects.filter(
            symbol=symbol.upper(), venue=venue, metric=metrica)
        n = qs.count()
        if n == 0:
            salida[metrica] = {"available": False, "points": 0,
                               "note": "No se ha recogido todavía."}
            continue
        primero = qs.order_by("observed_at").first()
        ultimo = qs.order_by("-observed_at").first()
        salida[metrica] = {
            "available": True,
            "points": n,
            "first_ms": primero.observed_at,
            "last_ms": ultimo.observed_at,
            "span_days": round((ultimo.observed_at - primero.observed_at) / 86_400_000, 2),
        }
    return {"symbol": symbol.upper(), "venue": venue, "metrics": salida}
