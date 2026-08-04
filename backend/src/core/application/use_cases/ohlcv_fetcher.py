"""
ohlcv_fetcher.py — Servicio compartido para obtener DataFrames OHLCV.

Implementa la cadena de fuentes:
  1. Binance  — OHLCV completo con volumen real
  2. KuCoin   — OHLCV completo con volumen real (tokens no listados en Binance)
  3. CoinGecko OHLC — sin volumen (volume=0); último recurso

Usado por los 5 use cases de análisis técnico para evitar duplicación.
"""

import logging
from typing import Optional

import pandas as pd

from core.infrastructure.external_apis.binance_client import (
    BinancePublicClient,
    BinanceClientError,
)
from core.infrastructure.external_apis.kucoin_client import (
    KuCoinPublicClient,
    KuCoinClientError,
)
from core.infrastructure.external_apis.coingecko_client import (
    CoinGeckoClient,
    CoinGeckoClientError,
)
from core.infrastructure.persistence.repositories_impl import DjangoCryptoAssetRepository

logger = logging.getLogger(__name__)

_QUOTE_CURRENCY = "USDT"

_COINGECKO_VALID_DAYS = [1, 7, 14, 30, 90, 180, 365]

_INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360,
    "12h": 720, "1d": 1440, "1w": 10080,
}


class OhlcvFetchResult:
    """Resultado de la obtención de OHLCV con metadatos de fuente."""
    __slots__ = ("df", "source")

    def __init__(self, df: pd.DataFrame, source: str) -> None:
        self.df = df
        self.source = source  # "binance" | "kucoin" | "coingecko"


