"""
infrastructure/persistence/models.py — Modelos ORM de Django.

Esta capa es el adaptador de la base de datos.
Los modelos de Django aquí son adaptadores de infraestructura: 
traducen entre el esquema relacional de PostgreSQL y las entidades del dominio.

IMPORTANTE: estos modelos NO son las entidades del dominio.
Las entidades son clases puras en core/domain/entities/.
Los modelos solo saben de base de datos.

Principio aplicado: Separación de responsabilidades (SRP).
Un modelo no tiene lógica de negocio; esa lógica vive en las entidades.
"""

from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


# ── Gestión de usuarios personalizados ────────────────────────────

class UserManager(BaseUserManager):
    """
    Manager personalizado para el modelo User.
    Necesario porque usamos email como campo de autenticación principal.
    """

    def create_user(self, email: str, username: str, password: str = None, **extra_fields):
        if not email:
            raise ValueError("El email es obligatorio.")
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)   # Django hashea la contraseña aquí
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, username: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, username, password, **extra_fields)
                                                                          

class User(AbstractBaseUser, PermissionsMixin):
    """
    Modelo de usuario extendido.

    Sustituye al User de Django mediante AUTH_USER_MODEL en settings.
    Usamos email como identificador principal en lugar de username.

    AbstractBaseUser: provee hashing de contraseña y gestión de sesión.
    PermissionsMixin: provee sistema de grupos y permisos de Django.
    """

    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(max_length=150, unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    # ── Campos de autenticación extendida ──────────────────────────
    is_email_verified = models.BooleanField(
        default=False,
        help_text="True cuando el usuario confirma su email.",
    )
    totp_secret = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Clave secreta TOTP (base32). Null si 2FA no está configurado.",
    )
    is_2fa_enabled = models.BooleanField(
        default=False,
        help_text="True cuando el usuario finaliza el setup de 2FA.",
    )

    objects = UserManager()

    # Django usará 'email' para autenticación en lugar de 'username'
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self) -> str:
        return self.email


# ── Modelos del dominio criptográfico ─────────────────────────────

class CryptoAsset(models.Model):
    """
    Modelo ORM para un activo criptográfico.

    Almacena los datos básicos del activo. Los datos de mercado
    en tiempo real se almacenan en MarketDataSnapshot.
    """

    symbol = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    current_price = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    market_cap = models.DecimalField(max_digits=30, decimal_places=2, null=True, blank=True)
    volume_24h = models.DecimalField(max_digits=30, decimal_places=2, null=True, blank=True)
    price_change_24h = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    coingecko_id = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    logo_url = models.URLField(max_length=500, null=True, blank=True)
    asset_address = models.CharField(max_length=200, null=True, blank=True)
    decimals = models.PositiveSmallIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "crypto_assets"
        verbose_name = "Activo Criptográfico"
        verbose_name_plural = "Activos Criptográficos"
        ordering = ["symbol"]

    def __str__(self) -> str:
        return f"{self.symbol} — {self.name}"


class MarketDataSnapshot(models.Model):
    """
    Instantánea de datos de mercado en un momento dado.

    Permite construir series temporales para análisis histórico.
    Cada registro es inmutable una vez creado (no se actualiza, se crea).
    """

    asset = models.ForeignKey(
        CryptoAsset,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    price = models.DecimalField(max_digits=20, decimal_places=8)
    volume = models.DecimalField(max_digits=30, decimal_places=2)
    market_cap = models.DecimalField(max_digits=38, decimal_places=2, null=True, blank=True)
    fully_diluted_valuation = models.DecimalField(max_digits=38, decimal_places=4, null=True, blank=True)
    circulating_supply = models.DecimalField(max_digits=38, decimal_places=4, null=True, blank=True)
    total_supply = models.DecimalField(max_digits=38, decimal_places=4, null=True, blank=True)
    max_supply = models.DecimalField(max_digits=38, decimal_places=4, null=True, blank=True)
    ath = models.DecimalField(max_digits=38, decimal_places=8, null=True, blank=True)
    ath_date = models.DateTimeField(null=True, blank=True)
    atl = models.DecimalField(max_digits=38, decimal_places=8, null=True, blank=True)
    atl_date = models.DateTimeField(null=True, blank=True)
    price_change_24h_pct = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    price_change_7d_pct = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    price_change_30d_pct = models.DecimalField(max_digits=18, decimal_places=8, null=True, blank=True)
    timestamp = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "market_data_snapshots"
        verbose_name = "Snapshot de Mercado"
        verbose_name_plural = "Snapshots de Mercado"
        ordering = ["-timestamp"]

    def __str__(self) -> str:
        return f"{self.asset.symbol} @ {self.timestamp}"


class PortfolioAsset(models.Model):
    """
    Posición de un activo dentro del portfolio de un usuario.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="portfolio_assets")
    asset = models.ForeignKey(CryptoAsset, on_delete=models.CASCADE, related_name="portfolio_entries")
    quantity = models.DecimalField(max_digits=38, decimal_places=18)
    purchase_value_usd = models.DecimalField(max_digits=38, decimal_places=18)
    current_value_usd = models.DecimalField(max_digits=38, decimal_places=18, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "portfolio_assets"
        verbose_name = "Posición de Portfolio"
        verbose_name_plural = "Posiciones de Portfolio"
        constraints = [
            models.UniqueConstraint(fields=["user", "asset"], name="uq_portfolio_asset_user_asset"),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} — {self.asset.symbol} ({self.quantity})"


class AnalysisExecution(models.Model):
    """
    Registro de una ejecución de análisis técnico/cuantitativo.

    Permite auditar qué análisis se han ejecutado, cuándo y con qué resultado.
    El campo 'result' almacena JSON con los resultados del análisis.
    """

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("running", "En ejecución"),
        ("completed", "Completado"),
        ("failed", "Fallido"),
    ]

    asset = models.ForeignKey(
        CryptoAsset,
        on_delete=models.CASCADE,
        related_name="analyses",
    )
    analysis_type = models.CharField(max_length=50)   # RSI, MACD, SMA, etc.
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    result = models.JSONField(null=True, blank=True)   # Resultado del análisis en JSON
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "analysis_executions"
        verbose_name = "Ejecución de Análisis"
        verbose_name_plural = "Ejecuciones de Análisis"

    def __str__(self) -> str:
        return f"{self.asset.symbol} — {self.analysis_type} ({self.status})"
