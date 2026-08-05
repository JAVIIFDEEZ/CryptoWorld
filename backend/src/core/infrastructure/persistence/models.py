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
    notify_risk_digest = models.BooleanField(
        default=False,
        help_text="Recibir un resumen diario del riesgo de la cartera (VaR, "
                  "barreras del OMS y P&L) por email.",
    )
    notifications_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Última vez que el usuario abrió el centro de notificaciones; "
                  "los eventos posteriores cuentan como no leídos.",
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

    # ── Ciclo de vida: la condición para un universo sin sesgo de supervivencia ──
    # Sin estas dos fechas, cualquier estudio sobre "el universo" lo construye
    # con la lista de HOY, que contiene solo a los que sobrevivieron. El sesgo no
    # es pequeño ni acotado: en cripto la mortalidad de activos es alta, y las
    # muertes se concentran justo en los tramos de mercado que más importan.
    listed_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Inicio de cotización. Antes de esta fecha el activo no era operable.")
    delisted_at = models.DateTimeField(
        null=True, blank=True, db_index=True,
        help_text="Fin de cotización. Nulo = sigue vivo.")
    DELISTING_REASONS = [
        ("delisted", "Retirado del exchange"),
        ("dead", "Proyecto abandonado"),
        ("merged", "Fusionado con otro activo"),
        ("renamed", "Renombrado / redenominado"),
    ]
    delisting_reason = models.CharField(
        max_length=16, choices=DELISTING_REASONS, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_active(self) -> bool:
        """Sigue cotizando hoy."""
        return self.delisted_at is None

    def was_tradable_at(self, moment) -> bool:
        """
        ¿Era este activo operable en `moment`?

        La respuesta correcta a esta pregunta es lo único que separa un universo
        point-in-time de una lista de supervivientes. `listed_at` nulo significa
        fecha desconocida: se asume operable, porque inventar una fecha de alta
        excluiría datos reales, y ese error sí es silencioso.
        """
        if self.listed_at is not None and moment < self.listed_at:
            return False
        return self.delisted_at is None or moment < self.delisted_at

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


class StrategyExperimentRun(models.Model):
    """
    Registro APPEND-ONLY de cada ejecución del generador de estrategias.

    El paradigma de *research factory*: si solo se guardan las búsquedas que
    dieron algo, el número de pruebas realizadas queda subestimado y con él la
    deflación del Sharpe — se acaba creyendo un edge que es selección. Aquí se
    registra TODA ejecución, produjera estrategias o ninguna.

    Es a nivel de ejecución y no de genoma a propósito: un preset profundo
    evalúa miles de specs y la reoptimización nocturna corre sobre muchos
    activos, así que una fila por genoma serían millones de registros al mes.
    El dato que importa para la gobernanza —cuántas configuraciones se han
    probado sobre este activo— se conserva exactamente sumando `evaluations`,
    y los genomas que sobrevivieron ya viven en `StrategyDefinition`.

    Nunca se actualiza ni se borra: `save()` rechaza modificar una fila ya
    escrita. Un registro de experimentos que se puede reescribir no sirve de
    nada.
    """

    asset = models.ForeignKey(
        CryptoAsset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="experiment_runs",
    )
    # Se guarda el símbolo aparte del FK: si el activo se borra del catálogo, el
    # registro histórico debe seguir diciendo sobre qué se buscó.
    asset_symbol = models.CharField(max_length=20, db_index=True)
    interval = models.CharField(max_length=10, default="1d")

    # ── Reproducibilidad ──────────────────────────────────────────
    seed = models.IntegerField(null=True, blank=True)
    preset = models.CharField(max_length=20, blank=True, default="")
    optimizer = models.CharField(max_length=10, blank=True, default="single")
    # Huella del espacio de búsqueda (bloques + rangos + operadores). Dos
    # ejecuciones con la misma semilla pero distinto catálogo NO son comparables.
    catalog_version = models.CharField(max_length=32, blank=True, default="")
    candles = models.PositiveIntegerField(default=0)
    data_start = models.DateTimeField(null=True, blank=True)
    data_end = models.DateTimeField(null=True, blank=True)

    # ── Multiplicidad ─────────────────────────────────────────────
    evaluations = models.PositiveIntegerField(default=0)        # nº real de pruebas
    effective_trials = models.PositiveIntegerField(default=0)   # independientes tras agrupar
    expected_max_sharpe = models.FloatField(null=True, blank=True)  # umbral del azar con ese N

    # ── Resultado ─────────────────────────────────────────────────
    candidates_gated = models.PositiveIntegerField(default=0)
    passed_gating = models.PositiveIntegerField(default=0)
    best_fitness = models.FloatField(null=True, blank=True)
    best_deflated_sharpe = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "strategy_experiment_runs"
        verbose_name = "Ejecución del generador (registro)"
        verbose_name_plural = "Ejecuciones del generador (registro)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["asset_symbol", "interval", "-created_at"]),
        ]

    def save(self, *args, **kwargs):
        """Append-only: una ejecución registrada no se modifica jamás."""
        if self.pk is not None:
            raise ValueError(
                "StrategyExperimentRun es append-only: un registro de "
                "experimento no puede modificarse una vez escrito."
            )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return (f"{self.asset_symbol}/{self.interval} · {self.evaluations} pruebas "
                f"→ {self.passed_gating} validadas")


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
    last_signal = models.CharField(max_length=8, default="HOLD")   # BUY|SELL|SHORT|COVER|HOLD
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

    # Cuatro acciones, no dos. Una estrategia corta emite SHORT/COVER, y
    # forzarlas a BUY/SELL invertiría su significado: SELL es cerrar un largo,
    # no abrir un corto. Ver `strategy_spec.SIGNALS`.
    SIGNAL_CHOICES = [
        ("BUY", "Compra"),
        ("SELL", "Venta"),
        ("SHORT", "Apertura en corto"),
        ("COVER", "Cierre de corto"),
    ]

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


