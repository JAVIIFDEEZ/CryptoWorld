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
    pending_email = models.EmailField(
        null=True,
        blank=True,
        help_text=(
            "Nueva dirección solicitada por el usuario, a la espera de "
            "confirmación. Solo sustituye a email cuando el usuario "
            "verifica el enlace enviado a la nueva dirección."
        ),
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
    credentials_changed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Momento del último cambio de credenciales (contraseña, email o "
            "doble factor). Todo JWT emitido antes de esta marca se rechaza: "
            "es lo que hace que cambiar la contraseña expulse de verdad a "
            "las sesiones abiertas."
        ),
    )

    # ── Preferencias de cuenta ──────────────────────────────────────
    class Currency(models.TextChoices):
        USD = "usd", "Dólar Estadounidense (USD)"
        EUR = "eur", "Euro (EUR)"
        GBP = "gbp", "Libra Esterlina (GBP)"

    preferred_currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.USD,
        help_text="Moneda fiat de referencia para mostrar precios.",
    )
    notify_price_alerts = models.BooleanField(
        default=True,
        help_text="Recibir emails cuando se dispare una alerta de precio.",
    )
    notify_market_digest = models.BooleanField(
        default=False,
        help_text="Recibir resúmenes periódicos del estado del mercado.",
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


class AuditLog(models.Model):
    """
    Traza inmutable de los eventos relevantes para la seguridad.

    Registra quién hizo qué, cuándo, desde dónde y con qué resultado:
    inicios de sesión (con y sin éxito), cambios de credenciales, altas y
    bajas de doble factor, y toda acción del panel de administración.

    Decisiones de diseño:
      - `actor` es SET_NULL y se guarda además `actor_email`: la traza de
        un usuario debe sobrevivir al borrado de su cuenta, que es
        justamente el momento en que más falta hace.
      - No se almacena nunca el secreto involucrado (contraseña, código
        TOTP, token); solo el hecho de que la operación ocurrió.
      - `metadata` recoge contexto adicional no sensible en JSON.
    """

    class Action(models.TextChoices):
        LOGIN_SUCCESS = "login.success", "Inicio de sesión correcto"
        LOGIN_FAILURE = "login.failure", "Inicio de sesión fallido"
        LOGIN_BLOCKED = "login.blocked", "Inicio de sesión bloqueado"
        LOGOUT = "logout", "Cierre de sesión"
        TWO_FACTOR_CHALLENGE = "2fa.challenge", "Segundo factor solicitado"
        TWO_FACTOR_SUCCESS = "2fa.success", "Segundo factor superado"
        TWO_FACTOR_FAILURE = "2fa.failure", "Segundo factor fallido"
        TWO_FACTOR_ENABLED = "2fa.enabled", "Doble factor activado"
        TWO_FACTOR_DISABLED = "2fa.disabled", "Doble factor desactivado"
        RECOVERY_CODES_REGENERATED = "2fa.recovery_regenerated", "Códigos de recuperación regenerados"
        REGISTER = "account.register", "Registro de cuenta"
        EMAIL_VERIFIED = "account.email_verified", "Email verificado"
        PASSWORD_CHANGED = "account.password_changed", "Contraseña cambiada"
        PASSWORD_RESET = "account.password_reset", "Contraseña restablecida"
        EMAIL_CHANGE_REQUESTED = "account.email_change_requested", "Cambio de email solicitado"
        EMAIL_CHANGED = "account.email_changed", "Email cambiado"
        ACCOUNT_DELETED = "account.deleted", "Cuenta eliminada"
        ADMIN_USER_CREATED = "admin.user_created", "Usuario administrador creado"
        ADMIN_USER_UPDATED = "admin.user_updated", "Usuario modificado por un administrador"
        ADMIN_MARKET_SYNC = "admin.market_sync", "Sincronización de mercado forzada"

    class Outcome(models.TextChoices):
        SUCCESS = "SUCCESS", "Correcto"
        FAILURE = "FAILURE", "Fallido"

    actor = models.ForeignKey(
        "core.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_entries",
    )
    # Copia del identificador en el momento del evento: la traza debe
    # seguir siendo legible aunque la cuenta se borre o cambie de email.
    actor_email = models.EmailField(blank=True, default="")
    action = models.CharField(max_length=48, choices=Action.choices, db_index=True)
    outcome = models.CharField(
        max_length=8, choices=Outcome.choices, default=Outcome.SUCCESS
    )
    target_type = models.CharField(max_length=48, blank=True, default="")
    target_id = models.CharField(max_length=64, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True, default="")
    request_id = models.CharField(max_length=64, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_log"
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["actor", "-created_at"], name="idx_audit_actor_created"),
            models.Index(fields=["action", "-created_at"], name="idx_audit_action_created"),
        ]

    def __str__(self) -> str:
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {self.action} {self.outcome} {self.actor_email}"


