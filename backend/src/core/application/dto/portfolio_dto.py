"""
portfolio_dto.py — DTOs para el módulo de Portfolio.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional
from datetime import datetime


@dataclass(frozen=True)
class AddTradeInputDTO:
    """Datos para registrar una operación (compra o venta)."""
    asset_symbol: str
    trade_type: str          # "BUY" | "SELL"
    # Decimal y no float: las cantidades llegan con hasta 18 decimales y
    # un float de doble precision no las representa exactamente.
    quantity: Decimal
    price_usd: Decimal
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
    avg_buy_price: str          # Precio medio de compra (LONG) o de venta (SHORT) en USD
    total_invested: str         # Total invertido (LONG) o recibido (SHORT) en USD
    current_price: str          # Precio actual en USD
    current_value: str          # Valor actual en USD
    pnl_usd: str                # Ganancia/pérdida en USD
    pnl_pct: str                # Ganancia/pérdida en %
    is_profit: bool
    position_type: str = "LONG"  # "LONG" | "SHORT"


@dataclass(frozen=True)
class PortfolioSummaryDTO:
    """Resumen global del portfolio del usuario."""
    total_invested_usd: str
    total_current_value_usd: str
    total_pnl_usd: str
    total_pnl_pct: str
    positions: list
    is_profit: bool
    # Desglose LONG / SHORT para el resumen de cabecera
    long_count: int = 0
    short_count: int = 0
    total_long_invested_usd: str = "0.00"     # Capital comprometido en posiciones LONG
    total_short_exposure_usd: str = "0.00"    # Coste de recompra actual de posiciones SHORT


# ── DTOs del modelo de posiciones explícitas ──────────────────────────────────

@dataclass(frozen=True)
class OpenPositionInputDTO:
    """Datos para abrir una nueva posición (LONG o SHORT)."""
    asset_symbol: str
    direction: str        # "LONG" | "SHORT"
    quantity: Decimal
    entry_price: Decimal
    opened_at: str        # ISO 8601 string
    label: str = ""
    notes: str = ""


@dataclass(frozen=True)
class ClosePositionInputDTO:
    """Datos para cerrar parcial o totalmente una posición."""
    close_quantity: Decimal
    close_price: Decimal
    executed_at: str      # ISO 8601 string
    notes: str = ""


@dataclass(frozen=True)
class AddToPositionInputDTO:
    """Datos para ampliar una posición existente (escalar entrada, recalcula AVCO)."""
    quantity: Decimal
    entry_price: Decimal
    executed_at: str      # ISO 8601 string
    notes: str = ""


@dataclass(frozen=True)
class PositionDTO:
    """Representación pública completa de una posición."""
    id: int
    asset_symbol: str
    asset_name: str
    logo_url: Optional[str]
    direction: str              # "LONG" | "SHORT"
    status: str                 # "OPEN" | "CLOSED"
    label: str
    avg_entry_price: str
    open_quantity: str          # Cantidad actualmente abierta
    initial_quantity: str       # Cantidad total históricamente entrada
    current_price: str          # Precio live (sólo en OPEN)
    unrealized_pnl_usd: str     # PnL no realizado (sólo en OPEN)
    unrealized_pnl_pct: str     # PnL % no realizado (sólo en OPEN)
    realized_pnl_usd: str       # PnL acumulado de cierres parciales
    total_pnl_usd: str          # realized + unrealized
    is_profit: bool
    opened_at: str
    closed_at: Optional[str]
    trades_count: int


@dataclass(frozen=True)
class PositionSummaryDTO:
    """Resumen de posiciones del usuario."""
    open_positions: list        # lista de PositionDTO con status=OPEN
    closed_positions: list      # lista de PositionDTO con status=CLOSED
    total_unrealized_pnl_usd: str
    total_realized_pnl_usd: str
    open_long_count: int
    open_short_count: int
