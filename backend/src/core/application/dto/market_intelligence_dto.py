"""
market_intelligence_dto.py — DTOs para datos de mercado, on-chain y noticias.

Estos DTOs definen contratos de salida estables para el frontend.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MarketOverviewOutputDTO:
    total_market_cap_usd: str
    total_volume_24h_usd: str
    btc_dominance_pct: str
    fear_greed_index: int
    updated_at: str


@dataclass(frozen=True)
class OhlcvCandleOutputDTO:
    open_time: str
    open: str
    high: str
    low: str
    close: str
    volume: str


@dataclass(frozen=True)
class OnChainMetricPointOutputDTO:
    metric: str
    symbol: str
    timestamp: str
    value: str
    source: str


@dataclass(frozen=True)
class NewsItemOutputDTO:
    title: str
    url: str
    source: str
    published_at: str
    sentiment: str
    relevance_score: Optional[float]
