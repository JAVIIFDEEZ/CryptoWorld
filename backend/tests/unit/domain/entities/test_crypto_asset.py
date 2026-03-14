"""
tests/unit/domain/entities/test_crypto_asset.py — Tests unitarios de entidades cripto.

Cubre tres entidades del módulo crypto_asset.py:
  - CryptoAssetEntity: activo criptográfico con reglas de dominio
  - MarketDataSnapshotEntity: instantánea de datos de mercado
  - AnalysisExecutionEntity: registro de ejecución de análisis técnico

No necesitan base de datos ni Django.
Ejecutar: pytest tests/unit/domain/entities/test_crypto_asset.py -v
"""

import pytest
from decimal import Decimal
from core.domain.entities.crypto_asset import (
    CryptoAssetEntity,
    MarketDataSnapshotEntity,
    PortfolioAssetEntity,
    AnalysisExecutionEntity,
)


class TestCryptoAssetEntityCreation:
    """Tests de construcción y validación inicial de CryptoAssetEntity."""

    @pytest.mark.unit
    def test_create_valid_asset(self):
        asset = CryptoAssetEntity(
            symbol="BTC", name="Bitcoin", current_price=Decimal("65000")
        )
        assert asset.symbol == "BTC"
        assert asset.name == "Bitcoin"
        assert asset.current_price == Decimal("65000")

    @pytest.mark.unit
    def test_symbol_normalized_to_uppercase(self):
        asset = CryptoAssetEntity(
            symbol="btc", name="Bitcoin", current_price=Decimal("65000")
        )
        assert asset.symbol == "BTC"

    @pytest.mark.unit
    def test_mixed_case_symbol_normalized(self):
        asset = CryptoAssetEntity(
            symbol="eTh", name="Ethereum", current_price=Decimal("3200")
        )
        assert asset.symbol == "ETH"

    @pytest.mark.unit
    def test_empty_symbol_raises_value_error(self):
        with pytest.raises(ValueError, match="símbolo"):
            CryptoAssetEntity(symbol="", name="Bitcoin", current_price=Decimal("65000"))

    @pytest.mark.unit
    def test_negative_price_raises_value_error(self):
        with pytest.raises(ValueError, match="precio"):
            CryptoAssetEntity(
                symbol="BTC", name="Bitcoin", current_price=Decimal("-1")
            )

    @pytest.mark.unit
    def test_zero_price_is_valid(self):
        asset = CryptoAssetEntity(
            symbol="NEW", name="NewCoin", current_price=Decimal("0")
        )
        assert asset.current_price == Decimal("0")

    @pytest.mark.unit
    def test_optional_fields_default_to_none(self):
        asset = CryptoAssetEntity(
            symbol="BTC", name="Bitcoin", current_price=Decimal("65000")
        )
        assert asset.market_cap is None
        assert asset.volume_24h is None
        assert asset.price_change_24h is None
        assert asset.id is None

    @pytest.mark.unit
    def test_create_asset_with_all_fields(self):
        asset = CryptoAssetEntity(
            symbol="BTC",
            name="Bitcoin",
            current_price=Decimal("65000"),
            market_cap=Decimal("1200000000000"),
            volume_24h=Decimal("30000000000"),
            price_change_24h=Decimal("2.5"),
            coingecko_id="bitcoin",
            logo_url="https://example.com/btc.png",
            asset_address="0x123",
            decimals=8,
            id=1,
        )
        assert asset.id == 1
        assert asset.market_cap == Decimal("1200000000000")
        assert asset.volume_24h == Decimal("30000000000")
        assert asset.price_change_24h == Decimal("2.5")
        assert asset.coingecko_id == "bitcoin"
        assert asset.logo_url == "https://example.com/btc.png"
        assert asset.asset_address == "0x123"
        assert asset.decimals == 8


class TestCryptoAssetEntityIsBullish:
    """Tests de la regla de negocio is_bullish_24h."""

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
    def test_is_bullish_false_when_change_is_none(self):
        asset = CryptoAssetEntity(
            symbol="BTC", name="Bitcoin", current_price=Decimal("65000")
        )
        assert asset.is_bullish_24h is False

    @pytest.mark.unit
    def test_is_bullish_false_when_zero_change(self):
        asset = CryptoAssetEntity(
            symbol="BTC", name="Bitcoin",
            current_price=Decimal("65000"),
            price_change_24h=Decimal("0"),
        )
        assert asset.is_bullish_24h is False

    @pytest.mark.unit
    def test_is_bullish_true_with_very_small_positive_change(self):
        asset = CryptoAssetEntity(
            symbol="BTC", name="Bitcoin",
            current_price=Decimal("65000"),
            price_change_24h=Decimal("0.000001"),
        )
        assert asset.is_bullish_24h is True


