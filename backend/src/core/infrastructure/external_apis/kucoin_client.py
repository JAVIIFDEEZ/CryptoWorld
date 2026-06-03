"""
kucoin_client.py — Adaptador para la API pública de KuCoin.

KuCoin ofrece un endpoint público sin autenticación para datos de mercado.
URL base: https://api.kucoin.com

Rate limits (IP, sin autenticación):
  - ~2000 requests / 30 segundos en el pool público
  - Confirmado vía headers: gw-ratelimit-limit: 2000

Formato de respuesta klines (cada elemento, orden ESPECIAL):
  [
    timestamp,  # str — Unix epoch en SEGUNDOS (no ms como Binance)
    open,       # str — precio apertura
    close,      # str — precio cierre  ← índice 2 (¡antes que high/low!)
    high,       # str — máximo         ← índice 3
    low,        # str — mínimo         ← índice 4
    volume,     # str — volumen en activo base
    turnover,   # str — volumen en USDT
  ]

Notas importantes:
  - El símbolo usa guión: "BTC-USDT" (no "BTCUSDT" como Binance)
  - Requiere startAt + endAt (epoch segundos); no existe parámetro "limit"
  - Retorna en orden DESCENDENTE (más reciente primero) → invertir al usar
  - Máximo 1500 velas por llamada

Intervalos soportados: 1min, 3min, 5min, 15min, 30min,
                        1hour, 2hour, 4hour, 6hour, 8hour, 12hour,
                        1day, 1week

Docs: https://docs.kucoin.com/#get-klines
"""

import logging
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ── Configuración ──────────────────────────────────────────────────

KUCOIN_BASE_URL = "https://api.kucoin.com"
REQUEST_TIMEOUT = 15  # segundos (aumentado para Docker DNS)

_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)
MAX_CANDLES_PER_CALL = 1500

# Mapa de intervalos Binance → KuCoin
_INTERVAL_MAP: dict[str, str] = {
    "1m":  "1min",
    "3m":  "3min",
    "5m":  "5min",
    "15m": "15min",
    "30m": "30min",
    "1h":  "1hour",
    "2h":  "2hour",
    "4h":  "4hour",
    "6h":  "6hour",
    "8h":  "8hour",
    "12h": "12hour",
    "1d":  "1day",
    "1w":  "1week",
}

# Duración en segundos de cada intervalo (para calcular startAt)
_INTERVAL_SECONDS: dict[str, int] = {
    "1min":  60,
    "3min":  180,
    "5min":  300,
    "15min": 900,
    "30min": 1800,
    "1hour": 3600,
    "2hour": 7200,
    "4hour": 14400,
    "6hour": 21600,
    "8hour": 28800,
    "12hour": 43200,
    "1day":  86400,
    "1week": 604800,
}


class KuCoinClientError(Exception):
    """Error al comunicarse con la API pública de KuCoin."""


class KuCoinPublicClient:
    """
    Cliente HTTP para la API pública de KuCoin sin autenticación.

    No requiere API key ni cuenta de KuCoin.
    Solo para datos de mercado de solo lectura.

    Uso:
        client = KuCoinPublicClient()
        klines = client.get_klines("HTX-USDT", "1h", limit=300)
    """

    def __init__(self, base_url: str = KUCOIN_BASE_URL, timeout: int = REQUEST_TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CryptoWorld/1.0",
        })
        adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 300,
    ) -> list[list[Any]]:
        """
        Obtiene velas OHLCV de KuCoin.

        Args:
            symbol:   Par en formato Binance ("BTCUSDT") o KuCoin ("BTC-USDT").
                      El cliente normaliza automáticamente.
            interval: Intervalo en formato Binance ("1h", "4h", "1d", etc.).
            limit:    Número de velas deseadas (máx. 1500).

        Returns:
            Lista de listas con el formato normalizado de Binance:
            [[ts_ms, open, high, low, close, volume], ...]
            Ordenado de más antigua a más reciente.

        Raises:
            KuCoinClientError: Si la API devuelve error o el par no existe.
        """
        kucoin_symbol = self._normalize_symbol(symbol)
        kucoin_interval = _INTERVAL_MAP.get(interval)
        if kucoin_interval is None:
            raise KuCoinClientError(f"Intervalo '{interval}' no soportado por KuCoin.")

        limit = min(limit, MAX_CANDLES_PER_CALL)
        interval_secs = _INTERVAL_SECONDS[kucoin_interval]
        end_at = int(time.time())
        start_at = end_at - (interval_secs * limit)

        params = {
            "type": kucoin_interval,
            "symbol": kucoin_symbol,
            "startAt": start_at,
            "endAt": end_at,
        }

        try:
            resp = self._session.get(
                f"{self._base_url}/api/v1/market/candles",
                params=params,
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise KuCoinClientError(f"Error HTTP al contactar KuCoin: {exc}") from exc

        payload = resp.json()
        code = str(payload.get("code", ""))
        if code != "200000":
            msg = payload.get("msg", "Error desconocido")
            raise KuCoinClientError(f"KuCoin API error [{code}]: {msg}")

        raw: list[list[str]] = payload.get("data", [])
        if not raw:
            raise KuCoinClientError(f"KuCoin no devolvió velas para {kucoin_symbol}.")

        # KuCoin devuelve en orden descendente → invertir
        raw_asc = list(reversed(raw))

        # Normalizar al formato Binance: [ts_ms, open, high, low, close, volume]
        # KuCoin:  [ts_secs, open, close, high, low, volume, turnover]
        # Indices:     0       1      2      3    4      5       6
        normalized = [
            [
                int(row[0]) * 1000,  # timestamp ms
                row[1],              # open
                row[3],              # high (índice 3 en KuCoin)
                row[4],              # low  (índice 4 en KuCoin)
                row[2],              # close (índice 2 en KuCoin, ¡antes que high/low!)
                row[5],              # volume
            ]
            for row in raw_asc
        ]
        return normalized

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        """
        Convierte símbolo Binance-style a KuCoin-style.

        Ejemplos:
          "HTXUSDT"  → "HTX-USDT"
          "BTC-USDT" → "BTC-USDT" (ya está en formato correcto)
          "BTCUSDT"  → "BTC-USDT"
        """
        symbol = symbol.upper().replace("-", "")
        for quote in ("USDT", "USDC", "BTC", "ETH", "BNB"):
            if symbol.endswith(quote) and len(symbol) > len(quote):
                base = symbol[: -len(quote)]
                return f"{base}-{quote}"
        return symbol