class PaperTradingAccount(models.Model):
    """
    Cartera virtual (paper trading) que sigue automáticamente una estrategia
    generada: invierte capital ficticio según sus señales de compra/venta y
    registra el P&L REALIZADO operación a operación.

    Cierra el bucle entre el generador y la operativa: el backtest dice cómo se
    habría comportado en el pasado; el paper trading lo verifica hacia delante con
    datos en vivo, sin arriesgar dinero. Una tarea periódica reevalúa la señal en
    la última vela y, si cambia, abre o cierra la posición aplicando costes
    (comisión + slippage) coherentes con el motor de backtest.
    """

    strategy = models.ForeignKey(
        StrategyDefinition, on_delete=models.CASCADE, related_name="paper_accounts",
    )
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="paper_accounts",
        null=True, blank=True,
    )
    asset_symbol = models.CharField(max_length=20, db_index=True)
    interval = models.CharField(max_length=10, default="1d")

    initial_capital = models.FloatField(default=10000.0)
    cash = models.FloatField(default=10000.0)          # efectivo disponible
    units = models.FloatField(default=0.0)             # tamaño de la posición abierta (0 = en liquidez)
    entry_price = models.FloatField(null=True, blank=True)   # precio medio de entrada (con coste)
    last_price = models.FloatField(null=True, blank=True)    # último cierre marcado a mercado
    realized_pnl = models.FloatField(default=0.0)      # P&L realizado acumulado (moneda)

    commission_bps = models.FloatField(default=10.0)   # coste por operación (puntos básicos)
    slippage_bps = models.FloatField(default=5.0)

    is_active = models.BooleanField(default=True, db_index=True)
    trades_count = models.PositiveIntegerField(default=0)   # operaciones cerradas (round-trips)
    wins = models.PositiveIntegerField(default=0)
    last_signal = models.CharField(max_length=8, default="HOLD")  # BUY|SELL|SHORT|COVER|HOLD
    last_eval_at = models.DateTimeField(null=True, blank=True)
    # Seguimiento de decadencia (decay): pico de patrimonio para medir drawdown y
    # bandera que se activa cuando la estrategia se degrada en vivo (dispara
    # reoptimización del activo sin esperar al ciclo semanal).
    peak_equity = models.FloatField(default=0.0)
    decayed = models.BooleanField(default=False, db_index=True)
    decayed_at = models.DateTimeField(null=True, blank=True)
    # ── Promoción a ejecución REAL (opcional, con límites) ──
    # Cuando live_enabled, las señales de esta cartera también se ejecutan en el
    # exchange del usuario con un TOPE de nocional por operación. Cualquier error
    # del broker desactiva la ejecución real (kill-switch) y guarda el motivo.
    live_connection = models.ForeignKey(
        "ExchangeConnection", on_delete=models.SET_NULL,
        related_name="live_paper_accounts", null=True, blank=True,
    )
    live_enabled = models.BooleanField(default=False, db_index=True)
    live_cap_usd = models.FloatField(default=100.0)      # nocional máximo por orden
    live_base_position = models.FloatField(default=0.0)  # unidades compradas en real
    live_error = models.CharField(max_length=300, blank=True, default="")
    # Sello del último kill-switch: alimenta el centro de notificaciones y se
    # limpia al reactivar la promoción.
    live_disabled_at = models.DateTimeField(null=True, blank=True)
    # Reconciliación OMS: última comparación posición esperada ↔ balance real
    # del exchange y discrepancia detectada (unidades base; 0 = cuadra).
    live_reconciled_at = models.DateTimeField(null=True, blank=True)
    live_discrepancy = models.FloatField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "paper_trading_accounts"
        verbose_name = "Cartera de Paper Trading"
        verbose_name_plural = "Carteras de Paper Trading"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["is_active", "asset_symbol", "interval"]),
        ]

    def __str__(self) -> str:
        return f"Paper #{self.id} {self.asset_symbol} ({'activa' if self.is_active else 'parada'})"

    @property
    def position_value(self) -> float:
        """Valor a mercado de la posición abierta (0 si está en liquidez)."""
        if self.units and self.last_price:
            return self.units * self.last_price
        return 0.0

    @property
    def equity(self) -> float:
        """Patrimonio total: efectivo + posición marcada a mercado."""
        return self.cash + self.position_value

    @property
    def total_return_pct(self) -> float:
        """Rentabilidad total sobre el capital inicial (realizado + latente)."""
        if not self.initial_capital:
            return 0.0
        return (self.equity / self.initial_capital - 1.0) * 100.0

    @property
    def drawdown_pct(self) -> float:
        """Caída actual desde el máximo histórico de patrimonio (≥ 0)."""
        peak = max(self.peak_equity, self.initial_capital)
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - self.equity) / peak * 100.0)


