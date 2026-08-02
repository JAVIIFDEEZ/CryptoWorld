"""
alerts_dto.py — DTOs para el módulo de Alertas de Precio.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class CreateAlertInputDTO:
    """Datos para crear una nueva alerta de precio."""
    asset_symbol: str
    condition: str      # "ABOVE" | "BELOW"
    threshold_price: Decimal
    notes: str = ""


@dataclass(frozen=True)
class AlertOutputDTO:
    """Representación pública de una alerta de precio."""
    id: int
    asset_symbol: str
    asset_name: str
    condition: str
    threshold_price: str
    current_price: str
    is_active: bool
    is_triggered: bool
    triggered_at: Optional[str]
    notes: str
    created_at: str
