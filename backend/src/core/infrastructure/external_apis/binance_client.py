"""
binance_client.py — Adaptador para la API pública de Binance.

Binance ofrece un endpoint público sin autenticación para datos de mercado.
URL base: https://data-api.binance.vision  (modo read-only, sin API key)

Rate limits (IP):
  - 1200 weight/min en total
  - /api/v3/klines → weight=2  →  ~600 llamadas OHLCV efectivas por minuto

Formato de respuesta klines (cada elemento):
  [
    open_time,      # int  — timestamp de apertura en ms
    open,           # str  — precio apertura
    high,           # str  — máximo
    low,            # str  — mínimo
    close,          # str  — precio cierre
    volume,         # str  — volumen en activo base (ej. BTC)
    close_time,     # int  — timestamp de cierre en ms
    quote_volume,   # str  — volumen en moneda quote (ej. USDT)
    num_trades,     # int  — número de operaciones
    taker_buy_base, # str  — volumen comprador taker base
    taker_buy_quote,# str  — volumen comprador taker quote
    ignore          # str  — campo reservado, ignorar
  ]

Docs: https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md

Principio aplicado: Adapter Pattern (Arquitectura Hexagonal).
"""

import logging
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

# ── Configuración ──────────────────────────────────────────────────

BINANCE_BASE_URL = "https://data-api.binance.vision"
REQUEST_TIMEOUT = 20  # segundos (aumentado para cubrir latencia DNS en Docker)

# Reintentos automáticos ante fallos de red/SSL transitorios
_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,          # 0s, 1s, 2s entre reintentos
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)

# Intervalos admitidos por Binance para klines
VALID_INTERVALS = frozenset({
    "1s",
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d",
    "1w",
    "1M",
})


class BinanceClientError(Exception):
    """Error al comunicarse con la API pública de Binance."""


class BinancePublicClient:
    """
    Cliente HTTP para la API pública de Binance sin autenticación.

    No requiere API key ni cuenta de Binance.
    Pensado exclusivamente para datos de mercado de solo lectura.

    Uso:
        client = BinancePublicClient()
        klines = client.get_klines("BTCUSDT", "1h", limit=200)
        ticker = client.get_ticker_24hr("BTCUSDT")
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    # ── Endpoints públicos ─────────────────────────────────────────

    def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        end_time_ms: int | None = None,
    ) -> list[list]:
        """
        GET /api/v3/klines — Velas OHLCV históricas.

        Args:
            symbol:   Par de trading en formato Binance (ej: "BTCUSDT").
            interval: Intervalo temporal.  Válidos: 1m, 5m, 15m, 30m,
                      1h, 2h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M.
            limit:    Número de velas a devolver (máx. 1000, default 500).

        Returns:
            Lista de listas con el formato descrito en el módulo docstring.

        Raises:
            BinanceClientError: si la petición HTTP falla.
        """
        if interval not in VALID_INTERVALS:
            raise BinanceClientError(
                f"Intervalo '{interval}' no válido. "
                f"Opciones: {sorted(VALID_INTERVALS)}"
            )

        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": min(limit, 1000),
        }
        # endTime permite paginar hacia atrás (backfill del histórico propio):
        # velas con open_time ≤ endTime, las `limit` más recientes de ese rango.
        if end_time_ms is not None:
            params["endTime"] = int(end_time_ms)
        return self._get("/api/v3/klines", params=params)

    def get_ticker_24hr(
        self,
        symbol: Optional[str] = None,
    ) -> Any:
        """
        GET /api/v3/ticker/24hr — Estadísticas de precio/volumen en 24 h.

        Args:
            symbol: Par concreto (ej: "BTCUSDT").
                    Si es None devuelve todos los pares (lista).

        Returns:
            Dict con el par solicitado, o lista de dicts si symbol=None.

        Raises:
            BinanceClientError: si la petición HTTP falla.
        """
        params: dict = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self._get("/api/v3/ticker/24hr", params=params)

    def ping(self) -> bool:
        """
        GET /api/v3/ping — Comprueba conectividad con la API.

        Returns:
            True si el servidor responde, False en caso contrario.
        """
        try:
            self._get("/api/v3/ping")
            return True
        except BinanceClientError:
            return False

    # ── Internos ───────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        """Ejecuta una petición GET y devuelve el JSON parseado."""
        url = f"{BINANCE_BASE_URL}{path}"
        try:
            response = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            logger.error(
                "Binance HTTP error %s en %s: %s",
                exc.response.status_code if exc.response else "?",
                path,
                exc,
            )
            raise BinanceClientError(
                f"Binance devolvió HTTP {exc.response.status_code if exc.response else '?'}: {exc}"
            ) from exc
        except requests.RequestException as exc:
            logger.error("Binance request error en %s: %s", path, exc)
            raise BinanceClientError(f"Error de red con Binance: {exc}") from exc
