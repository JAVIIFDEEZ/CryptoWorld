"""
core/models.py — Punto de entrada de modelos para Django.

Django descubre los modelos de una app buscando su módulo 'models'.
Como nuestros modelos ORM residen en la capa de infraestructura
(core/infrastructure/persistence/models.py), este archivo los importa
para que el sistema de apps de Django los registre correctamente bajo
la etiqueta de app 'core'.

No añadir lógica aquí. Este archivo es solo un adaptador de importación.
"""

from core.infrastructure.persistence.models import (  # noqa: F401
    UserManager,
    User,
    CryptoAsset,
    MarketDataSnapshot,
    PortfolioAsset,
    AnalysisExecution,
)

__all__ = [
    "UserManager",
    "User",
    "CryptoAsset",
    "MarketDataSnapshot",
    "PortfolioAsset",
    "AnalysisExecution",
]
