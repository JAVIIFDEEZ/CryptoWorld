"""
tests/unit/domain/value_objects/test_email.py — Tests de Value Objects.

Cubre dos value objects del módulo email.py:
  - Email: valida el formato de email y garantiza inmutabilidad
  - CryptoSymbol: normaliza a mayúsculas y valida el ticker

Los Value Objects son inmutables y se comparan por valor, no por referencia.
No necesitan base de datos ni Django.
Ejecutar: pytest tests/unit/domain/value_objects/test_email.py -v
"""

import pytest
from dataclasses import FrozenInstanceError
from core.domain.value_objects.email import Email, CryptoSymbol


class TestEmailValueObject:
    """Tests del Value Object Email."""

    @pytest.mark.unit
    def test_create_valid_email(self):
        email = Email("user@example.com")
        assert email.value == "user@example.com"

    @pytest.mark.unit
    def test_email_str_returns_value(self):
        email = Email("user@example.com")
        assert str(email) == "user@example.com"

    @pytest.mark.unit
    def test_valid_email_with_subdomain(self):
        email = Email("user@mail.example.com")
        assert email.value == "user@mail.example.com"

    @pytest.mark.unit
    def test_valid_email_with_plus(self):
        email = Email("user+tag@example.com")
        assert email.value == "user+tag@example.com"

    @pytest.mark.unit
    def test_valid_email_with_dots_in_local(self):
        email = Email("first.last@example.com")
        assert email.value == "first.last@example.com"

    @pytest.mark.unit
    def test_email_without_at_raises_value_error(self):
        with pytest.raises(ValueError, match="Formato de email inválido"):
            Email("invalidemail.com")

    @pytest.mark.unit
    def test_email_without_domain_raises_value_error(self):
        with pytest.raises(ValueError, match="Formato de email inválido"):
            Email("user@")

    @pytest.mark.unit
    def test_email_without_tld_raises_value_error(self):
        with pytest.raises(ValueError, match="Formato de email inválido"):
            Email("user@example")

    @pytest.mark.unit
    def test_empty_email_raises_value_error(self):
        with pytest.raises(ValueError, match="Formato de email inválido"):
            Email("")

    @pytest.mark.unit
    def test_email_only_at_raises_value_error(self):
        with pytest.raises(ValueError, match="Formato de email inválido"):
            Email("@")

    @pytest.mark.unit
    def test_email_equality_by_value(self):
        email1 = Email("user@example.com")
        email2 = Email("user@example.com")
        assert email1 == email2

    @pytest.mark.unit
    def test_different_emails_not_equal(self):
        email1 = Email("user1@example.com")
        email2 = Email("user2@example.com")
        assert email1 != email2

    @pytest.mark.unit
    def test_email_is_immutable(self):
        email = Email("user@example.com")
        with pytest.raises((FrozenInstanceError, TypeError)):
            email.value = "other@example.com"

    @pytest.mark.unit
    def test_email_usable_as_dict_key(self):
        """Inmutabilidad implica que es hashable y puede ser clave."""
        email = Email("user@example.com")
        d = {email: "data"}
        assert d[email] == "data"

    @pytest.mark.unit
    def test_email_usable_in_set(self):
        email1 = Email("user@example.com")
        email2 = Email("user@example.com")
        s = {email1, email2}
        assert len(s) == 1


class TestCryptoSymbolValueObject:
    """Tests del Value Object CryptoSymbol."""

    @pytest.mark.unit
    def test_create_valid_symbol_uppercase(self):
        symbol = CryptoSymbol("BTC")
        assert symbol.value == "BTC"

    @pytest.mark.unit
    def test_lowercase_symbol_normalized_to_uppercase(self):
        symbol = CryptoSymbol("btc")
        assert symbol.value == "BTC"

    @pytest.mark.unit
    def test_mixed_case_symbol_normalized(self):
        symbol = CryptoSymbol("eTh")
        assert symbol.value == "ETH"

    @pytest.mark.unit
    def test_symbol_str_returns_value(self):
        symbol = CryptoSymbol("BTC")
        assert str(symbol) == "BTC"

    @pytest.mark.unit
    def test_empty_symbol_raises_value_error(self):
        with pytest.raises(ValueError, match="Símbolo de criptoactivo inválido"):
            CryptoSymbol("")

    @pytest.mark.unit
    def test_symbol_with_numbers_raises_value_error(self):
        with pytest.raises(ValueError, match="Símbolo de criptoactivo inválido"):
            CryptoSymbol("BTC1")

    @pytest.mark.unit
    def test_symbol_with_spaces_raises_value_error(self):
        with pytest.raises(ValueError, match="Símbolo de criptoactivo inválido"):
            CryptoSymbol("BT C")

    @pytest.mark.unit
    def test_symbol_with_special_chars_raises_value_error(self):
        with pytest.raises(ValueError, match="Símbolo de criptoactivo inválido"):
            CryptoSymbol("BT-C")

    @pytest.mark.unit
    def test_symbol_equality_by_value(self):
        s1 = CryptoSymbol("BTC")
        s2 = CryptoSymbol("btc")  # ambos se normalizan a BTC
        assert s1 == s2

    @pytest.mark.unit
    def test_different_symbols_not_equal(self):
        s1 = CryptoSymbol("BTC")
        s2 = CryptoSymbol("ETH")
        assert s1 != s2

    @pytest.mark.unit
    def test_symbol_is_immutable(self):
        symbol = CryptoSymbol("BTC")
        with pytest.raises((FrozenInstanceError, TypeError)):
            symbol.value = "ETH"

    @pytest.mark.unit
    def test_symbol_usable_as_dict_key(self):
        symbol = CryptoSymbol("BTC")
        d = {symbol: "Bitcoin"}
        assert d[symbol] == "Bitcoin"

    @pytest.mark.unit
    def test_symbol_usable_in_set(self):
        s1 = CryptoSymbol("BTC")
        s2 = CryptoSymbol("btc")
        s = {s1, s2}
        assert len(s) == 1
