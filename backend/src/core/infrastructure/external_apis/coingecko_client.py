"""
coingecko_client.py — Adaptador para la API pública de CoinGecko.

CoinGecko Demo (gratuito): 30 req/min, sin tarjeta de crédito.
Si se configura COINGECKO_API_KEY se añade como header para reducir
errores de rate-limit.

Uso en este proyecto:
  - get_markets()  → sincronizar catálogo de CryptoAsset (logos, ids, precios)
  - get_global()   → métricas globales (market cap total, dominancia BTC)

El OHLCV está cubierto por BinancePublicClient (más rápido y sin límites).

Docs: https://docs.coingecko.com/reference/introduction
Principio: Adapter Pattern (Arquitectura Hexagonal).
"""

import logging
from typing import Any, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
REQUEST_TIMEOUT = 15  # segundos


class CoinGeckoClientError(Exception):
    """Error al comunicarse con la API de CoinGecko."""


class CoinGeckoClient:
    """
    Cliente HTTP para CoinGecko API v3 (plan gratuito/Demo).

    Uso:
        client = CoinGeckoClient()
        markets = client.get_markets(per_page=100)
        global_data = client.get_global()
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        api_key = getattr(settings, "COINGECKO_API_KEY", None)
        if api_key:
            self._session.headers["x-cg-demo-api-key"] = api_key

    # ── Endpoints ─────────────────────────────────────────────────

    def get_markets(
        self,
        vs_currency: str = "usd",
        per_page: int = 100,
        page: int = 1,
        order: str = "market_cap_desc",
    ) -> list[dict[str, Any]]:
        """
        GET /coins/markets — Top monedas por capitalización.

        Devuelve símbolo, nombre, precio, market cap, volumen, cambio 24h,
        logo URL y coingecko_id.  Ideal para sync completo del catálogo.

        Docs: https://docs.coingecko.com/reference/coins-markets
        """
        return self._get("/coins/markets", params={
            "vs_currency": vs_currency,
            "order": order,
            "per_page": min(per_page, 250),
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "24h",
        })

    def get_global(self) -> dict[str, Any]:
        """
        GET /global — Métricas globales del mercado crypto.

        Devuelve:
          data.total_market_cap.usd       — capitalización total en USD
          data.total_volume.usd           — volumen total 24h en USD
          data.market_cap_percentage.btc  — dominancia de Bitcoin (%)
          data.market_cap_change_percentage_24h_usd

        Docs: https://docs.coingecko.com/reference/global
        """
        return self._get("/global")

    def get_ohlc(
        self,
        coin_id: str,
        vs_currency: str = "usd",
        days: int | str = 30,
    ) -> list[list]:
        """
        GET /coins/{id}/ohlc — OHLC para gráficos de velas.

        Respuesta: [[timestamp_ms, open, high, low, close], ...]
        NOTA: No incluye volumen. Se devuelve volume=0 al consumir.

        Granularidad automática (plan gratuito):
          1-2 días  → velas de 30 min
          3-30 días → velas de 4h
          31+ días  → velas de 4 días

        `days` válidos: 1, 7, 14, 30, 90, 180, 365, "max"

        Docs: https://docs.coingecko.com/reference/coins-id-ohlc
        """
        return self._get(f"/coins/{coin_id}/ohlc", params={
            "vs_currency": vs_currency,
            "days": days,
        })

    def get_coin_detail(self, coin_id: str) -> dict[str, Any]:
        """
        GET /coins/{id} — Información detallada de una moneda: enlaces,
        datos de mercado (ATH, suministro) y categorías.

        Se solicita únicamente lo imprescindible para reducir el payload:
        tickers, community_data y developer_data se deshabilitan.

        Docs: https://docs.coingecko.com/reference/coins-id
        """
        return self._get(f"/coins/{coin_id}", params={
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "false",
            "developer_data": "false",
            "sparkline": "false",
        })

    def get_sparkline_prices(
        self,
        coin_id: str,
        vs_currency: str = "usd",
        days: int = 7,
    ) -> list[float]:
        """
        GET /coins/{id}/market_chart — Precios de cierre diarios para sparklines.

        Devuelve una lista plana de precios (float) ordenados cronológicamente,
        uno por día durante los últimos `days` días.

        Docs: https://docs.coingecko.com/reference/coins-id-market-chart
        """
        data = self._get(f"/coins/{coin_id}/market_chart", params={
            "vs_currency": vs_currency,
            "days": days,
            "interval": "daily",
        })
        # data["prices"] = [[timestamp_ms, price], ...]
        prices: list[list] = data.get("prices", [])
        return [float(point[1]) for point in prices]

    def ping(self) -> bool:
        """Comprueba que la API responde."""
        try:
            self._get("/ping")
            return True
        except CoinGeckoClientError:
            return False

    # ── Interno ───────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"{COINGECKO_BASE_URL}{path}"
        try:
            response = self._session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response else "?"
            logger.error("CoinGecko HTTP %s en %s: %s", code, path, exc)
            raise CoinGeckoClientError(f"CoinGecko HTTP {code}: {exc}") from exc
        except requests.RequestException as exc:
            logger.error("CoinGecko request error en %s: %s", path, exc)
            raise CoinGeckoClientError(f"Error de red con CoinGecko: {exc}") from exc
