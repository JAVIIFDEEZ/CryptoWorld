"""
funding_store.py — Almacén histórico de financiación de perpetuos.

Es la pieza que faltaba para que el coste de mantener un perpetuo abierto deje
de ser una omisión del backtest. El dominio ya sabía cobrarlo (`funding.py`) y
el motor ya sabía aplicarlo; sin este módulo no había de dónde sacar el dato, y
la lógica era código muerto.

Tres responsabilidades, en paralelo a `ohlcv_store`:
  · persist_funding / BackfillFundingUseCase: traer el histórico paginando hacia
    atrás e insertarlo de forma idempotente (unicidad symbol+funding_time).
  · attach_funding: adjuntar a un DataFrame OHLCV la columna `funding_rate` con
    las liquidaciones imputadas a cada vela. El resto del sistema no necesita
    enterarse: `backtest_signals` cobra la columna si está.
  · coverage: qué tramo del histórico está cubierto y con qué régimen, para que
    nadie confunda «no cobró funding» con «no había dato».

Sobre por qué el coste viaja como COLUMNA y no como parámetro: así acompaña
siempre a los datos a los que pertenece. Un tramo de histórico no puede
backtestearse por accidente sin su funding, que es exactamente el fallo que se
quiere hacer imposible.
"""

import logging
import time
from datetime import datetime, timezone as _tz

import pandas as pd

UTC = _tz.utc

from core.domain.services import funding as funding_service

logger = logging.getLogger(__name__)

_INTERVAL_MS: dict[str, int] = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000,
    "12h": 43_200_000, "1d": 86_400_000, "1w": 604_800_000,
}


def _pair(symbol: str) -> str:
    """Símbolo del perpetuo USDⓈ-M correspondiente al activo."""
    s = symbol.upper()
    return s if s.endswith("USDT") else f"{s}USDT"


def persist_funding(symbol: str, rows, source: str = "binance") -> int:
    """
    Persiste liquidaciones de funding (idempotente). `rows` son dicts al estilo
    de Binance: fundingTime, fundingRate, markPrice.
    """
    from core.infrastructure.persistence.models import FundingRateRecord

    pair = _pair(symbol)
    records = []
    for r in rows or []:
        try:
            records.append(FundingRateRecord(
                symbol=pair,
                funding_time=int(r["fundingTime"]),
                funding_rate=float(r["fundingRate"]),
                mark_price=float(r["markPrice"]) if r.get("markPrice") else None,
                source=source,
            ))
        except (KeyError, TypeError, ValueError):
            # Una fila malformada no debe tumbar la ingesta de las buenas, pero
            # tampoco colarse como un funding de cero: se descarta y se cuenta.
            logger.warning("funding: fila descartada para %s: %r", pair, r)

    if not records:
        return 0
    before = FundingRateRecord.objects.filter(symbol=pair).count()
    FundingRateRecord.objects.bulk_create(records, ignore_conflicts=True)
    return FundingRateRecord.objects.filter(symbol=pair).count() - before


def load_funding(symbol: str, start_ms: int | None = None,
                 end_ms: int | None = None) -> list[tuple[int, float]]:
    """Pares (funding_time, rate) ascendentes del tramo pedido."""
    from core.infrastructure.persistence.models import FundingRateRecord

    qs = FundingRateRecord.objects.filter(symbol=_pair(symbol))
    if start_ms is not None:
        qs = qs.filter(funding_time__gte=int(start_ms))
    if end_ms is not None:
        qs = qs.filter(funding_time__lte=int(end_ms))
    return [(int(t), float(r)) for t, r in
            qs.order_by("funding_time").values_list("funding_time", "funding_rate")]


def attach_funding(df: pd.DataFrame, symbol: str, interval: str) -> pd.DataFrame:
    """
    Devuelve el DataFrame con la columna `funding_rate` por vela.

    Si no hay histórico para el tramo, se devuelve el DataFrame **sin la
    columna** en lugar de con ceros. La diferencia importa: una columna de ceros
    afirma que el funding fue nulo, y lo que en realidad ocurre es que no se
    sabe. Un backtest debe poder distinguir esas dos cosas.
    """
    step = _INTERVAL_MS.get(interval)
    if df is None or df.empty or step is None or "timestamp" not in df.columns:
        return df

    times = df["timestamp"].astype("int64").tolist()
    records = load_funding(symbol, start_ms=times[0], end_ms=times[-1] + step)
    if not records:
        return df

    out = df.copy()
    out["funding_rate"] = funding_service.funding_per_bar(records, times, step)
    return out


def coverage(symbol: str) -> dict:
    """Estado y régimen del histórico de financiación de un perpetuo."""
    from core.infrastructure.persistence.models import FundingRateRecord

    pair = _pair(symbol)
    qs = FundingRateRecord.objects.filter(symbol=pair)
    count = qs.count()
    if count == 0:
        return {"symbol": pair, "settlements": 0, "first": None, "last": None,
                "note": "Sin histórico de financiación: los backtests de este "
                        "perpetuo NO incluyen su coste de mantenimiento."}

    rates = list(qs.order_by("funding_time").values_list("funding_rate", flat=True))
    first = qs.order_by("funding_time").values_list("funding_time", flat=True).first()
    last = qs.order_by("-funding_time").values_list("funding_time", flat=True).first()
    return {
        "symbol": pair,
        "settlements": count,
        "first": int(first),
        "last": int(last),
        **funding_service.describe(rates),
    }


