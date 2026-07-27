"""
ohlcv_store.py — Almacén histórico propio de velas OHLCV (nivel institucional).

Tres responsabilidades:
  · persist_candles / load_dataframe: guardar velas CERRADAS (la vela en curso
    muta hasta cerrar, no se persiste) y servirlas como DataFrame idéntico al
    del fetcher — el resto del sistema no distingue la procedencia.
  · coverage / find_gaps: auditoría honesta del histórico (primera/última vela,
    huecos respecto a la secuencia aritmética esperada).
  · BackfillOhlcvUseCase: paginación hacia atrás contra Binance (endTime) para
    construir años de histórico en tandas idempotentes (la unicidad
    symbol+interval+open_time hace inocua cualquier re-ingesta).

Por qué importa: los backtests y el generador dejan de estar limitados a las
~1000 velas de una llamada — pueden cubrir ciclos completos de mercado — y
cada validación es reproducible sobre datos inmutables propios.
"""

import logging
import time

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_INTERVAL_MS: dict[str, int] = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "12h": 43_200_000, "1d": 86_400_000, "1w": 604_800_000,
}

_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def _now_ms() -> int:
    return int(time.time() * 1000)


def persist_candles(symbol: str, interval: str, df: pd.DataFrame, source: str) -> int:
    """Persiste las velas CERRADAS del DataFrame (idempotente). Devuelve cuántas
    filas nuevas se han creado."""
    from core.infrastructure.persistence.models import OhlcvCandle

    step = _INTERVAL_MS.get(interval)
    if df is None or df.empty or step is None:
        return 0
    cutoff = _now_ms() - step   # una vela está cerrada si abrió hace ≥ 1 intervalo
    rows = [
        OhlcvCandle(
            symbol=symbol.upper(), interval=interval, open_time=int(r.timestamp),
            open=float(r.open), high=float(r.high), low=float(r.low),
            close=float(r.close), volume=float(r.volume), source=source,
        )
        for r in df.itertuples(index=False)
        if int(r.timestamp) <= cutoff
    ]
    if not rows:
        return 0
    before = OhlcvCandle.objects.filter(symbol=symbol.upper(), interval=interval).count()
    OhlcvCandle.objects.bulk_create(rows, ignore_conflicts=True)
    return OhlcvCandle.objects.filter(symbol=symbol.upper(), interval=interval).count() - before