class PaperTrade(models.Model):
    """Operación individual (apertura o cierre) de una cartera de paper trading."""

    SIDE_CHOICES = [("BUY", "Compra"), ("SELL", "Venta")]

    account = models.ForeignKey(
        PaperTradingAccount, on_delete=models.CASCADE, related_name="trades",
    )
    side = models.CharField(max_length=4, choices=SIDE_CHOICES)
    price = models.FloatField()              # precio de cierre de la vela
    fill_price = models.FloatField()         # precio efectivo tras slippage
    units = models.FloatField()
    cost = models.FloatField(default=0.0)    # comisión + slippage aplicados (moneda)
    cash_after = models.FloatField()
    equity_after = models.FloatField()
    pnl = models.FloatField(null=True, blank=True)       # P&L realizado del cierre (moneda)
    pnl_pct = models.FloatField(null=True, blank=True)   # % sobre el coste de entrada
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "paper_trades"
        verbose_name = "Operación de Paper Trading"
        verbose_name_plural = "Operaciones de Paper Trading"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.side} {self.units:.4f} @ {self.price:.2f}"


class PaperEquitySnapshot(models.Model):
    """
    Foto del patrimonio de una cartera en un instante, marcada a mercado. La
    sucesión de snapshots forma la CURVA DE EQUITY: la evolución real del valor de
    la cartera, base para graficar el rendimiento y medir el drawdown.

    Se registra una en cada evaluación periódica (mark-to-market), haya operado o
    no, porque el patrimonio se mueve con el precio aunque no haya trade.
    """

    account = models.ForeignKey(
        PaperTradingAccount, on_delete=models.CASCADE, related_name="equity_snapshots",
    )
    equity = models.FloatField()             # patrimonio total (efectivo + posición)
    price = models.FloatField()              # precio de mercado en el instante
    in_position = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "paper_equity_snapshots"
        verbose_name = "Snapshot de Patrimonio"
        verbose_name_plural = "Snapshots de Patrimonio"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["account", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"#{self.account_id} {self.equity:.2f} @ {self.created_at:%Y-%m-%d %H:%M}"


class WatchedAddress(models.Model):
    """
    Dirección on-chain vigilada por un usuario (watchlist). Una tarea periódica
    consulta su saldo nativo y, cuando varía por encima de un umbral, registra una
    alerta (whale tracking ligero). Permite seguir wallets de interés —ballenas,
    tesorerías, contratos— sin construir un indexador propio: se apoya en la API
    de Blockscout.
    """

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="watched_addresses",
    )
    chain = models.CharField(max_length=20)            # slug de red (ethereum, base…)
    address = models.CharField(max_length=42)          # dirección EVM (0x + 40 hex)
    label = models.CharField(max_length=80, blank=True)  # alias legible opcional
    native_symbol = models.CharField(max_length=10, blank=True)
    # Umbral de variación (%) del saldo nativo que dispara una alerta.
    alert_threshold_pct = models.FloatField(default=5.0)

    last_balance = models.FloatField(null=True, blank=True)     # saldo nativo (unidades)
    last_value_usd = models.FloatField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "watched_addresses"
        verbose_name = "Dirección Vigilada"
        verbose_name_plural = "Direcciones Vigiladas"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "chain", "address"], name="uniq_watched_owner_chain_address",
            ),
        ]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.label or self.address[:10]} ({self.chain})"