class TwoFactorRecoveryCode(models.Model):
    """
    Código de recuperación 2FA de un solo uso.

    Se generan 10 al activar 2FA y permiten completar el login si el
    usuario pierde el dispositivo TOTP. Solo se almacena el hash
    (mismo esquema PBKDF2 que las contraseñas); el código en claro se
    muestra una única vez al usuario.
    """

    user = models.ForeignKey(
        "core.User",
        on_delete=models.CASCADE,
        related_name="recovery_codes",
    )
    code_hash = models.CharField(max_length=128)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "two_factor_recovery_codes"
        verbose_name = "Código de recuperación 2FA"
        verbose_name_plural = "Códigos de recuperación 2FA"

    def __str__(self) -> str:
        state = "usado" if self.used_at else "disponible"
        return f"RecoveryCode({self.user_id}, {state})"


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
        indexes = [
            # La consulta de sparklines filtra por activo y ventana temporal;
            # sin este índice compuesto degenera en un recorrido secuencial
            # sobre una tabla que crece ~144 filas/día por activo.
            models.Index(fields=["asset", "-timestamp"], name="idx_snapshot_asset_ts"),
        ]

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


class Position(models.Model):
    """
    Posición explícita de trading: LONG o SHORT sobre un activo.

    Soporta modo hedge (múltiples posiciones simultáneas en la misma dirección
    o dirección opuesta sobre el mismo activo). El coste medio (AVCO) se
    recalcula al añadir entradas. Las salidas parciales acumulan realized_pnl.
    """

    DIRECTION_CHOICES = [
        ("LONG", "Long"),
        ("SHORT", "Short"),
    ]
    STATUS_CHOICES = [
        ("OPEN", "Abierta"),
        ("CLOSED", "Cerrada"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="positions",
    )
    asset = models.ForeignKey(
        CryptoAsset,
        on_delete=models.CASCADE,
        related_name="positions",
    )
    direction = models.CharField(max_length=5, choices=DIRECTION_CHOICES)
    status = models.CharField(max_length=6, choices=STATUS_CHOICES, default="OPEN")
    label = models.CharField(max_length=200, blank=True, default="")

    # Precio de entrada ponderado (AVCO) — se actualiza al escalar la posición
    avg_entry_price = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    # Cantidad actualmente abierta (disminuye con cierres parciales)
    open_quantity = models.DecimalField(max_digits=38, decimal_places=18, default=0)
    # Cantidad total históricamente entrada (nunca decrece)
    initial_quantity = models.DecimalField(max_digits=38, decimal_places=18, default=0)

    # PnL realizado acumulado de cierres parciales anteriores
    realized_pnl = models.DecimalField(max_digits=38, decimal_places=8, default=0)

    opened_at = models.DateTimeField()
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "positions"
        verbose_name = "Posición"
        verbose_name_plural = "Posiciones"
        ordering = ["-opened_at"]
        indexes = [
            models.Index(fields=["user", "status", "-opened_at"], name="idx_position_user_status"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.user.email} — {self.direction} {self.open_quantity} "
            f"{self.asset.symbol} @ {self.avg_entry_price} [{self.status}]"
        )


class TradeHistory(models.Model):
    """
    Historial de operaciones de compra/venta dentro del portfolio del usuario.

    Cada registro representa una transacción individual (BUY o SELL).
    Puede estar asociado a una posición explícita (campo `position`).
    """

    TRADE_TYPE_CHOICES = [
        ("BUY", "Compra"),
        ("SELL", "Venta"),
    ]
    INTENT_CHOICES = [
        ("OPEN", "Apertura"),
        ("ADD", "Ampliación"),
        ("CLOSE", "Cierre"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="trades",
    )
    asset = models.ForeignKey(
        CryptoAsset,
        on_delete=models.CASCADE,
        related_name="trades",
    )
    # Posición a la que pertenece este trade (opcional para compatibilidad)
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trades",
    )
    trade_type = models.CharField(max_length=4, choices=TRADE_TYPE_CHOICES)
    # Intención del trade: apertura, ampliación o cierre de posición
    trade_intent = models.CharField(
        max_length=5, choices=INTENT_CHOICES, null=True, blank=True
    )
    quantity = models.DecimalField(max_digits=38, decimal_places=18)
    price_usd = models.DecimalField(max_digits=20, decimal_places=8)
    total_usd = models.DecimalField(max_digits=38, decimal_places=8)
    notes = models.CharField(max_length=500, blank=True, default="")
    executed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "trade_history"
        verbose_name = "Operación"
        verbose_name_plural = "Historial de Operaciones"
        ordering = ["-executed_at"]
        indexes = [
            models.Index(fields=["user", "-executed_at"], name="idx_trade_user_executed"),
            models.Index(fields=["position"], name="idx_trade_position"),
        ]

    def __str__(self) -> str:
        return f"{self.user.email} — {self.trade_type} {self.quantity} {self.asset.symbol} @ {self.price_usd}"


class PriceAlert(models.Model):
    """
    Alerta de precio configurada por el usuario.

    El worker de Celery evalúa periódicamente cada alerta activa
    comparando el precio actual del activo con el umbral.
    """

    CONDITION_CHOICES = [
        ("ABOVE", "Por encima de"),
        ("BELOW", "Por debajo de"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="price_alerts",
    )
    asset = models.ForeignKey(
        CryptoAsset,
        on_delete=models.CASCADE,
        related_name="price_alerts",
    )
    condition = models.CharField(max_length=5, choices=CONDITION_CHOICES)
    threshold_price = models.DecimalField(max_digits=20, decimal_places=8)
    is_active = models.BooleanField(default=True)
    is_triggered = models.BooleanField(default=False)
    triggered_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "price_alerts"
        verbose_name = "Alerta de Precio"
        verbose_name_plural = "Alertas de Precio"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="idx_alert_user_created"),
            # El worker de Celery barre cada 2 min las alertas pendientes:
            # este índice es el que evita escanear toda la tabla.
            models.Index(fields=["is_active", "is_triggered"], name="idx_alert_pending"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.user.email} — {self.asset.symbol} "
            f"{self.condition} {self.threshold_price} "
            f"({'activa' if self.is_active else 'inactiva'})"
        )


class UserWatchlist(models.Model):
    """
    Activo marcado como favorito (watchlist) por un usuario.

    Relación N:M entre User y CryptoAsset implementada de forma explícita
    para tener control sobre la tabla pivot y sus metadatos.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="watchlist_entries",
    )
    asset = models.ForeignKey(
        CryptoAsset,
        on_delete=models.CASCADE,
        related_name="watchlist_entries",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "user_watchlist"
        verbose_name = "Watchlist"
        verbose_name_plural = "Watchlists"
        constraints = [
            models.UniqueConstraint(fields=["user", "asset"], name="uq_watchlist_user_asset"),
        ]
        ordering = ["-added_at"]

    def __str__(self) -> str:
        return f"{self.user.email} ★ {self.asset.symbol}"
