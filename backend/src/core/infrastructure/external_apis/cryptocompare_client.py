"""
cryptocompare_client.py — Adaptador para la API de noticias de CryptoCompare.

CryptoCompare ofrece un endpoint público de noticias crypto con categorías,
tags y puntuación de sentimiento calculada automáticamente.

Plan gratuito: hasta ~100 000 llamadas/mes con API key.
Registro: https://min-api.cryptocompare.com/

Docs: https://min-api.cryptocompare.com/documentation#latest-news

Principio aplicado: Adapter Pattern (Arquitectura Hexagonal).
"""

import logging
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.conf import settings

logger = logging.getLogger(__name__)

CRYPTOCOMPARE_BASE_URL = "https://min-api.cryptocompare.com/data"
REQUEST_TIMEOUT = 15  # segundos

_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)


class CryptoCompareClientError(Exception):
    """Error al comunicarse con la API de CryptoCompare."""


class CryptoCompareClient:
    """
    Cliente HTTP para la API de noticias de CryptoCompare.

    Requiere CRYPTOCOMPARE_API_KEY en settings/env.
    Si no hay API key, intenta sin autenticación (rate limit muy bajo).

    Uso:
        client = CryptoCompareClient()
        news = client.get_latest_news(categories="BTC,ETH", limit=20)
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        api_key = getattr(settings, "CRYPTOCOMPARE_API_KEY", None)
        if api_key:
            self._session.headers["authorization"] = f"Apikey {api_key}"

    def get_latest_news(
        self,
        categories: str = "",
        excludecategories: str = "",
        lang: str = "EN",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        GET /data/v2/news/ — Últimas noticias de CryptoCompare.

        Args:
            categories: Categorías separadas por coma (e.g. "BTC,ETH,Altcoin").
            excludecategories: Categorías a excluir.
            lang: Idioma del artículo ("EN" | "ES" | ...).
            limit: Número máximo de artículos (max 50 por llamada).

        Returns:
            Lista de dicts con title, url, source, published_on, body, tags, etc.
        """
        params: dict[str, Any] = {
            "lang": lang,
        }
        if categories:
            params["categories"] = categories
        if excludecategories:
            params["excludecategories"] = excludecategories

        try:
            resp = self._session.get(
                f"{CRYPTOCOMPARE_BASE_URL}/v2/news/",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("Type") != 100:
                raise CryptoCompareClientError(
                    f"CryptoCompare error: {data.get('Message', 'Unknown')}"
                )

            articles = data.get("Data", [])
            return articles[:limit]

        except CryptoCompareClientError:
            raise
        except requests.exceptions.Timeout:
            raise CryptoCompareClientError("Timeout al conectar con CryptoCompare.")
        except requests.exceptions.RequestException as exc:
            raise CryptoCompareClientError(f"Error de red: {exc}") from exc

    def get_news_feeds(self) -> list[dict[str, Any]]:
        """
        GET /data/news/feeds — Lista de fuentes de noticias disponibles.
        Útil para saber qué feeds hay en CryptoCompare.
        """
        try:
            resp = self._session.get(
                f"{CRYPTOCOMPARE_BASE_URL}/news/feeds",
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            raise CryptoCompareClientError(f"Error de red: {exc}") from exc
