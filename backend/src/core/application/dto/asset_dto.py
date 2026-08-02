"""
asset_dto.py — DTOs para operaciones con activos criptográficos y análisis técnico.
"""

from dataclasses import dataclass
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
    coingecko_id: Optional[str]
    logo_url: Optional[str]
    asset_address: Optional[str]
    decimals: Optional[int]
    is_bullish_24h: bool


@dataclass(frozen=True)
class AnalysisRequestInputDTO:
    """Datos para solicitar la ejecución de un análisis."""
    asset_symbol: str
    analysis_type: str          # "RSI", "MACD", "SMA", "EMA", "BOLLINGER"
    interval: str = "1h"
    limit: int = 300


@dataclass(frozen=True)
class AnalysisOutputDTO:
    """Resultado devuelto tras ejecutar un análisis."""
    id: int
    asset_symbol: str
    analysis_type: str
    status: str
    result: Optional[dict]


@dataclass(frozen=True)
class SignalsRequestDTO:
    """Datos para solicitar el panel multi-indicador."""
    asset_symbol: str
    interval: str = "1h"
    limit: int = 300


@dataclass(frozen=True)
class PredictionRequestDTO:
    """Datos para solicitar predicción ML."""
    asset_symbol: str
    interval: str = "1h"
    horizon: int = 5
    limit: int = 500


@dataclass(frozen=True)
class PatternsRequestDTO:
    """Datos para solicitar detección de patrones."""
    asset_symbol: str
    interval: str = "1h"
    limit: int = 300


@dataclass(frozen=True)
class BacktestRequestDTO:
    """Datos para solicitar backtesting."""
    asset_symbol: str
    strategy: str
    interval: str = "1h"
    limit: int = 500
    initial_capital: float = 10000.0
