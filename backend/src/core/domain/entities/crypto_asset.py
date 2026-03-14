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
    coingecko_id: Optional[str] = None
    logo_url: Optional[str] = None
    asset_address: Optional[str] = None
    decimals: Optional[int] = None
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
    market_cap: Optional[Decimal] = None
    fully_diluted_valuation: Optional[Decimal] = None
    circulating_supply: Optional[Decimal] = None
    total_supply: Optional[Decimal] = None
    max_supply: Optional[Decimal] = None
    ath: Optional[Decimal] = None
    ath_date: Optional[str] = None
    atl: Optional[Decimal] = None
    atl_date: Optional[str] = None
    price_change_24h_pct: Optional[Decimal] = None
    price_change_7d_pct: Optional[Decimal] = None
    price_change_30d_pct: Optional[Decimal] = None
    id: Optional[int] = None


@dataclass
class PortfolioAssetEntity:
    """
    Entidad de dominio para una posición de portfolio.
    """

    user_id: int
    asset_symbol: str
    quantity: Decimal
    purchase_value_usd: Decimal
    current_value_usd: Optional[Decimal] = None
    id: Optional[int] = None

    @property
    def avg_buy_price_usd(self) -> Optional[Decimal]:
        if self.quantity == 0:
            return None
        return self.purchase_value_usd / self.quantity

    @property
    def unrealized_pnl_usd(self) -> Optional[Decimal]:
        if self.current_value_usd is None:
            return None
        return self.current_value_usd - self.purchase_value_usd

    @property
    def unrealized_pnl_pct(self) -> Optional[Decimal]:
        if self.current_value_usd is None or self.purchase_value_usd == 0:
            return None
        return ((self.current_value_usd - self.purchase_value_usd) / self.purchase_value_usd) * Decimal("100")

    def update_current_value(self, current_price: Decimal) -> None:
        self.current_value_usd = self.quantity * current_price

    def add_position(self, quantity: Decimal, purchase_value_usd: Decimal) -> None:
        if quantity <= 0:
            raise ValueError("La cantidad a agregar debe ser positiva.")
        self.quantity += quantity
        self.purchase_value_usd += purchase_value_usd


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
