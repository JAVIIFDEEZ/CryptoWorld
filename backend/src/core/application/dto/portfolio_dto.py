"""
portfolio_dto.py — DTOs para el módulo de Portfolio.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass(frozen=True)
class AddTradeInputDTO:
    """Datos para registrar una operación (compra o venta)."""
    asset_symbol: str
    trade_type: str          # "BUY" | "SELL"
    quantity: float
    price_usd: float
    executed_at: str         # ISO 8601 string
    notes: str = ""


@dataclass(frozen=True)
class TradeOutputDTO:
    """Representación pública de una operación."""
    id: int
    asset_symbol: str
    asset_name: str
    trade_type: str
    quantity: str
    price_usd: str
    total_usd: str
    notes: str
    executed_at: str
    created_at: str


@dataclass(frozen=True)
class PortfolioPositionDTO:
    """Posición actual de un activo en el portfolio."""
    asset_symbol: str
    asset_name: str
    logo_url: Optional[str]
    quantity: str               # Total de unidades
    avg_buy_price: str          # Precio medio de compra en USD
    total_invested: str         # Total invertido en USD
    current_price: str          # Precio actual en USD
    current_value: str          # Valor actual en USD
    pnl_usd: str                # Ganancia/pérdida en USD
    pnl_pct: str                # Ganancia/pérdida en %
    is_profit: bool


@dataclass(frozen=True)
class PortfolioSummaryDTO:
    """Resumen global del portfolio del usuario."""
    total_invested_usd: str
    total_current_value_usd: str
    total_pnl_usd: str
    total_pnl_pct: str
    positions: list
    is_profit: bool
