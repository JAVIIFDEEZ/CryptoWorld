"""
crypto_asset.py — Entidad de dominio: Activo Criptográfico.

Representa un criptoactivo en el modelo de negocio.
Contiene las reglas del dominio relacionadas con activos digitales.

No sabe de bases de datos, no sabe de HTTP, no sabe de Django.
Solo describe QUÉ ES un activo y QUÉ PUEDE HACER.
"""

from dataclasses import dataclass
from typing import Optional
from decimal import Decimal


@dataclass
class CryptoAssetEntity:
    """
    Entidad central del dominio: un activo criptográfico.

    symbol: ticker del activo (BTC, ETH, etc.)
    name: nombre completo
    current_price: precio actual en USD
    market_cap: capitalización de mercado en USD
    """
    symbol: str
    name: str
    current_price: Decimal
    market_cap: Optional[Decimal] = None
    volume_24h: Optional[Decimal] = None
    price_change_24h: Optional[Decimal] = None
    id: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("El símbolo del activo no puede estar vacío.")
        if self.current_price < 0:
            raise ValueError("El precio no puede ser negativo.")
        self.symbol = self.symbol.upper()

    @property
    def is_bullish_24h(self) -> bool:
        """Regla de negocio: el activo sube si el cambio 24h es positivo."""
        if self.price_change_24h is None:
            return False
        return self.price_change_24h > 0


@dataclass
class MarketDataSnapshotEntity:
    """
    Entidad que representa una instantánea de datos de mercado.
    Se genera periódicamente para análisis histórico.
    """
    asset_symbol: str
    price: Decimal
    volume: Decimal
    timestamp: str   # ISO 8601
    id: Optional[int] = None


@dataclass
class AnalysisExecutionEntity:
    """
    Entidad que representa la ejecución de un análisis cuantitativo.
    Estructura base lista para ampliar en fases siguientes del TFG.
    """
    asset_symbol: str
    analysis_type: str          # p.ej. "RSI", "MACD", "SMA"
    status: str = "pending"     # pending | running | completed | failed
    result: Optional[dict] = None
    id: Optional[int] = None

    def mark_as_running(self) -> None:
        self.status = "running"

    def complete(self, result: dict) -> None:
        self.status = "completed"
        self.result = result

    def fail(self) -> None:
        self.status = "failed"