def load_dataframe(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    """Últimas `limit` velas del almacén, ascendentes, con el MISMO esquema que
    el fetcher remoto ([timestamp, open, high, low, close, volume])."""
    from core.infrastructure.persistence.models import OhlcvCandle

    qs = (OhlcvCandle.objects
          .filter(symbol=symbol.upper(), interval=interval)
          .order_by("-open_time")
          .values_list("open_time", "open", "high", "low", "close", "volume")[:limit])
    rows = list(qs)[::-1]
    if not rows:
        return pd.DataFrame(columns=_COLUMNS)
    return pd.DataFrame(rows, columns=_COLUMNS)


def store_is_fresh(symbol: str, interval: str, limit: int) -> bool:
    """True si el almacén puede servir `limit` velas y contiene TODAS las
    cerradas (la última vela cerrada abre siempre ≥ ahora − 2·intervalo)."""
    from core.infrastructure.persistence.models import OhlcvCandle

    step = _INTERVAL_MS.get(interval)
    if step is None:
        return False
    qs = OhlcvCandle.objects.filter(symbol=symbol.upper(), interval=interval)
    if qs.count() < limit:
        return False
    last = qs.order_by("-open_time").values_list("open_time", flat=True).first()
    return last is not None and last >= _now_ms() - 2 * step


def find_gaps(symbol: str, interval: str, max_report: int = 10) -> dict:
    """Huecos del histórico: posiciones donde falta al menos una vela respecto a
    la secuencia aritmética esperada entre la primera y la última almacenada."""
    from core.infrastructure.persistence.models import OhlcvCandle

    step = _INTERVAL_MS.get(interval)
    times = np.array(
        OhlcvCandle.objects.filter(symbol=symbol.upper(), interval=interval)
        .order_by("open_time").values_list("open_time", flat=True),
        dtype=np.int64,
    )
    if step is None or times.size < 2:
        return {"gaps": 0, "missing_candles": 0, "ranges": []}
    diffs = np.diff(times)
    gap_idx = np.where(diffs > step)[0]
    ranges = [
        {"after": int(times[i]), "before": int(times[i + 1]),
         "missing": int(diffs[i] // step) - 1}
        for i in gap_idx[:max_report]
    ]
    return {
        "gaps": int(gap_idx.size),
        "missing_candles": int(sum((diffs[gap_idx] // step) - 1)),
        "ranges": ranges,
    }


def coverage(symbol: str, interval: str) -> dict:
    """Estado de cobertura del histórico para un símbolo+marco."""
    from core.infrastructure.persistence.models import OhlcvCandle

    qs = OhlcvCandle.objects.filter(symbol=symbol.upper(), interval=interval)
    count = qs.count()
    if count == 0:
        return {"symbol": symbol.upper(), "interval": interval, "candles": 0,
                "first": None, "last": None, "gaps": 0, "missing_candles": 0}
    first = qs.order_by("open_time").values_list("open_time", flat=True).first()
    last = qs.order_by("-open_time").values_list("open_time", flat=True).first()
    gaps = find_gaps(symbol, interval)
    return {
        "symbol": symbol.upper(), "interval": interval, "candles": count,
        "first": int(first), "last": int(last),
        "gaps": gaps["gaps"], "missing_candles": gaps["missing_candles"],
        "gap_ranges": gaps["ranges"],
    }


class BackfillOhlcvUseCase:
    """Retro-carga del histórico paginando hacia atrás contra Binance.

    Cada página trae hasta 1000 velas anteriores a la más antigua almacenada.
    Idempotente y reanudable: se puede invocar tantas veces como haga falta
    hasta alcanzar el objetivo o agotar el histórico del exchange."""

    def __init__(self, binance_client=None) -> None:
        from core.infrastructure.external_apis.binance_client import BinancePublicClient
        self._binance = binance_client or BinancePublicClient()

    def execute(self, symbol: str, interval: str = "1d",
                target_candles: int = 3000, max_pages: int = 10,
                page_pause_s: float = 0.15) -> dict:
        from core.application.use_cases.ohlcv_fetcher import _binance_klines_to_df
        from core.infrastructure.persistence.models import OhlcvCandle
        from core.infrastructure.external_apis.binance_client import BinanceClientError

        symbol = symbol.upper()
        step = _INTERVAL_MS.get(interval)
        if step is None:
            return {"error": f"Intervalo '{interval}' no soportado."}

        pair = f"{symbol}USDT"
        created_total = pages = 0
        exhausted = False
        for _ in range(max_pages):
            qs = OhlcvCandle.objects.filter(symbol=symbol, interval=interval)
            count = qs.count()
            if count >= target_candles:
                break
            oldest = qs.order_by("open_time").values_list("open_time", flat=True).first()
            end_ms = (oldest - 1) if oldest else None   # página anterior a lo almacenado
            try:
                raw = self._binance.get_klines(symbol=pair, interval=interval,
                                               limit=1000, end_time_ms=end_ms)
            except BinanceClientError as exc:
                logger.warning("backfill %s %s: %s", symbol, interval, exc)
                return {"symbol": symbol, "interval": interval, "pages": pages,
                        "created": created_total, "exhausted": False,
                        "error": f"Binance no disponible: {exc}"}
            df = _binance_klines_to_df(raw)
            pages += 1
            if df.empty:
                exhausted = True      # no hay histórico anterior en el exchange
                break
            created = persist_candles(symbol, interval, df, source="binance")
            created_total += created
            if created == 0 and oldest is not None:
                exhausted = True      # la página no aportó nada nuevo: fin real
                break
            if page_pause_s:
                time.sleep(page_pause_s)

        return {
            "symbol": symbol, "interval": interval,
            "pages": pages, "created": created_total,
            "candles": OhlcvCandle.objects.filter(symbol=symbol, interval=interval).count(),
            "target": target_candles, "exhausted": exhausted,
        }