class AddressAlert(models.Model):
    """Movimiento significativo detectado en una dirección vigilada."""

    DIRECTION_CHOICES = [("increase", "Entrada"), ("decrease", "Salida")]

    watched = models.ForeignKey(
        WatchedAddress, on_delete=models.CASCADE, related_name="alerts",
    )
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="address_alerts",
    )
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    balance_before = models.FloatField()
    balance_after = models.FloatField()
    delta = models.FloatField()           # variación en unidades nativas (con signo)
    delta_pct = models.FloatField()       # variación porcentual (con signo)
    value_usd = models.FloatField(null=True, blank=True)  # valor del movimiento (precio actual)
    notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "address_alerts"
        verbose_name = "Alerta de Dirección"
        verbose_name_plural = "Alertas de Dirección"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.direction} {self.delta_pct:+.1f}% · {self.watched_id}"


class WhaleMovementSnapshot(models.Model):
    """
    Movimiento on-chain grande persistido por el escáner periódico.

    El feed de ballenas en vivo es efímero (se consulta y se pierde); persistir
    los movimientos construye el HISTÓRICO propio que permite el análisis de
    flujo hacia/desde exchanges (presión vendedora vs acumulación) con series
    temporales — el edge on-chain. La dirección se clasifica al guardar usando
    las etiquetas públicas de entidad (dominio: onchain_flow.classify_flow).
    """

    DIRECTION_CHOICES = [
        ("to_exchange", "Depósito en exchange"),
        ("from_exchange", "Retirada de exchange"),
        ("between_exchanges", "Entre exchanges"),
        ("unknown", "Desconocida"),
    ]

    chain = models.CharField(max_length=20, db_index=True)   # slug de red (ethereum…)
    symbol = models.CharField(max_length=20)                 # activo movido (ETH, USDC…)
    kind = models.CharField(max_length=10, default="native") # native | token
    amount = models.FloatField()
    value_usd = models.FloatField(db_index=True)
    from_address = models.CharField(max_length=64, blank=True)
    to_address = models.CharField(max_length=64, blank=True)
    from_label = models.CharField(max_length=120, blank=True)
    to_label = models.CharField(max_length=120, blank=True)
    direction = models.CharField(max_length=20, choices=DIRECTION_CHOICES, db_index=True)
    tx_hash = models.CharField(max_length=80)
    moved_at = models.DateTimeField(db_index=True)           # timestamp del movimiento
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "whale_movement_snapshots"
        verbose_name = "Movimiento de Ballena"
        verbose_name_plural = "Movimientos de Ballena"
        ordering = ["-moved_at"]
        constraints = [
            # Un mismo hash puede mover varios activos (nativo + tokens); la
            # combinación identifica el movimiento concreto.
            models.UniqueConstraint(
                fields=["chain", "tx_hash", "symbol", "from_address", "to_address"],
                name="uniq_whale_movement",
            ),
        ]
        indexes = [
            models.Index(fields=["chain", "-moved_at"]),
            models.Index(fields=["direction", "-moved_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} ${self.value_usd:,.0f} {self.direction} ({self.chain})"


class LiveOrderRecord(models.Model):
    """
    Auditoría de TODA orden enviada al exchange real del usuario.

    Cubre las dos vías por las que el sistema puede mover dinero real:
      · `mirror` — la promoción automática paper→real (una señal del motor).
      · `manual` — una orden lanzada a mano desde el terminal de trading.

    Se registra todo intento: enviadas (con el id del broker y el precio de
    ejecución si el exchange lo devuelve), fallidas (con el motivo) y
    bloqueadas por el OMS (con la barrera que las frenó). Es la trazabilidad
    que permite comparar el P&L real contra el del paper, calcular el TCA y
    responder a la pregunta de cumplimiento: quién ordenó qué, cuándo y con
    qué resultado.

    `owner` es la clave de consulta canónica. `account` solo existe en las
    órdenes espejadas (una orden manual no nace de ninguna cartera de paper).
    """

    # `pending` es el estado en el que se reserva el intento ANTES de llamar al
    # exchange, para que la restricción de idempotencia se aplique de verdad.
    # Un registro que se quede en `pending` significa "resultado desconocido":
    # el proceso murió entre el envío y la confirmación, y eso es exactamente
    # lo que una auditoría debe poder decir en lugar de callarlo.
    STATUS_CHOICES = [
        ("pending", "En curso"), ("sent", "Enviada"),
        ("failed", "Fallida"), ("blocked", "Bloqueada"),
    ]
    SOURCE_CHOICES = [("mirror", "Promoción paper→real"), ("manual", "Orden manual")]

    # Dueño de la orden. Nullable a nivel de esquema solo para que la migración
    # pueda rellenarlo desde `account`; en código siempre se informa.
    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="live_orders",
        null=True, blank=True,
    )
    account = models.ForeignKey(
        "PaperTradingAccount", on_delete=models.CASCADE, related_name="live_orders",
        null=True, blank=True,
    )
    connection = models.ForeignKey(
        "ExchangeConnection", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="live_orders",
    )
    source = models.CharField(
        max_length=10, choices=SOURCE_CHOICES, default="mirror", db_index=True,
    )
    symbol = models.CharField(max_length=20)         # par unificado (BTC/USDT)
    side = models.CharField(max_length=4)            # buy | sell
    order_type = models.CharField(max_length=10, default="market")  # market | limit
    amount = models.FloatField()                     # unidades base
    ref_price = models.FloatField()                  # precio de referencia (vela del paper / limit)
    fill_price = models.FloatField(null=True, blank=True)  # ejecución real si el broker la devuelve
    notional_usd = models.FloatField(default=0.0)    # amount × ref_price
    is_testnet = models.BooleanField(default=True)
    broker_order_id = models.CharField(max_length=80, blank=True, default="")
    # Identificador de idempotencia que envía el cliente. Dos peticiones con el
    # mismo valor son el MISMO intento: la segunda devuelve el resultado de la
    # primera en lugar de mandar otra orden real al exchange.
    client_order_id = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, db_index=True)
    error = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "live_order_records"
        verbose_name = "Orden Real (auditoría)"
        verbose_name_plural = "Órdenes Reales (auditoría)"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account", "-created_at"]),
            models.Index(fields=["owner", "-created_at"], name="live_order_owner_created_idx"),
        ]
        constraints = [
            # La idempotencia se garantiza en la base de datos, no solo en el
            # código: dos peticiones concurrentes con el mismo client_order_id
            # no pueden crear dos órdenes reales. El filtro deja fuera el valor
            # vacío (las órdenes espejadas no lo usan).
            models.UniqueConstraint(
                fields=["owner", "client_order_id"],
                condition=~models.Q(client_order_id=""),
                name="uniq_live_order_client_id_per_owner",
            ),
        ]

    def save(self, *args, **kwargs):
        """Garantiza el invariante «todo registro de auditoría tiene dueño».

        `owner` es la clave por la que consultan el rastro de cumplimiento, el
        TCA y el libro de riesgo. Derivarlo aquí de la cartera —y no confiar en
        que cada llamante se acuerde— es lo que impide que una orden real acabe
        siendo invisible para esas tres superficies.
        """
        if self.owner_id is None and self.account_id is not None:
            self.owner_id = self.account.owner_id
            if "update_fields" in kwargs and kwargs["update_fields"] is not None:
                kwargs["update_fields"] = list(kwargs["update_fields"]) + ["owner"]
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        mode = "testnet" if self.is_testnet else "REAL"
        return f"{self.side} {self.amount:.6f} {self.symbol} ({self.status}, {mode})"


