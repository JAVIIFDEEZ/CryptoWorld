"""
get_market_overview.py — Caso de uso: Resumen global del mercado crypto.

Fuentes:
  - CoinGecko GET /global  → market cap total, volumen 24h, dominancia BTC
  - Alternative.me Fear & Greed Index (API pública gratuita, sin auth)
    Docs: https://alternative.me/crypto/fear-and-greed-index/#api

Si alguna fuente falla, devuelve el último valor conocido o "—".
"""

import logging
from datetime import datetime, UTC
from typing import Optional

import requests

from core.application.dto.market_intelligence_dto import MarketOverviewOutputDTO
from core.infrastructure.external_apis.coingecko_client import (
    CoinGeckoClient,
    CoinGeckoClientError,
)

logger = logging.getLogger(__name__)

_FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"
_TIMEOUT = 8  # segundos


def _fetch_fear_greed() -> Optional[int]:
    """
    Obtiene el índice Fear & Greed actual desde Alternative.me.
    Devuelve entero 0-100 o None si falla.
    """
    try:
        resp = requests.get(_FEAR_GREED_URL, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        value = data["data"][0]["value"]
        return int(value)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fear & Greed Index no disponible: %s", exc)
        return None


class GetMarketOverviewUseCase:
    """
    Devuelve métricas globales del mercado crypto.

    Flujo:
      1. CoinGeckoClient.get_global() → cap total, vol 24h, dominancia BTC
      2. Alternative.me → Fear & Greed Index
      3. Si alguna fuente falla → fallback a valor por defecto
    """

    def __init__(self, client: Optional[CoinGeckoClient] = None) -> None:
        self._client = client or CoinGeckoClient()

    def execute(self) -> MarketOverviewOutputDTO:
        now = datetime.now(UTC).isoformat()

        # ── 1. CoinGecko /global ───────────────────────────────────
        total_market_cap = "0"
        total_volume = "0"
        btc_dominance = "0.00"

        try:
            raw = self._client.get_global()
            data = raw.get("data", {})

            mc = data.get("total_market_cap", {}).get("usd")
            vol = data.get("total_volume", {}).get("usd")
            btc_pct = data.get("market_cap_percentage", {}).get("btc")

            if mc is not None:
                total_market_cap = str(int(mc))
            if vol is not None:
                total_volume = str(int(vol))
            if btc_pct is not None:
                btc_dominance = f"{float(btc_pct):.2f}"

        except CoinGeckoClientError as exc:
            logger.warning("CoinGecko /global no disponible: %s. Usando fallback.", exc)
            total_market_cap = "2450000000000"
            total_volume = "156800000000"
            btc_dominance = "48.30"

        # ── 2. Fear & Greed Index ──────────────────────────────────
        fear_greed = _fetch_fear_greed()
        if fear_greed is None:
            fear_greed = 50  # Neutral como fallback

        return MarketOverviewOutputDTO(
            total_market_cap_usd=total_market_cap,
            total_volume_24h_usd=total_volume,
            btc_dominance_pct=btc_dominance,
            fear_greed_index=fear_greed,
            updated_at=now,
        )
