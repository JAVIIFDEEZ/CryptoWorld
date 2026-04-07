"""
admin_manage_asset.py — Casos de uso CRUD de activos criptográficos (admin).
"""

from decimal import Decimal, InvalidOperation
from typing import List, Optional

from core.domain.entities.crypto_asset import CryptoAssetEntity
from core.domain.repositories.crypto_asset_repository import ICryptoAssetRepository
from core.application.dto.admin_dto import (
    AdminCreateAssetInputDTO,
    AdminUpdateAssetInputDTO,
    AdminAssetOutputDTO,
)


def _to_output_dto(entity: CryptoAssetEntity) -> AdminAssetOutputDTO:
    """Convertir entidad de dominio a DTO de salida."""
    return AdminAssetOutputDTO(
        id=entity.id,
        symbol=entity.symbol,
        name=entity.name,
        current_price=str(entity.current_price),
        market_cap=str(entity.market_cap) if entity.market_cap else None,
        volume_24h=str(entity.volume_24h) if entity.volume_24h else None,
        price_change_24h=str(entity.price_change_24h) if entity.price_change_24h else None,
        coingecko_id=entity.coingecko_id,
        logo_url=entity.logo_url,
    )


class AdminListAssetsUseCase:
    """Listar todos los activos criptográficos."""

    def __init__(self, asset_repository: ICryptoAssetRepository) -> None:
        self._asset_repo = asset_repository

    def execute(self) -> List[AdminAssetOutputDTO]:
        assets = self._asset_repo.get_all()
        return [_to_output_dto(a) for a in assets]


class AdminCreateAssetUseCase:
    """Crear un activo criptográfico manualmente."""

    def __init__(self, asset_repository: ICryptoAssetRepository) -> None:
        self._asset_repo = asset_repository

    def execute(self, input_dto: AdminCreateAssetInputDTO) -> AdminAssetOutputDTO:
        # Verificar que no exista ya
        existing = self._asset_repo.get_by_symbol(input_dto.symbol)
        if existing is not None:
            raise ValueError(f"Ya existe un activo con el símbolo '{input_dto.symbol}'.")

        try:
            price = Decimal(input_dto.current_price)
        except (InvalidOperation, TypeError):
            raise ValueError("El precio debe ser un número válido.")

        entity = CryptoAssetEntity(
            symbol=input_dto.symbol,
            name=input_dto.name,
            current_price=price,
            market_cap=Decimal(input_dto.market_cap) if input_dto.market_cap else None,
            volume_24h=Decimal(input_dto.volume_24h) if input_dto.volume_24h else None,
            price_change_24h=Decimal(input_dto.price_change_24h) if input_dto.price_change_24h else None,
            coingecko_id=input_dto.coingecko_id,
            logo_url=input_dto.logo_url,
        )
        saved = self._asset_repo.save(entity)
        return _to_output_dto(saved)


class AdminUpdateAssetUseCase:
    """Actualizar un activo criptográfico existente."""

    def __init__(self, asset_repository: ICryptoAssetRepository) -> None:
        self._asset_repo = asset_repository

    def execute(self, input_dto: AdminUpdateAssetInputDTO) -> AdminAssetOutputDTO:
        entity = self._asset_repo.get_by_id(input_dto.asset_id)
        if entity is None:
            raise ValueError("Activo no encontrado.")

        if input_dto.name is not None:
            entity.name = input_dto.name
        if input_dto.current_price is not None:
            try:
                entity.current_price = Decimal(input_dto.current_price)
            except (InvalidOperation, TypeError):
                raise ValueError("El precio debe ser un número válido.")
        if input_dto.market_cap is not None:
            entity.market_cap = Decimal(input_dto.market_cap) if input_dto.market_cap else None
        if input_dto.volume_24h is not None:
            entity.volume_24h = Decimal(input_dto.volume_24h) if input_dto.volume_24h else None
        if input_dto.price_change_24h is not None:
            entity.price_change_24h = Decimal(input_dto.price_change_24h) if input_dto.price_change_24h else None
        if input_dto.coingecko_id is not None:
            entity.coingecko_id = input_dto.coingecko_id
        if input_dto.logo_url is not None:
            entity.logo_url = input_dto.logo_url

        saved = self._asset_repo.save(entity)
        return _to_output_dto(saved)


class AdminDeleteAssetUseCase:
    """Eliminar un activo criptográfico."""

    def __init__(self, asset_repository: ICryptoAssetRepository) -> None:
        self._asset_repo = asset_repository

    def execute(self, asset_id: int) -> None:
        entity = self._asset_repo.get_by_id(asset_id)
        if entity is None:
            raise ValueError("Activo no encontrado.")
        self._asset_repo.delete(asset_id)
