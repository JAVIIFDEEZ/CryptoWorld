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
    BinanceClientError,
    BinancePublicClient,
)
from core.infrastructure.external_apis.coingecko_client import (
    CoinGeckoClient,
    CoinGeckoClientError,
)
from core.infrastructure.external_apis.kucoin_client import (
    KuCoinClientError,
    KuCoinPublicClient,
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

    # ── 1. Binance ──────────────────────────────────────────────
    binance_symbol = f"{symbol}{_QUOTE_CURRENCY}"
    try:
        raw = binance.get_klines(symbol=binance_symbol, interval=interval, limit=limit)
        df = _binance_klines_to_df(raw)
        if not df.empty:
            return OhlcvFetchResult(df=df, source="binance")
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
            return OhlcvFetchResult(df=df, source="kucoin")
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