class OnChainSignalEvent(models.Model):
    """
    Cambio de régimen del indicador de presión on-chain (señal global).

    El escáner de ballenas, tras cada pasada, recalcula la presión de la ventana
    de 24h y registra un evento SOLO cuando el veredicto cambia (acumulación ↔
    presión vendedora ↔ equilibrio). Estos eventos alimentan el centro de
    notificaciones de todos los usuarios: el cruce de régimen es la señal
    accionable, no el valor continuo.
    """

    chain = models.CharField(max_length=20, db_index=True)
    verdict = models.CharField(max_length=20)      # ACUMULACION | PRESION_VENDEDORA | EQUILIBRIO
    previous_verdict = models.CharField(max_length=20, blank=True)
    pressure = models.FloatField()
    window_hours = models.PositiveSmallIntegerField(default=24)
    inflow_usd = models.FloatField(default=0.0)
    outflow_usd = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "onchain_signal_events"
        verbose_name = "Señal On-Chain"
        verbose_name_plural = "Señales On-Chain"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["chain", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.chain}: {self.previous_verdict or '—'} → {self.verdict} ({self.pressure:+.2f})"


class ExchangeConnection(models.Model):
    """
    Conexión de un usuario con un exchange para operar en mercado real (ccxt).

    Las credenciales se guardan CIFRADAS (Fernet con clave derivada de
    SECRET_KEY; ver infrastructure.security.crypto) — nunca en claro — y la API
    jamás las devuelve. `is_testnet` es True por defecto: toda conexión nace en
    el sandbox del exchange y pasar a real exige activarlo explícitamente.
    """

    SUPPORTED_EXCHANGES = [
        ("binance", "Binance"),
        ("kraken", "Kraken"),
        ("coinbase", "Coinbase Advanced"),
        ("bybit", "Bybit"),
        ("okx", "OKX"),
    ]

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="exchange_connections",
    )
    exchange = models.CharField(max_length=20, choices=SUPPORTED_EXCHANGES)
    label = models.CharField(max_length=80, blank=True)
    api_key_enc = models.TextField()          # cifrado Fernet
    api_secret_enc = models.TextField()       # cifrado Fernet
    api_password_enc = models.TextField(blank=True, default="")  # passphrase (OKX…)
    is_testnet = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "exchange_connections"
        verbose_name = "Conexión de Exchange"
        verbose_name_plural = "Conexiones de Exchange"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "is_active"]),
        ]

    def __str__(self) -> str:
        mode = "testnet" if self.is_testnet else "REAL"
        return f"{self.exchange} ({mode}) · {self.owner_id}"


