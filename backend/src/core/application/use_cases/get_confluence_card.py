"""
get_confluence_card.py — Caso de uso: Confluence Card de un activo.

Orquesta la construcción de la ficha de confluencia: resuelve el activo a
través del contrato de repositorio (inyectado — este módulo no importa
nada de infrastructure), obtiene el OHLCV diario con la cadena compartida
de fuentes y delega TODO el cálculo en el domain service.

La ficha se cachea 1 hora: el endpoint REST y la landing SEO comparten la
misma entrada de caché, de modo que el coste de cálculo se paga una vez.
"""

import logging

from django.core.cache import cache

from core.application.dto.asset_dto import ConfluenceCardDTO
from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
from core.domain.repositories.crypto_asset_repository import ICryptoAssetRepository
from core.domain.services.confluence_service import build_confluence_card

logger = logging.getLogger(__name__)

# Velas diarias de un año: suficientes para SMA200, pivotes y Fibonacci
_INTERVAL = "1d"
_CANDLES = 365
_MIN_CANDLES = 60

_CACHE_KEY = "confluence_card:{symbol}"
_CACHE_TTL = 3600  # 1 hora — igual que la landing SEO


class AssetNotFoundError(ValueError):
    """El símbolo o slug no corresponde a ningún activo del catálogo."""


class ConfluenceDataUnavailableError(ValueError):
    """Ninguna fuente OHLCV pudo servir datos suficientes para el activo."""


class GetConfluenceCardUseCase:
    """Devuelve la ConfluenceCardDTO de un activo, cacheada 1 hora."""

    def __init__(self, asset_repo: ICryptoAssetRepository) -> None:
        self._asset_repo = asset_repo

    def execute(self, symbol: str) -> ConfluenceCardDTO:
        symbol = symbol.upper()

        asset = self._asset_repo.get_by_symbol(symbol)
        if asset is None:
            raise AssetNotFoundError(f"Activo '{symbol}' no encontrado.")

        cache_key = _CACHE_KEY.format(symbol=symbol)
        cached = cache.get(cache_key)
        if cached is not None:
            return ConfluenceCardDTO(**cached)

        result = fetch_ohlcv_dataframe(
            symbol=symbol, interval=_INTERVAL, limit=_CANDLES
        )
        if result is None or result.df.empty or len(result.df) < _MIN_CANDLES:
            raise ConfluenceDataUnavailableError(
                f"Datos de mercado insuficientes para generar la ficha de {symbol}."
            )

        card = build_confluence_card(result.df, symbol)
        payload = {
            **card,
            "name": asset.name,
            "slug": (asset.coingecko_id or symbol.lower()),
            "logo_url": asset.logo_url,
            "interval": _INTERVAL,
            "data_source": result.source,
        }

        cache.set(cache_key, payload, _CACHE_TTL)
        logger.info("Confluence card generada para %s (fuente=%s)", symbol, result.source)
        return ConfluenceCardDTO(**payload)
