"""
tests/unit/test_domain_entities.py — Tests unitarios de entidades del dominio.

Los tests unitarios del dominio son los más valiosos:
  - No necesitan base de datos
  - No necesitan Django
  - Son extremadamente rápidos
  - Verifican las reglas de negocio directamente

Marcados con @pytest.mark.unit para poder ejecutarlos aislados:
  pytest -m unit
"""

import pytest
from decimal import Decimal
from core.domain.entities.user import UserEntity
from core.domain.entities.crypto_asset import CryptoAssetEntity
from core.domain.value_objects.email import Email, CryptoSymbol


# ── UserEntity ─────────────────────────────────────────────────────

class TestUserEntity:

    @pytest.mark.unit
    def test_create_valid_user(self):
        user = UserEntity(email="user@example.com", username="testuser")
        assert user.email == "user@example.com"
        assert user.username == "testuser"
        assert user.is_active is True

    @pytest.mark.unit
    def test_invalid_email_raises_error(self):
        with pytest.raises(ValueError, match="Email inválido"):
            UserEntity(email="not-an-email", username="testuser")

    @pytest.mark.unit
    def test_short_username_raises_error(self):
        with pytest.raises(ValueError, match="al menos 3 caracteres"):
            UserEntity(email="user@example.com", username="ab")

    @pytest.mark.unit
    def test_deactivate_user(self):
        user = UserEntity(email="user@example.com", username="testuser")
        user.deactivate()
        assert user.is_active is False

    @pytest.mark.unit
    def test_promote_to_staff(self):
        user = UserEntity(email="user@example.com", username="testuser")
        user.promote_to_staff()
        assert user.is_staff is True


# ── CryptoAssetEntity ──────────────────────────────────────────────

class TestCryptoAssetEntity:

    @pytest.mark.unit
    def test_symbol_normalized_to_uppercase(self):
        asset = CryptoAssetEntity(symbol="btc", name="Bitcoin", current_price=Decimal("65000"))
        assert asset.symbol == "BTC"

    @pytest.mark.unit
    def test_is_bullish_true_when_positive_change(self):
        asset = CryptoAssetEntity(
            symbol="BTC", name="Bitcoin",
            current_price=Decimal("65000"),
            price_change_24h=Decimal("2.5"),
        )
        assert asset.is_bullish_24h is True

    @pytest.mark.unit
    def test_is_bullish_false_when_negative_change(self):
        asset = CryptoAssetEntity(
            symbol="ETH", name="Ethereum",
            current_price=Decimal("3200"),
            price_change_24h=Decimal("-1.2"),
        )
        assert asset.is_bullish_24h is False

    @pytest.mark.unit
    def test_negative_price_raises_error(self):
        with pytest.raises(ValueError, match="precio no puede ser negativo"):
            CryptoAssetEntity(symbol="BTC", name="Bitcoin", current_price=Decimal("-1"))


# ── Value Objects ──────────────────────────────────────────────────

class TestEmailValueObject:

    @pytest.mark.unit
    def test_valid_email(self):
        email = Email("user@example.com")
        assert str(email) == "user@example.com"

    @pytest.mark.unit
    def test_invalid_email_raises(self):
        with pytest.raises(ValueError):
            Email("not-valid")

    @pytest.mark.unit
    def test_email_is_immutable(self):
        email = Email("user@example.com")
        with pytest.raises(Exception):
            email.value = "other@example.com"


class TestCryptoSymbolValueObject:

    @pytest.mark.unit
    def test_symbol_uppercased(self):
        sym = CryptoSymbol("btc")
        assert sym.value == "BTC"

    @pytest.mark.unit
    def test_invalid_symbol_raises(self):
        with pytest.raises(ValueError):
            CryptoSymbol("BTC123")
