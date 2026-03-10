"""
tests/unit/domain/repositories/test_crypto_asset_repository.py — Tests del contrato ICryptoAssetRepository.

ICryptoAssetRepository es una interfaz abstracta (ABC). Estos tests verifican:
  1. Que no se puede instanciar directamente
  2. Que una implementación stub completa satisface el contrato
  3. El comportamiento esperado de cada método: get_all, get_by_symbol, save

Patrón usado: In-memory repository stub para tests sin base de datos.
Ejecutar: pytest tests/unit/domain/repositories/test_crypto_asset_repository.py -v
"""

import pytest
from decimal import Decimal
from typing import List, Optional
from core.domain.repositories.crypto_asset_repository import ICryptoAssetRepository
from core.domain.entities.crypto_asset import CryptoAssetEntity


# ── Implementación stub in-memory ─────────────────────────────────

class InMemoryCryptoAssetRepository(ICryptoAssetRepository):
    """
    Repositorio de activos criptográficos en memoria para tests.
    Implementa todos los métodos abstractos de ICryptoAssetRepository.
    """

    def __init__(self):
        self._store: dict[str, CryptoAssetEntity] = {}
        self._next_id: int = 1

    def get_all(self) -> List[CryptoAssetEntity]:
        return list(self._store.values())

    def get_by_symbol(self, symbol: str) -> Optional[CryptoAssetEntity]:
        return self._store.get(symbol.upper())

    def save(self, asset: CryptoAssetEntity) -> CryptoAssetEntity:
        if asset.id is None:
            from dataclasses import replace
            asset = replace(asset, id=self._next_id)
            self._next_id += 1
        self._store[asset.symbol] = asset
        return asset


# ── Tests del contrato abstracto ──────────────────────────────────

class TestICryptoAssetRepositoryContract:
    """Verifica que el ABC no se puede instanciar directamente."""

    @pytest.mark.unit
    def test_cannot_instantiate_abstract_repository(self):
        with pytest.raises(TypeError):
            ICryptoAssetRepository()

    @pytest.mark.unit
    def test_partial_implementation_raises_type_error(self):
        """Una subclase que no implementa todos los métodos no es válida."""
        class PartialRepo(ICryptoAssetRepository):
            def get_all(self): return []
            # Faltan get_by_symbol y save

        with pytest.raises(TypeError):
            PartialRepo()


# ── Tests de get_all ──────────────────────────────────────────────

class TestInMemoryCryptoAssetRepositoryGetAll:
    """Tests del método get_all."""

    @pytest.mark.unit
    def test_get_all_returns_empty_list_when_no_assets(self):
        repo = InMemoryCryptoAssetRepository()
        assert repo.get_all() == []

    @pytest.mark.unit
    def test_get_all_returns_one_asset_after_save(self):
        repo = InMemoryCryptoAssetRepository()
        asset = CryptoAssetEntity(
            symbol="BTC", name="Bitcoin", current_price=Decimal("65000")
        )
        repo.save(asset)
        result = repo.get_all()
        assert len(result) == 1
        assert result[0].symbol == "BTC"

    @pytest.mark.unit
    def test_get_all_returns_all_saved_assets(self):
        repo = InMemoryCryptoAssetRepository()
        repo.save(CryptoAssetEntity(symbol="BTC", name="Bitcoin", current_price=Decimal("65000")))
        repo.save(CryptoAssetEntity(symbol="ETH", name="Ethereum", current_price=Decimal("3200")))
        repo.save(CryptoAssetEntity(symbol="SOL", name="Solana", current_price=Decimal("150")))
        result = repo.get_all()
        assert len(result) == 3

    @pytest.mark.unit
    def test_get_all_returns_list_type(self):
        repo = InMemoryCryptoAssetRepository()
        result = repo.get_all()
        assert isinstance(result, list)


# ── Tests de get_by_symbol ────────────────────────────────────────

class TestInMemoryCryptoAssetRepositoryGetBySymbol:
    """Tests del método get_by_symbol."""

    @pytest.mark.unit
    def test_get_by_symbol_returns_none_when_empty(self):
        repo = InMemoryCryptoAssetRepository()
        assert repo.get_by_symbol("BTC") is None

    @pytest.mark.unit
    def test_get_by_symbol_returns_asset_after_save(self):
        repo = InMemoryCryptoAssetRepository()
        asset = CryptoAssetEntity(
            symbol="BTC", name="Bitcoin", current_price=Decimal("65000")
        )
        repo.save(asset)
        result = repo.get_by_symbol("BTC")
        assert result is not None
        assert result.name == "Bitcoin"

    @pytest.mark.unit
    def test_get_by_symbol_case_insensitive(self):
        repo = InMemoryCryptoAssetRepository()
        repo.save(CryptoAssetEntity(symbol="BTC", name="Bitcoin", current_price=Decimal("65000")))
        assert repo.get_by_symbol("btc") is not None
        assert repo.get_by_symbol("Btc") is not None

    @pytest.mark.unit
    def test_get_by_symbol_returns_none_for_unknown_symbol(self):
        repo = InMemoryCryptoAssetRepository()
        repo.save(CryptoAssetEntity(symbol="BTC", name="Bitcoin", current_price=Decimal("65000")))
        assert repo.get_by_symbol("ETH") is None

    @pytest.mark.unit
    def test_get_by_symbol_returns_correct_asset_among_many(self):
        repo = InMemoryCryptoAssetRepository()
        repo.save(CryptoAssetEntity(symbol="BTC", name="Bitcoin", current_price=Decimal("65000")))
        repo.save(CryptoAssetEntity(symbol="ETH", name="Ethereum", current_price=Decimal("3200")))
        result = repo.get_by_symbol("ETH")
        assert result.name == "Ethereum"


# ── Tests de save ─────────────────────────────────────────────────

class TestInMemoryCryptoAssetRepositorySave:
    """Tests del método save."""

    @pytest.mark.unit
    def test_save_assigns_id_to_new_asset(self):
        repo = InMemoryCryptoAssetRepository()
        asset = CryptoAssetEntity(
            symbol="BTC", name="Bitcoin", current_price=Decimal("65000")
        )
        assert asset.id is None
        saved = repo.save(asset)
        assert saved.id is not None

    @pytest.mark.unit
    def test_save_returns_the_saved_entity(self):
        repo = InMemoryCryptoAssetRepository()
        asset = CryptoAssetEntity(
            symbol="ETH", name="Ethereum", current_price=Decimal("3200")
        )
        saved = repo.save(asset)
        assert saved.symbol == "ETH"
        assert saved.name == "Ethereum"

    @pytest.mark.unit
    def test_save_two_assets_get_different_ids(self):
        repo = InMemoryCryptoAssetRepository()
        a1 = repo.save(CryptoAssetEntity(symbol="BTC", name="Bitcoin", current_price=Decimal("65000")))
        a2 = repo.save(CryptoAssetEntity(symbol="ETH", name="Ethereum", current_price=Decimal("3200")))
        assert a1.id != a2.id

    @pytest.mark.unit
    def test_save_updates_existing_asset_by_symbol(self):
        repo = InMemoryCryptoAssetRepository()
        asset = CryptoAssetEntity(symbol="BTC", name="Bitcoin", current_price=Decimal("65000"))
        saved = repo.save(asset)

        from dataclasses import replace
        updated = replace(saved, current_price=Decimal("70000"))
        repo.save(updated)

        result = repo.get_by_symbol("BTC")
        assert result.current_price == Decimal("70000")
        assert len(repo.get_all()) == 1  # No duplica
