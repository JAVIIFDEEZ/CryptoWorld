"""
admin_dto.py — DTOs para operaciones de administración.

DTOs de entrada y salida para los casos de uso del panel de admin.
"""

from dataclasses import dataclass
from typing import Optional


# ── Entrada ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AdminUpdateUserInputDTO:
    """Datos que un admin puede modificar de un usuario."""
    user_id: int
    is_active: Optional[bool] = None
    role: Optional[str] = None
    is_email_verified: Optional[bool] = None


@dataclass(frozen=True)
class AdminCreateAssetInputDTO:
    """Datos para crear un activo criptográfico manualmente."""
    symbol: str
    name: str
    current_price: str
    market_cap: Optional[str] = None
    volume_24h: Optional[str] = None
    price_change_24h: Optional[str] = None
    coingecko_id: Optional[str] = None
    logo_url: Optional[str] = None


@dataclass(frozen=True)
class AdminUpdateAssetInputDTO:
    """Datos para actualizar un activo criptográfico."""
    asset_id: int
    name: Optional[str] = None
    current_price: Optional[str] = None
    market_cap: Optional[str] = None
    volume_24h: Optional[str] = None
    price_change_24h: Optional[str] = None
    coingecko_id: Optional[str] = None
    logo_url: Optional[str] = None


# ── Salida ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AdminUserOutputDTO:
    """Representación completa de un usuario para el panel de admin."""
    id: int
    email: str
    username: str
    is_active: bool
    is_staff: bool
    role: str
    is_email_verified: bool
    is_2fa_enabled: bool
    date_joined: str


@dataclass(frozen=True)
class AdminAssetOutputDTO:
    """Representación de un activo para el panel de admin."""
    id: int
    symbol: str
    name: str
    current_price: str
    market_cap: Optional[str]
    volume_24h: Optional[str]
    price_change_24h: Optional[str]
    coingecko_id: Optional[str]
    logo_url: Optional[str]


@dataclass(frozen=True)
class AdminStatsOutputDTO:
    """Estadísticas globales del sistema para el dashboard de admin."""
    total_users: int
    active_users: int
    verified_users: int
    users_with_2fa: int
    admin_users: int
    total_assets: int
    total_analyses: int
