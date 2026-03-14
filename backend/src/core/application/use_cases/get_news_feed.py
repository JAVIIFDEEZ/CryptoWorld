"""
get_news_feed.py — Caso de uso para feed de noticias y sentimiento.
"""

from datetime import datetime, UTC

from core.application.dto.market_intelligence_dto import NewsItemOutputDTO


class GetNewsFeedUseCase:
    """
    Devuelve noticias filtrables por query y sentimiento.

    Implementación inicial contract-first. En la integración real consumirá
    GDELT (fuente principal) y calculará sentimiento en backend.
    """

    def execute(self, query: str, sentiment: str, limit: int) -> list[NewsItemOutputDTO]:
        raw_items = [
            NewsItemOutputDTO(
                title="Bitcoin consolida por encima de 62k tras datos macro en EE.UU.",
                url="https://example.com/news/btc-62k",
                source="GDELT",
                published_at=datetime.now(UTC).isoformat(),
                sentiment="positive",
                relevance_score=0.91,
            ),
            NewsItemOutputDTO(
                title="Aumento de actividad on-chain en Ethereum durante las ultimas 24h",
                url="https://example.com/news/eth-onchain",
                source="GDELT",
                published_at=datetime.now(UTC).isoformat(),
                sentiment="neutral",
                relevance_score=0.84,
            ),
            NewsItemOutputDTO(
                title="Salida de capital en altcoins de baja capitalizacion",
                url="https://example.com/news/altcoins-outflow",
                source="GDELT",
                published_at=datetime.now(UTC).isoformat(),
                sentiment="negative",
                relevance_score=0.77,
            ),
        ]

        q = query.strip().lower()
        s = sentiment.strip().lower()

        filtered = [
            item
            for item in raw_items
            if (not q or q in item.title.lower()) and (s in {"", "all"} or item.sentiment == s)
        ]

        return filtered[:limit]