class TestMarketDataSnapshotEntity:
    """Tests de MarketDataSnapshotEntity."""

    @pytest.mark.unit
    def test_create_valid_snapshot(self):
        snapshot = MarketDataSnapshotEntity(
            asset_symbol="BTC",
            price=Decimal("65000"),
            volume=Decimal("30000000000"),
            timestamp="2026-03-09T12:00:00Z",
        )
        assert snapshot.asset_symbol == "BTC"
        assert snapshot.price == Decimal("65000")
        assert snapshot.volume == Decimal("30000000000")
        assert snapshot.timestamp == "2026-03-09T12:00:00Z"

    @pytest.mark.unit
    def test_snapshot_id_defaults_to_none(self):
        snapshot = MarketDataSnapshotEntity(
            asset_symbol="ETH",
            price=Decimal("3200"),
            volume=Decimal("15000000000"),
            timestamp="2026-03-09T12:00:00Z",
        )
        assert snapshot.id is None

    @pytest.mark.unit
    def test_snapshot_with_explicit_id(self):
        snapshot = MarketDataSnapshotEntity(
            asset_symbol="BTC",
            price=Decimal("65000"),
            volume=Decimal("30000000000"),
            timestamp="2026-03-09T12:00:00Z",
            id=99,
        )
        assert snapshot.id == 99


class TestAnalysisExecutionEntity:
    """Tests de AnalysisExecutionEntity y su máquina de estados."""

    @pytest.mark.unit
    def test_create_valid_analysis(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="BTC", analysis_type="RSI"
        )
        assert analysis.asset_symbol == "BTC"
        assert analysis.analysis_type == "RSI"

    @pytest.mark.unit
    def test_default_status_is_pending(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="BTC", analysis_type="RSI"
        )
        assert analysis.status == "pending"

    @pytest.mark.unit
    def test_default_result_is_none(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="BTC", analysis_type="RSI"
        )
        assert analysis.result is None

    @pytest.mark.unit
    def test_default_id_is_none(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="BTC", analysis_type="RSI"
        )
        assert analysis.id is None

    @pytest.mark.unit
    def test_mark_as_running_changes_status(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="BTC", analysis_type="MACD"
        )
        analysis.mark_as_running()
        assert analysis.status == "running"

    @pytest.mark.unit
    def test_complete_sets_status_and_result(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="BTC", analysis_type="SMA"
        )
        result_data = {"value": 64500.0, "period": 20}
        analysis.complete(result_data)
        assert analysis.status == "completed"
        assert analysis.result == result_data

    @pytest.mark.unit
    def test_complete_with_complex_result(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="ETH", analysis_type="BOLLINGER"
        )
        result_data = {
            "upper_band": 3500.0,
            "middle_band": 3200.0,
            "lower_band": 2900.0,
        }
        analysis.complete(result_data)
        assert analysis.result["upper_band"] == 3500.0
        assert analysis.result["lower_band"] == 2900.0

    @pytest.mark.unit
    def test_fail_sets_status_to_failed(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="BTC", analysis_type="EMA"
        )
        analysis.fail()
        assert analysis.status == "failed"

    @pytest.mark.unit
    def test_fail_does_not_set_result(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="BTC", analysis_type="EMA"
        )
        analysis.fail()
        assert analysis.result is None

    @pytest.mark.unit
    def test_state_transition_pending_to_running_to_completed(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="BTC", analysis_type="RSI"
        )
        assert analysis.status == "pending"
        analysis.mark_as_running()
        assert analysis.status == "running"
        analysis.complete({"rsi": 72.5})
        assert analysis.status == "completed"

    @pytest.mark.unit
    def test_state_transition_running_to_failed(self):
        analysis = AnalysisExecutionEntity(
            asset_symbol="BTC", analysis_type="RSI"
        )
        analysis.mark_as_running()
        analysis.fail()
        assert analysis.status == "failed"


class TestPortfolioAssetEntity:
    """Tests de reglas de dominio para PortfolioAssetEntity."""

    @pytest.mark.unit
    def test_avg_buy_price(self):
        position = PortfolioAssetEntity(
            user_id=1,
            asset_symbol="BTC",
            quantity=Decimal("2"),
            purchase_value_usd=Decimal("80000"),
        )
        assert position.avg_buy_price_usd == Decimal("40000")

    @pytest.mark.unit
    def test_update_current_value(self):
        position = PortfolioAssetEntity(
            user_id=1,
            asset_symbol="ETH",
            quantity=Decimal("3"),
            purchase_value_usd=Decimal("6000"),
        )
        position.update_current_value(Decimal("2500"))
        assert position.current_value_usd == Decimal("7500")

    @pytest.mark.unit
    def test_unrealized_pnl(self):
        position = PortfolioAssetEntity(
            user_id=1,
            asset_symbol="BTC",
            quantity=Decimal("1"),
            purchase_value_usd=Decimal("30000"),
            current_value_usd=Decimal("36000"),
        )
        assert position.unrealized_pnl_usd == Decimal("6000")
        assert position.unrealized_pnl_pct == Decimal("20")

    @pytest.mark.unit
    def test_add_position_accumulates(self):
        position = PortfolioAssetEntity(
            user_id=1,
            asset_symbol="BTC",
            quantity=Decimal("1"),
            purchase_value_usd=Decimal("30000"),
        )
        position.add_position(Decimal("0.5"), Decimal("18000"))
        assert position.quantity == Decimal("1.5")
        assert position.purchase_value_usd == Decimal("48000")

    @pytest.mark.unit
    def test_add_position_rejects_non_positive_quantity(self):
        position = PortfolioAssetEntity(
            user_id=1,
            asset_symbol="BTC",
            quantity=Decimal("1"),
            purchase_value_usd=Decimal("30000"),
        )
        with pytest.raises(ValueError, match="positiva"):
            position.add_position(Decimal("0"), Decimal("1000"))
