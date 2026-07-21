"""
get_news_globe.py — Caso de uso: noticias del mundo sobre el globo 3D.

Obtiene el feed real (CryptoCompare) y lo clasifica geográfica y temáticamente
(dominio: news_geography) en marcadores con lat/lon, categoría dominante y
titulares por región. Cacheado: la clasificación es determinista y el feed
cambia despacio.
"""

import logging
from dataclasses import asdict

from core.application.use_cases.get_news_feed import GetNewsFeedUseCase
from core.domain.services.news_geography import classify_news_geography

logger = logging.getLogger(__name__)


class GetNewsGlobeUseCase:

    def __init__(self, news_uc: GetNewsFeedUseCase | None = None) -> None:
        self._news = news_uc or GetNewsFeedUseCase()

    def execute(self, limit: int = 60) -> dict:
        feed = self._news.execute(query="", sentiment="", limit=limit)
        if feed.get("error"):
            return {"error": feed["error"], "markers": [], "total": 0}
        items = [asdict(i) if not isinstance(i, dict) else i for i in feed.get("items", [])]
        result = classify_news_geography(items)
        result["source"] = feed.get("source", "cryptocompare")
        return result