class BackfillFundingUseCase:
    """
    Retro-carga del histórico de funding paginando hacia atrás contra Binance.

    Idempotente y reanudable, igual que el backfill de velas: cada página trae
    hasta 1000 liquidaciones anteriores a la más antigua almacenada, y se puede
    invocar tantas veces como haga falta.
    """

    def __init__(self, binance_client=None) -> None:
        from core.infrastructure.external_apis.binance_client import BinancePublicClient
        self._binance = binance_client or BinancePublicClient()

    def execute(self, symbol: str, target_settlements: int = 3000,
                max_pages: int = 10, page_pause_s: float = 0.15) -> dict:
        from core.infrastructure.external_apis.binance_client import BinanceClientError
        from core.infrastructure.persistence.models import FundingRateRecord

        pair = _pair(symbol)
        created_total = pages = 0
        exhausted = False

        for _ in range(max_pages):
            qs = FundingRateRecord.objects.filter(symbol=pair)
            if qs.count() >= target_settlements:
                break
            oldest = qs.order_by("funding_time").values_list("funding_time", flat=True).first()
            end_ms = (oldest - 1) if oldest else None
            try:
                raw = self._binance.funding_rate_history(pair, end_time=end_ms, limit=1000)
            except BinanceClientError as exc:
                logger.warning("backfill funding %s: %s", pair, exc)
                return {"symbol": pair, "pages": pages, "created": created_total,
                        "exhausted": False, "error": f"Binance no disponible: {exc}"}
            pages += 1
            if not raw:
                exhausted = True
                break
            created = persist_funding(symbol, raw)
            created_total += created
            if created == 0 and oldest is not None:
                exhausted = True      # la página no aportó nada: fin real
                break
            if page_pause_s:
                time.sleep(page_pause_s)

        return {
            "symbol": pair, "pages": pages, "created": created_total,
            "settlements": FundingRateRecord.objects.filter(symbol=pair).count(),
            "target": target_settlements, "exhausted": exhausted,
        }


class SyncAssetLifecycleUseCase:
    """
    Sincroniza fechas de alta y baja del universo contra el catálogo del exchange.

    Es la ingesta que hace posible un universo point-in-time. Sin ella,
    `listed_at` y `delisted_at` quedan nulos y `universe.coverage` lo declara
    explícitamente NO fiable — que es preferible a un rigor aparente.

    Una baja se registra por AUSENCIA: si un símbolo que el almacén conoce ya no
    figura como operable en el catálogo, dejó de cotizar. La fecha exacta no la
    da el exchange, así que se marca el momento en que se detecta y se anota el
    motivo como `delisted`. Es una aproximación, y se documenta como tal: llega
    tarde, nunca pronto, de modo que el sesgo residual va en contra de la
    estrategia y no a su favor.
    """

    def __init__(self, binance_client=None) -> None:
        from core.infrastructure.external_apis.binance_client import BinancePublicClient
        self._binance = binance_client or BinancePublicClient()

    def execute(self, mark_missing_as_delisted: bool = True) -> dict:
        from django.utils import timezone
        from core.infrastructure.external_apis.binance_client import BinanceClientError
        from core.infrastructure.persistence.models import CryptoAsset

        try:
            info = self._binance.futures_exchange_info()
        except BinanceClientError as exc:
            return {"error": f"Binance no disponible: {exc}", "updated": 0}

        listed: dict[str, int] = {}
        tradable: set[str] = set()
        for entry in info.get("symbols", []):
            base = str(entry.get("baseAsset", "")).upper()
            if not base:
                continue
            onboard = entry.get("onboardDate")
            if onboard:
                listed[base] = int(onboard)
            if entry.get("status") == "TRADING":
                tradable.add(base)

        now = timezone.now()
        updated = delisted = 0
        for asset in CryptoAsset.objects.all():
            fields: list[str] = []
            base = asset.symbol.upper()

            onboard = listed.get(base)
            if onboard and asset.listed_at is None:
                asset.listed_at = datetime.fromtimestamp(onboard / 1000.0, tz=UTC)
                fields.append("listed_at")

            # Solo se marca baja a lo que el catálogo llegó a conocer: un activo
            # que nunca tuvo perpetuo no está delistado, simplemente no cotiza
            # en ese mercado.
            known = base in listed or base in tradable
            if (mark_missing_as_delisted and known and base not in tradable
                    and asset.delisted_at is None):
                asset.delisted_at = now
                asset.delisting_reason = "delisted"
                fields += ["delisted_at", "delisting_reason"]
                delisted += 1

            if fields:
                asset.save(update_fields=fields + ["updated_at"])
                updated += 1

        return {
            "catalogue_symbols": len(listed),
            "tradable": len(tradable),
            "updated": updated,
            "newly_delisted": delisted,
            "note": (
                f"{updated} activos actualizados; {delisted} marcados como "
                "retirados. La fecha de baja es la de DETECCIÓN, no la real: "
                "llega tarde, nunca pronto, así que el sesgo residual va en "
                "contra de la estrategia y no a su favor."
            ),
        }
