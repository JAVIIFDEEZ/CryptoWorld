"""
user.py — Entidad de dominio: Usuario.

Una entidad de dominio representa un objeto de negocio con identidad propia.
Esta clase NO hereda de ningún modelo de Django ni ORM.
La lógica de validación de negocio vive aquí, no en la base de datos.

Principio aplicado: Separación de responsabilidades (SRP).
La entidad solo sabe sobre sí misma, no sobre cómo se persiste.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class UserEntity:
    """
    Representa a un usuario del sistema en el dominio.

    id puede ser None cuando la entidad aún no ha sido persistida.
    """
    email: str
    username: str
    is_active: bool = True
    is_staff: bool = False
    date_joined: datetime = field(default_factory=datetime.utcnow)
    id: Optional[int] = None
    # Campos de autenticación extendida
    is_email_verified: bool = False
    totp_secret: Optional[str] = None
    is_2fa_enabled: bool = False

    def __post_init__(self) -> None:
        """Validaciones de negocio al crear la entidad."""
        if not self.email or "@" not in self.email:
            raise ValueError(f"Email inválido: '{self.email}'")
        if not self.username or len(self.username) < 3:
            raise ValueError("El nombre de usuario debe tener al menos 3 caracteres.")

    def deactivate(self) -> None:
        """Operación de dominio: desactivar cuenta."""
        self.is_active = False

    def promote_to_staff(self) -> None:
        """Operación de dominio: promover a staff."""
        self.is_staff = True
