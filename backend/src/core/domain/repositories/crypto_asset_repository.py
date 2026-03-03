"""
crypto_asset_repository.py — Contrato del repositorio de activos cripto.

Define las operaciones de acceso a datos para CryptoAsset.
La implementación concreta que usa Django ORM está en infrastructure/.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from core.domain.entities.crypto_asset import CryptoAssetEntity


class ICryptoAssetRepository(ABC):
    """
    Interfaz abstracta del repositorio de activos criptográficos.
    """

    @abstractmethod
    def get_all(self) -> List[CryptoAssetEntity]:
        """Obtener todos los activos disponibles en el sistema."""
        ...

    @abstractmethod
    def get_by_symbol(self, symbol: str) -> Optional[CryptoAssetEntity]:
        """Obtener un activo por su ticker (BTC, ETH, ...)."""
        ...

    @abstractmethod
    def save(self, asset: CryptoAssetEntity) -> CryptoAssetEntity:
        """Persistir o actualizar un activo criptográfico."""
        ...