class OhlcvCandle(models.Model):
    """
    Vela OHLCV persistida — el almacén histórico PROPIO del sistema.

    Un actor institucional no re-pide 500 velas a un exchange en cada análisis:
    acumula un histórico inmutable, verificable y reproducible. Cada análisis /
    backtest / generación puede entonces cubrir ciclos completos de mercado y
    citar exactamente sobre qué datos se validó. Solo se persisten velas
    CERRADAS (la vela en curso cambia hasta que cierra) y la restricción de
    unicidad hace idempotente cualquier re-ingesta.
    """

    symbol = models.CharField(max_length=20, db_index=True)      # BTC, ETH…
    interval = models.CharField(max_length=8)                    # 1h, 4h, 1d…
    open_time = models.BigIntegerField()                         # epoch ms UTC (apertura)
    open = models.FloatField()
    high = models.FloatField()
    low = models.FloatField()
    close = models.FloatField()
    volume = models.FloatField()
    source = models.CharField(max_length=20, default="binance")  # procedencia del dato
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ohlcv_candles"
        verbose_name = "Vela OHLCV"
        verbose_name_plural = "Velas OHLCV"
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "interval", "open_time"], name="uq_ohlcv_candle",
            ),
        ]
        indexes = [
            models.Index(fields=["symbol", "interval", "-open_time"]),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} {self.interval} @ {self.open_time}"


class ChainMetricPoint(models.Model):
    """
    Punto de una serie temporal on-chain — el almacén histórico del módulo de
    blockchain.

    Hasta ahora ese módulo no persistía nada: cada panel consultaba en vivo a
    Blockscout o Blockchair y mostraba una foto. Eso tiene tres consecuencias,
    todas visibles para el usuario:

      · **Si la fuente falla, el panel queda vacío.** Una API pública sin clave
        con ~1 petición/minuto de límite falla a menudo, y el módulo no tenía a
        qué replegarse.
      · **No hay tendencias.** «El gas está a 12 Gwei» no dice nada sin saber a
        cuánto ha estado. Los umbrales fijos por red (10/30 Gwei) son constantes
        arbitrarias que envejecen: lo que era caro en 2021 es carísimo hoy.
      · **No hay gráficas.** Un punto no se puede dibujar.

    El diseño es deliberadamente genérico —(cadena, métrica, instante, valor)—
    porque las métricas útiles difieren por cadena: Bitcoin tiene hashrate y
    dificultad, Ethereum tiene gas y utilización, y forzar un esquema con
    columnas fijas dejaría fuera la mitad.

    Los instantes se agrupan en cubos de 5 minutos: sin ellos, cada visita de
    cada usuario crearía una fila y el almacén crecería con el tráfico en vez de
    con el tiempo. Con cubos, la re-ingesta es idempotente y el volumen es
    predecible (~288 puntos por métrica y día).
    """

    chain = models.CharField(max_length=20, db_index=True)   # ethereum, bitcoin…
    metric = models.CharField(max_length=40)                 # gas_average, hashrate…
    timestamp = models.BigIntegerField()                     # epoch ms UTC (cubo)
    value = models.FloatField()
    source = models.CharField(max_length=20, default="blockscout")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chain_metric_points"
        verbose_name = "Punto de métrica on-chain"
        verbose_name_plural = "Puntos de métricas on-chain"
        constraints = [
            models.UniqueConstraint(
                fields=["chain", "metric", "timestamp"], name="uq_chain_metric_point",
            ),
        ]
        indexes = [
            models.Index(fields=["chain", "metric", "-timestamp"]),
        ]

    def __str__(self) -> str:
        return f"{self.chain}.{self.metric}={self.value} @ {self.timestamp}"


