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


class StrategyDefinition(models.Model):
    """
    Estrategia generada por el algoritmo genético (Módulo 2) que ha superado el
    gating de robustez (Módulo 1).

    `spec` guarda el StrategySpec componible (Módulo 0) tal cual — JSON
    autocontenido que el compilador puede re-ejecutar. Junto a él se persisten
    las métricas de robustez de la zona de evolución, los checks del gating, el
    rendimiento en el tramo de validación final (holdout, datos jamás vistos) y
    la posición en el ranking de la generación.
    """

    STATUS_CHOICES = [
        ("candidate", "Candidata"),
        ("validated", "Validada"),     # pasó el gating de robustez
        ("rejected", "Descartada"),
        ("archived", "Archivada"),
    ]

    asset = models.ForeignKey(
        CryptoAsset,
        on_delete=models.CASCADE,
        related_name="strategy_definitions",
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=255)
    spec = models.JSONField()                       # StrategySpec componible (Módulo 0)
    spec_hash = models.CharField(max_length=64, db_index=True)
    interval = models.CharField(max_length=10, default="1d")
    rank = models.PositiveSmallIntegerField(default=0)
    fitness = models.FloatField(null=True, blank=True)
    passed_gating = models.BooleanField(default=False)
    robustness_metrics = models.JSONField(null=True, blank=True)   # PBO, Sharpe, MC, eficiencia…
    gating_checks = models.JSONField(null=True, blank=True)        # qué umbrales se cumplieron
    holdout_metrics = models.JSONField(null=True, blank=True)      # rendimiento en validación final
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="candidate")
    # Monitorización en vivo: una estrategia "activada" se reevalúa periódicamente
    # y notifica a su dueño cuando su señal cambia a compra o venta.
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="monitored_strategies",
        null=True, blank=True,
    )
    is_monitored = models.BooleanField(default=False, db_index=True)
    last_signal = models.CharField(max_length=8, default="HOLD")   # BUY | SELL | HOLD
    last_signal_at = models.DateTimeField(null=True, blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "strategy_definitions"
        verbose_name = "Estrategia Generada"
        verbose_name_plural = "Estrategias Generadas"
        ordering = ["rank", "-fitness"]
        indexes = [
            models.Index(fields=["asset", "interval", "status"]),
        ]

    def __str__(self) -> str:
        sym = self.asset.symbol if self.asset else "—"
        return f"#{self.rank} {sym} {self.name[:40]} ({self.status})"


class StrategySignalEvent(models.Model):
    """
    Registro de un cambio de señal de una estrategia monitorizada.

    La tarea periódica crea un evento cada vez que la señal de una estrategia
    activa pasa a compra o venta. Es el historial consultable in-app de lo que
    han "disparado" las estrategias del usuario (no solo la última señal).
    """

    SIGNAL_CHOICES = [("BUY", "Compra"), ("SELL", "Venta")]

    strategy = models.ForeignKey(
        StrategyDefinition, on_delete=models.CASCADE, related_name="signal_events",
    )
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="strategy_signal_events",
        null=True, blank=True,
    )
    signal = models.CharField(max_length=8, choices=SIGNAL_CHOICES)
    price = models.FloatField(null=True, blank=True)   # precio de cierre al disparar
    notified = models.BooleanField(default=False)      # si se envió el email
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "strategy_signal_events"
        verbose_name = "Evento de Señal"
        verbose_name_plural = "Eventos de Señal"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.signal} · {self.strategy_id} @ {self.created_at:%Y-%m-%d %H:%M}"


class PredictionRecord(models.Model):
    """
    Registro inmutable de una predicción de dirección del modelo ML, para poder
    comprobar después si acertó y medir el rendimiento REAL en vivo (no solo el
    backtest OOS). Es el bucle de mejora continua: cada predicción se guarda con
    el precio del momento y una fecha de resolución (cuando transcurre el
    horizonte); una tarea periódica trae el precio real entonces y la marca como
    acierto o fallo.
    """

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("correct", "Acierto"),
        ("incorrect", "Fallo"),
        ("unresolved", "Sin resolver"),
    ]
    DIRECTION_CHOICES = [("ALCISTA", "Alcista"), ("BAJISTA", "Bajista")]

    asset = models.ForeignKey(
        CryptoAsset, on_delete=models.SET_NULL, related_name="prediction_records",
        null=True, blank=True,
    )
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="prediction_records",
        null=True, blank=True,
    )
    asset_symbol = models.CharField(max_length=20, db_index=True)
    interval = models.CharField(max_length=10)
    horizon = models.PositiveSmallIntegerField()

    # ── Lo que predijo el modelo ──
    predicted = models.CharField(max_length=8, choices=DIRECTION_CHOICES)
    prob_up = models.FloatField()
    confidence = models.FloatField()
    edge = models.FloatField(null=True, blank=True)
    oos_accuracy = models.FloatField(null=True, blank=True)
    verdict = models.CharField(max_length=10, blank=True)
    model = models.CharField(max_length=80, blank=True)
    price_at_prediction = models.FloatField()

    # ── Resolución (se rellena cuando transcurre el horizonte) ──
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending", db_index=True)
    resolve_at = models.DateTimeField(db_index=True)
    actual_direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES, blank=True)
    price_at_resolution = models.FloatField(null=True, blank=True)
    actual_return_pct = models.FloatField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "prediction_records"
        verbose_name = "Registro de Predicción"
        verbose_name_plural = "Registros de Predicción"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "resolve_at"]),
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["asset_symbol", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.asset_symbol} {self.predicted} h{self.horizon} ({self.status})"