def fetch_ohlcv_dataframe(
    symbol: str,
    interval: str = "1h",
    limit: int = 300,
    binance_client: Optional[BinancePublicClient] = None,
    kucoin_client: Optional[KuCoinPublicClient] = None,
    coingecko_client: Optional[CoinGeckoClient] = None,
    asset_repo: Optional[DjangoCryptoAssetRepository] = None,
) -> Optional[OhlcvFetchResult]:
    """
    Obtiene un DataFrame OHLCV con columnas [open, high, low, close, volume].

    Cadena: Binance → KuCoin → CoinGecko → None.
    Devuelve None si ninguna fuente sirve datos.
    """
    symbol = symbol.upper()
    binance = binance_client or BinancePublicClient()
    kucoin = kucoin_client or KuCoinPublicClient()
    coingecko = coingecko_client or CoinGeckoClient()
    repo = asset_repo or DjangoCryptoAssetRepository()

    def _with_funding(df: pd.DataFrame) -> pd.DataFrame:
        """
        Adjunta el coste de financiación del perpetuo, si el almacén lo tiene.

        Solo en la ruta HISTÓRICA, que es la del generador y los backtests: son
        los que miden rendimiento a lo largo del tiempo y por tanto los únicos
        a los que el funding puede cambiarles el veredicto. Que el coste viaje
        pegado al DataFrame —y no como parámetro— es lo que hace imposible
        backtestear un tramo sin él por descuido.

        Best-effort: sin BD o sin histórico, se devuelve el DataFrame tal cual y
        SIN columna de funding, que es distinto de una columna de ceros.
        """
        if limit < 300:
            return df
        try:
            from core.application.use_cases import funding_store
            return funding_store.attach_funding(df, symbol, interval)
        except Exception:  # noqa: BLE001 — el coste nunca rompe un análisis
            return df

    # ── 0. Almacén histórico propio ─────────────────────────────
    # Solo para peticiones HISTÓRICAS (limit ≥ 300: generador, backtests,
    # robustez): reproducible, sin latencia externa y capaz de superar las
    # 1000 velas por llamada de los exchanges. Las rutas en vivo (señales,
    # paper) siguen yendo a remoto porque usan la vela en formación, que el
    # almacén deliberadamente no guarda. Best-effort: nunca rompe la cadena.
    if limit >= 300:
        try:
            from core.application.use_cases import ohlcv_store
            if ohlcv_store.store_is_fresh(symbol, interval, limit):
                df = ohlcv_store.load_dataframe(symbol, interval, limit)
                if len(df) >= min(limit, 30):
                    return OhlcvFetchResult(df=_with_funding(df), source="store")
        except Exception:  # noqa: BLE001 — sin BD (tests puros) se sigue con remoto
            pass

    def _persist(df: pd.DataFrame, source: str) -> None:
        """Acumulación oportunista: todo lo que se trae de fuera se guarda."""
        try:
            from core.application.use_cases import ohlcv_store
            ohlcv_store.persist_candles(symbol, interval, df, source=source)
        except Exception:  # noqa: BLE001 — persistir nunca rompe un análisis
            pass

    # ── 1. Binance ──────────────────────────────────────────────
    binance_symbol = f"{symbol}{_QUOTE_CURRENCY}"
    try:
        raw = binance.get_klines(symbol=binance_symbol, interval=interval, limit=limit)
        df = _binance_klines_to_df(raw)
        if not df.empty:
            _persist(df, "binance")
            return OhlcvFetchResult(df=_with_funding(df), source="binance")
        logger.warning("Binance devolvió 0 velas para %s.", binance_symbol)
    except BinanceClientError as exc:
        logger.info("Binance no tiene %s (%s). Probando KuCoin...", binance_symbol, exc)

    # ── 2. KuCoin ───────────────────────────────────────────────
    try:
        raw = kucoin.get_klines(symbol=binance_symbol, interval=interval, limit=limit)
        df = _normalized_klines_to_df(raw)  # formato normalizado 6 columnas
        if not df.empty:
            logger.info(
                "KuCoin sirvió %d velas para %s.",
                len(df), binance_symbol,
            )
            _persist(df, "kucoin")
            return OhlcvFetchResult(df=_with_funding(df), source="kucoin")
    except KuCoinClientError as exc:
        logger.info("KuCoin no tiene %s (%s). Probando CoinGecko...", binance_symbol, exc)

    # ── 3. CoinGecko OHLC ──────────────────────────────────────
    asset = repo.get_by_symbol(symbol)
    if asset and asset.coingecko_id:
        days = _interval_limit_to_days(interval, limit)
        try:
            raw = coingecko.get_ohlc(
                coin_id=asset.coingecko_id, vs_currency="usd", days=days,
            )
            df = _coingecko_ohlc_to_df(raw)
            if not df.empty:
                logger.info(
                    "CoinGecko OHLC sirvió %d velas para %s (days=%s).",
                    len(df), symbol, days,
                )
                return OhlcvFetchResult(df=df, source="coingecko")
        except CoinGeckoClientError as exc:
            logger.error("CoinGecko OHLC falló para %s: %s", symbol, exc)

    return None


# ── Conversores ────────────────────────────────────────────────────

def _binance_klines_to_df(raw: list) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "num_trades",
        "taker_buy_base", "taker_buy_quote", "ignore",
    ])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_numeric(df["open_time"], errors="coerce")
    return df[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _coingecko_ohlc_to_df(raw: list) -> pd.DataFrame:
    """CoinGecko OHLC: [[ts, open, high, low, close], ...] — sin volumen."""
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close"])
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = 0.0
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    return df[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _normalized_klines_to_df(raw: list) -> pd.DataFrame:
    """
    Formato normalizado devuelto por KuCoinPublicClient.get_klines():
    [[ts_ms, open, high, low, close, volume], ...] — 6 columnas.
    Distinto del formato Binance de 12 columnas.
    """
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    return df[["timestamp", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _interval_limit_to_days(interval: str, limit: int) -> int:
    minutes_per_candle = _INTERVAL_MINUTES.get(interval, 60)
    total_days = (minutes_per_candle * limit) / 1440
    for d in _COINGECKO_VALID_DAYS:
        if d >= total_days:
            return d
    return 365