class FundingRateRecord(models.Model):
    """
    Tasa de financiación de un perpetuo en un momento de liquidación.

    El funding es lo que un largo paga a un corto (o al revés) cada 8 horas por
    mantener la posición abierta. No es un detalle de microestructura: en cripto
    llega a costar decenas de puntos básicos al día, se cobra tenga o no razón la
    posición, y su coste crece con la duración. Un backtest de perpetuos que lo
    ignora no está midiendo la estrategia — está midiendo una versión de ella que
    nadie puede operar.

    Se guarda el histórico completo, no la última lectura, porque el coste hay
    que aplicarlo en el momento en que se pagó: el funding es fuertemente
    autocorrelacionado y su media reciente no representa a la del tramo que se
    está backtesteando. La unicidad hace idempotente cualquier re-ingesta.
    """

    symbol = models.CharField(max_length=20, db_index=True)       # BTCUSDT
    funding_time = models.BigIntegerField()                       # epoch ms UTC
    # Fracción, NO porcentaje: 0.0001 = 1 bp por liquidación. Se guarda como
    # float con signo — positivo significa que los largos pagan.
    funding_rate = models.FloatField()
    mark_price = models.FloatField(null=True, blank=True)
    interval_hours = models.PositiveSmallIntegerField(default=8)
    source = models.CharField(max_length=20, default="binance")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "funding_rate_records"
        verbose_name = "Tasa de financiación"
        verbose_name_plural = "Tasas de financiación"
        constraints = [
            models.UniqueConstraint(
                fields=["symbol", "funding_time"], name="uq_funding_rate",
            ),
        ]
        indexes = [
            models.Index(fields=["symbol", "-funding_time"]),
        ]

    def __str__(self) -> str:
        return f"{self.symbol} funding {self.funding_rate:.6f} @ {self.funding_time}"


class ConfluenceSnapshot(models.Model):
    """
    Lectura del motor de confluencia 360° registrada para su verificación.

    El bucle de auto-aprendizaje del motor: cada lectura guarda el score de
    CADA fuente (técnica, ML, on-chain, noticias) y el precio del momento; al
    vencer el horizonte se resuelve contra el precio real y el aprendizaje de
    pesos (confluence_fusion.learn_weights) se alimenta de estas filas — las
    fuentes que aciertan ganan peso, las que no, lo pierden.
    """

    STATUS_CHOICES = [("pending", "Pendiente"), ("resolved", "Resuelta")]

    asset_symbol = models.CharField(max_length=20, db_index=True)
    scores = models.JSONField(default=dict)      # {fuente: score ∈ [-1,1]}
    fused_score = models.FloatField()
    verdict = models.CharField(max_length=30)
    price_at = models.FloatField()
    horizon_hours = models.PositiveIntegerField(default=24)
    resolve_at = models.DateTimeField(db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default="pending", db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    actual_return_pct = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "confluence_snapshots"
        verbose_name = "Lectura de confluencia"
        verbose_name_plural = "Lecturas de confluencia"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "resolve_at"])]

    def __str__(self) -> str:
        return f"Confluencia {self.asset_symbol} {self.verdict} ({self.status})"


class ConfluenceSignalEvent(models.Model):
    """
    Cambio de régimen del motor de confluencia 360° para un activo.

    La evaluación programada compara el veredicto actual con el del último
    evento y solo registra la TRANSICIÓN (entrar/salir/cambiar de confluencia)
    — nunca el estado repetido. Global (como los eventos de presión on-chain):
    alimenta el centro de notificaciones de todos los usuarios.
    """

    asset_symbol = models.CharField(max_length=20, db_index=True)
    verdict = models.CharField(max_length=30)
    previous_verdict = models.CharField(max_length=30, blank=True, default="")
    score = models.FloatField()
    agreement_pct = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "confluence_signal_events"
        verbose_name = "Evento de confluencia"
        verbose_name_plural = "Eventos de confluencia"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.asset_symbol}: {self.previous_verdict or '—'} → {self.verdict}"


