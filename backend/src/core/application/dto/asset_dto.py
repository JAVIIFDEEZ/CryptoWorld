"""
asset_dto.py — DTOs para operaciones con activos criptográficos.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class CryptoAssetOutputDTO:
    """Representación pública de un activo criptográfico."""
    id: int
    symbol: str
    name: str
    current_price: str          # Decimal serializado como string para JSON
    market_cap: Optional[str]
    volume_24h: Optional[str]
    price_change_24h: Optional[str]
    is_bullish_24h: bool


@dataclass(frozen=True)
class AnalysisRequestInputDTO:
    """
    Datos para solicitar la ejecución de un análisis.
    Estructura base; se amplía en fases posteriores del TFG.
    """
    asset_symbol: str
    analysis_type: str          # "RSI", "MACD", "SMA", etc.


@dataclass(frozen=True)
class AnalysisOutputDTO:
    """Resultado devuelto tras ejecutar un análisis."""
    id: int
    asset_symbol: str
    analysis_type: str
    status: str
    result: Optional[dict]
