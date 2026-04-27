"""
get_news_feed.py — Caso de uso para feed de noticias y sentimiento.

Fuente: CryptoCompare News API (plan gratuito, requiere CRYPTOCOMPARE_API_KEY en .env).
Docs: https://min-api.cryptocompare.com/documentation#latest-news

Sentimiento inferido a partir de los campos 'downvotes'/'upvotes' de CryptoCompare
o de palabras clave en el título (fallback).
"""

import logging
from datetime import datetime, UTC
from typing import Optional

from core.application.dto.market_intelligence_dto import NewsItemOutputDTO
from core.infrastructure.external_apis.cryptocompare_client import (
    CryptoCompareClient,
    CryptoCompareClientError,
)

logger = logging.getLogger(__name__)

# Palabras negativas para inferir sentimiento cuando no hay score
_NEGATIVE_WORDS = frozenset(
    {
        "crash", "drop", "fall", "bear", "hack", "scam", "ban", "banned",
        "lawsuit", "loss", "fear", "sell", "short", "low", "down", "risk",
        "warning", "concern", "collapse", "plunge",
    }
)
_POSITIVE_WORDS = frozenset(
    {
        "surge", "rally", "bull", "ath", "all-time high", "gain", "rise",
        "buy", "adoption", "launch", "partnership", "upgrade", "record",
        "growth", "up", "higher", "profit", "support",
    }
)


def _infer_sentiment(article: dict) -> str:
    """
    Infiere el sentimiento a partir de votos y palabras clave del título.
    CryptoCompare no provee sentimiento explícito; lo calculamos nosotros.
    """
    upvotes = int(article.get("upvotes", 0) or 0)
    downvotes = int(article.get("downvotes", 0) or 0)

    if upvotes + downvotes > 5:
        if upvotes > downvotes * 2:
            return "positive"
        if downvotes > upvotes * 2:
            return "negative"
        return "neutral"

    # Fallback: palabras clave
    title_lower = (article.get("title", "") + " " + article.get("body", ""))[:300].lower()
    pos_hits = sum(1 for w in _POSITIVE_WORDS if w in title_lower)
    neg_hits = sum(1 for w in _NEGATIVE_WORDS if w in title_lower)

    if pos_hits > neg_hits:
        return "positive"
    if neg_hits > pos_hits:
        return "negative"
    return "neutral"


def _article_to_dto(article: dict) -> NewsItemOutputDTO:
    """Convierte un artículo de CryptoCompare al DTO interno."""
    published_ts = article.get("published_on", 0)
    try:
        published_at = datetime.fromtimestamp(published_ts, UTC).isoformat()
    except (TypeError, OSError):
        published_at = datetime.now(UTC).isoformat()

    source_info = article.get("source_info", {})
    source_name = source_info.get("name") or article.get("source", "CryptoCompare")

    return NewsItemOutputDTO(
        id=str(article.get("id", "")),
        title=article.get("title", ""),
        url=article.get("url", ""),
        imageurl=article.get("imageurl", ""),
        source=source_name,
        published_at=published_at,
        sentiment=_infer_sentiment(article),
        body=article.get("body", "")[:400],
        categories=article.get("categories", ""),
        relevance_score=None,
    )


class GetNewsFeedUseCase:
    """
    Devuelve noticias filtrables por query y sentimiento.

    Fuente real: CryptoCompare News API.
    Si la API falla (rate limit, sin API key, red), devuelve lista vacía
    con aviso en lugar de datos simulados.
    """

    def __init__(self, client: Optional[CryptoCompareClient] = None) -> None:
        self._client = client or CryptoCompareClient()

    def execute(self, query: str, sentiment: str, limit: int) -> dict:
        q = query.strip().lower()
        s = sentiment.strip().lower()

        # CryptoCompare 'categories' solo acepta etiquetas exactas (BTC, ETH, Mining…).
        # Solo lo usamos cuando la query parece un símbolo corto (≤ 10 chars, sin espacios).
        categories = ""
        if q and len(q) <= 10 and " " not in q:
            categories = q.upper()

        try:
            articles = self._client.get_latest_news(
                categories=categories,
                limit=min(limit * 2, 50),  # Pedimos más para compensar filtrado
            )
        except CryptoCompareClientError as exc:
            logger.warning("CryptoCompare News no disponible: %s", exc)
            return {
                "items": [],
                "total": 0,
                "source": "cryptocompare",
                "error": "Feed de noticias temporalmente no disponible.",
            }

        # Convertir a DTOs
        items = [_article_to_dto(a) for a in articles if a.get("title")]

        # Filtrar por query en título, cuerpo o etiquetas (siempre que haya query)
        if q:
            items = [
                i for i in items
                if q in i.title.lower() or q in (i.source or "").lower()
            ]

        # Filtrar por sentimiento si se especifica
        if s and s != "all":
            items = [i for i in items if i.sentiment == s]

        return {
            "items": items[:limit],
            "total": len(items),
            "source": "cryptocompare",
        }
