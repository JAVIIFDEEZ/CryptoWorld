"""
get_assets.py — Caso de uso: Obtener listado de activos criptográficos.

Orquesta la obtención de activos desde el repositorio y los
transforma en DTOs de salida para la capa de interfaces.
"""

from typing import List

from core.domain.repositories.crypto_asset_repository import ICryptoAssetRepository
from core.application.dto.asset_dto import CryptoAssetOutputDTO


class GetAssetsUseCase:
    """
    Caso de uso: listar todos los activos disponibles.
    """

    def __init__(self, crypto_asset_repository: ICryptoAssetRepository) -> None:
        self._asset_repo = crypto_asset_repository

    def execute(self) -> List[CryptoAssetOutputDTO]:
        """
        Obtener todos los activos y transformarlos a DTOs.

        Returns:
            Lista de CryptoAssetOutputDTO listos para serializar a JSON.
        """
        assets = self._asset_repo.get_all()

        return [
            CryptoAssetOutputDTO(
                id=asset.id,
                symbol=asset.symbol,
                name=asset.name,
                current_price=str(asset.current_price),
                market_cap=str(asset.market_cap) if asset.market_cap else None,
                volume_24h=str(asset.volume_24h) if asset.volume_24h else None,
                price_change_24h=str(asset.price_change_24h) if asset.price_change_24h else None,
                coingecko_id=asset.coingecko_id,
                logo_url=asset.logo_url,
                asset_address=asset.asset_address,
                decimals=asset.decimals,
                is_bullish_24h=asset.is_bullish_24h,
            )
            for asset in assets
        ]