class LiveRiskPolicy(models.Model):
    """
    Política de riesgo GLOBAL de la ejecución real de un usuario (OMS).

    Dos controles: límite de pérdida diaria y límite de concentración por
    activo. Ambos bloquean COMPRAS en real (abrir riesgo), nunca ventas.

    daily_loss_limit_usd: si la pérdida realizada HOY (sumando todas sus
    promociones paper→real) alcanza este umbral, el OMS bloquea nuevas COMPRAS
    en real hasta el día siguiente. Las ventas nunca se bloquean: reducir
    exposición siempre está permitido. Null = sin límite configurado.
    """

    owner = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="live_risk_policy",
    )
    daily_loss_limit_usd = models.FloatField(null=True, blank=True)
    # Máximo % del libro completo (exposición bruta) que puede ocupar un solo
    # activo. Si una compra en real lo superaría, se bloquea (nunca las ventas).
    # Null = sin límite de concentración.
    max_concentration_pct = models.FloatField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "live_risk_policies"
        verbose_name = "Política de riesgo en vivo"
        verbose_name_plural = "Políticas de riesgo en vivo"

    def __str__(self) -> str:
        limit = f"{self.daily_loss_limit_usd} USD/día" if self.daily_loss_limit_usd else "sin límite"
        return f"RiskPolicy({self.owner_id}, {limit})"


class PushSubscription(models.Model):
    """
    Suscripción Web Push de un navegador del usuario (PWA).

    Guarda el endpoint del push service y las claves del cliente (p256dh, auth)
    necesarias para cifrar el payload. Permite que las notificaciones críticas
    (kill-switch de ejecución real, controles de riesgo, cambios de régimen)
    lleguen al dispositivo AUNQUE la app esté cerrada. El endpoint es único por
    suscripción; un usuario puede tener varios dispositivos.
    """

    owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=500, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "push_subscriptions"
        verbose_name = "Suscripción Push"
        verbose_name_plural = "Suscripciones Push"

    def __str__(self) -> str:
        return f"Push({self.owner_id}, {self.endpoint[:40]}…)"


class QuantAlert(models.Model):
    """
    Alerta cuantitativa multi-métrica configurada por el usuario.

    A diferencia de PriceAlert (solo precio), evalúa cualquier métrica del
    sistema — técnica (RSI/ADX/StochRSI/MACD/vol/ATR/rango), precio,
    confluencia 360°, presión on-chain o riesgo de cartera (VaR/CVaR/
    concentración/exposición) — con disparo por flanco (edge-trigger) y
    cooldown, de modo que se re-arma sola y no genera spam. La evalúa Celery
    cada 3 min.
    """

    OPERATOR_CHOICES = [
        ("gt", "Mayor o igual que"),
        ("lt", "Menor que"),
        ("cross_up", "Cruza al alza"),
        ("cross_down", "Cruza a la baja"),
    ]

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="quant_alerts",
    )
    # Nulo = métrica de cartera (riesgo del libro completo), no ligada a un activo.
    asset = models.ForeignKey(
        CryptoAsset, on_delete=models.CASCADE, null=True, blank=True,
        related_name="quant_alerts",
    )
    metric = models.CharField(max_length=40)                 # clave del registro de métricas
    timeframe = models.CharField(max_length=4, default="1h")  # 1h/4h/1d (técnicas)
    operator = models.CharField(max_length=10, choices=OPERATOR_CHOICES)
    threshold = models.FloatField()
    cooldown_minutes = models.PositiveIntegerField(default=60)
    is_active = models.BooleanField(default=True)
    # Estado para el disparo por flanco: 'above' / 'below' / '' (desconocido).
    last_side = models.CharField(max_length=6, blank=True, default="")
    last_value = models.FloatField(null=True, blank=True)
    last_fired_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "quant_alerts"
        verbose_name = "Alerta Cuantitativa"
        verbose_name_plural = "Alertas Cuantitativas"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        target = self.asset.symbol if self.asset else "CARTERA"
        return (
            f"{self.user.email} — {target} {self.metric} "
            f"{self.operator} {self.threshold}"
        )


class QuantAlertFiring(models.Model):
    """Registro de cada disparo de una QuantAlert — alimenta el feed de avisos."""

    alert = models.ForeignKey(
        QuantAlert, on_delete=models.CASCADE, related_name="firings",
    )
    fired_at = models.DateTimeField(auto_now_add=True)
    value = models.FloatField()
    threshold = models.FloatField()
    operator = models.CharField(max_length=10)
    message = models.CharField(max_length=300)
    seen = models.BooleanField(default=False)

    class Meta:
        db_table = "quant_alert_firings"
        verbose_name = "Disparo de Alerta Cuantitativa"
        verbose_name_plural = "Disparos de Alertas Cuantitativas"
        ordering = ["-fired_at"]

    def __str__(self) -> str:
        return f"Firing({self.alert_id}, {self.value} {self.operator} {self.threshold})"
